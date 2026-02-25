"""Zen Controls TPI Advanced UDP client and hub abstractions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
import logging
import socket
from typing import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

RESPONSE_OK = 0xA0
RESPONSE_ANSWER = 0xA1
RESPONSE_NO_ANSWER = 0xA2
RESPONSE_ERROR = 0xA3

COMMAND_QUERY_GROUP_LABEL = 0x01
COMMAND_QUERY_DALI_DEVICE_LABEL = 0x03
COMMAND_QUERY_INSTANCES_BY_ADDRESS = 0x0D
COMMAND_QUERY_TPI_EVENT_EMIT_STATE = 0x07
COMMAND_ENABLE_TPI_EVENT_EMIT = 0x08
COMMAND_QUERY_GROUP_MEMBERSHIP_BY_ADDRESS = 0x15
COMMAND_QUERY_GROUP_NUMBERS = 0x09
COMMAND_QUERY_GROUP_BY_NUMBER = 0x12
COMMAND_DALI_COLOUR = 0x0E
COMMAND_QUERY_CONTROL_GEAR_DALI_ADDRESSES = 0x1D
COMMAND_QUERY_CONTROLLER_VERSION_NUMBER = 0x1C
COMMAND_QUERY_CONTROLLER_LABEL = 0x24
COMMAND_QUERY_CONTROLLER_STARTUP_COMPLETE = 0x27
COMMAND_QUERY_IS_DALI_READY = 0x26
COMMAND_QUERY_DALI_COLOUR = 0x34
COMMAND_QUERY_DALI_COLOUR_FEATURES = 0x35
COMMAND_QUERY_DALI_COLOUR_TEMP_LIMITS = 0x38
COMMAND_DALI_ARC_LEVEL = 0xA2
COMMAND_DALI_OFF = 0xA9
COMMAND_DALI_QUERY_LEVEL = 0xAA

COLOUR_TYPE_TC = 0x20
COLOUR_TYPE_RGBWAF = 0x80

EVENT_HEADER = b"\x5A\x43"
EVENT_MULTICAST_GROUP = "239.255.90.67"
EVENT_MULTICAST_PORT = 6969

EVENT_LEVEL_CHANGE = 0x03
EVENT_GROUP_LEVEL_CHANGE = 0x04
EVENT_OCCUPANCY = 0x06
EVENT_COLOUR_CHANGED = 0x08
EVENT_GROUP_OCCUPANCY = 0x0A
EVENT_LEVEL_CHANGE_V2 = 0x0B

INSTANCE_TYPE_OCCUPANCY = 0x03
PIR_CLEAR_SECONDS = 30.0


class ZenTPIError(Exception):
    """Raised when TPI communication or decoding fails."""


@dataclass(slots=True)
class ZenEndpoint:
    """Address target for TPI commands."""

    address: int
    kind: str  # "group" or "gear"


@dataclass(slots=True)
class ZenEntityDescription:
    """Discovered target metadata."""

    unique_id: str
    name: str
    endpoint: ZenEndpoint
    supports_color_temp: bool = False
    supports_rgb: bool = False
    min_kelvin: int | None = None
    max_kelvin: int | None = None


@dataclass(slots=True)
class ZenEntityState:
    """Latest entity runtime state."""

    is_on: bool
    brightness: int | None = None
    color_temp_kelvin: int | None = None
    rgb_color: tuple[int, int, int] | None = None


@dataclass(slots=True)
class ZenPirDescription:
    """Discovered PIR instance metadata."""

    unique_id: str
    name: str
    control_device: int  # 0..63
    target_address: int  # 64..127
    instance: int


class ZenTPIClient:
    """Minimal async TPI Advanced client over UDP."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        retries: int,
        logger: logging.Logger | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._retries = retries
        self._seq = 0
        self._logger = logger or _LOGGER

    @staticmethod
    def _checksum(data: bytes) -> int:
        acc = 0
        for b in data:
            acc ^= b
        return acc & 0xFF

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    async def request_basic(
        self,
        command: int,
        address: int = 0x00,
        data: list[int] | None = None,
    ) -> tuple[int, bytes]:
        """Send a basic 8-byte TPI request and return response type and payload."""
        d = (data or [0x00, 0x00, 0x00])[:3]
        while len(d) < 3:
            d.append(0x00)

        seq = self._next_seq()
        body = bytes([0x04, seq, command & 0xFF, address & 0xFF, d[0], d[1], d[2]])
        packet = body + bytes([self._checksum(body)])

        last_error: Exception | None = None
        for _attempt in range(self._retries + 1):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            loop = asyncio.get_running_loop()
            try:
                await loop.sock_sendto(sock, packet, (self._host, self._port))
                while True:
                    raw, _addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), timeout=self._timeout
                    )
                    response = self._parse_response(raw)
                    if response[0] != seq:
                        continue
                    return response[1], response[2]
            except Exception as err:
                last_error = err
            finally:
                sock.close()

        raise ZenTPIError(f"TPI request timeout/failed for command 0x{command:02X}: {last_error}")

    async def request_dali_colour(
        self,
        address: int,
        arc_level: int,
        colour_type: int,
        colour_data: list[int],
    ) -> int:
        """Send a DALI_COLOUR command frame (12-byte request)."""
        seq = self._next_seq()

        payload = [address & 0xFF, arc_level & 0xFF, colour_type & 0xFF] + colour_data
        payload = payload[:8]
        while len(payload) < 8:
            payload.append(0x00)

        body = bytes([0x04, seq, COMMAND_DALI_COLOUR]) + bytes(payload)
        packet = body + bytes([self._checksum(body)])

        last_error: Exception | None = None
        for _attempt in range(self._retries + 1):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            loop = asyncio.get_running_loop()
            try:
                await loop.sock_sendto(sock, packet, (self._host, self._port))
                while True:
                    raw, _addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096), timeout=self._timeout
                    )
                    rseq, rtype, _payload = self._parse_response(raw)
                    if rseq != seq:
                        continue
                    return rtype
            except Exception as err:
                last_error = err
            finally:
                sock.close()

        raise ZenTPIError(f"DALI_COLOUR timeout/failed: {last_error}")

    def _parse_response(self, raw: bytes) -> tuple[int, int, bytes]:
        """Parse TPI advanced response: type, seq, len, data..., checksum."""
        if len(raw) < 4:
            raise ZenTPIError("Response too short")

        response_type = raw[0]
        seq = raw[1]
        data_len = raw[2]

        if len(raw) != (4 + data_len):
            raise ZenTPIError(f"Response length mismatch: expected {4 + data_len}, got {len(raw)}")

        if self._checksum(raw[:-1]) != raw[-1]:
            raise ZenTPIError("Response checksum mismatch")

        payload = raw[3:-1]
        return seq, response_type, payload


class ZenTPIDeviceHub:
    """High-level command helper used by the HA integration."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        retries: int,
        scan_groups: bool,
        scan_gears: bool,
    ) -> None:
        self.client = ZenTPIClient(host, port, timeout, retries, logger=_LOGGER)
        self.scan_groups = scan_groups
        self.scan_gears = scan_gears
        self._lock = asyncio.Lock()

        self.controller_label: str | None = None
        self.controller_version: str | None = None
        self.entities: dict[str, ZenEntityDescription] = {}
        self.states: dict[str, ZenEntityState] = {}
        self.group_occupancy: dict[int, bool] = {}
        self.pir_entities: dict[str, ZenPirDescription] = {}
        self.pir_states: dict[str, bool] = {}
        self._pir_expiry: dict[str, float] = {}
        self._pir_uid_by_target_instance: dict[tuple[int, int], str] = {}
        self._uid_by_address: dict[int, str] = {}
        self._callbacks: list[Callable[[], Awaitable[None]]] = []
        self._event_task: asyncio.Task | None = None
        self._event_stop = asyncio.Event()

    async def async_initialize(self) -> None:
        """Fetch controller details and perform one-time discovery."""
        async with self._lock:
            await self._load_controller_info()
            await self._discover_entities()
            await self._refresh_states_locked()

    async def async_start_events(self) -> None:
        """Start multicast event listener for near real-time state updates."""
        if self._event_task and not self._event_task.done():
            return
        await self._ensure_multicast_events_enabled()
        self._event_stop.clear()
        self._event_task = asyncio.create_task(self._event_listener_loop())
        _LOGGER.info("ZenControls: multicast listener started on %s:%s", EVENT_MULTICAST_GROUP, EVENT_MULTICAST_PORT)

    async def async_stop_events(self) -> None:
        """Stop multicast event listener."""
        self._event_stop.set()
        if self._event_task:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
            self._event_task = None

    def add_update_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register callback fired when events update local state."""
        self._callbacks.append(callback)

    async def async_refresh_states(self) -> dict[str, ZenEntityState]:
        """Refresh live state for all discovered entities."""
        async with self._lock:
            await self._refresh_states_locked()
            return dict(self.states)

    async def _load_controller_info(self) -> None:
        rtype, payload = await self.client.request_basic(COMMAND_QUERY_CONTROLLER_LABEL)
        if rtype == RESPONSE_ANSWER:
            self.controller_label = payload.decode("ascii", errors="ignore") or "Zen Controller"

        rtype, payload = await self.client.request_basic(COMMAND_QUERY_CONTROLLER_VERSION_NUMBER)
        if rtype == RESPONSE_ANSWER and len(payload) >= 3:
            self.controller_version = f"{payload[0]}.{payload[1]}.{payload[2]}"

    async def _discover_entities(self) -> None:
        entities: dict[str, ZenEntityDescription] = {}
        group_caps: dict[int, dict[str, int | bool]] = {}
        group_numbers: list[int] = []

        if self.scan_groups:
            group_numbers = await self._query_group_numbers()
            self.group_occupancy = {group: False for group in group_numbers}

        if self.scan_gears:
            gear_addresses = await self._query_control_gear_addresses()
            for gear in gear_addresses:
                label = await self._query_gear_label(gear)
                name = label or f"Gear {gear}"
                supports_tunable, supports_rgb, min_kelvin, max_kelvin = await self._query_gear_color_caps(gear)
                uid = f"gear_{gear}"
                entities[uid] = ZenEntityDescription(
                    unique_id=uid,
                    name=name,
                    endpoint=ZenEndpoint(address=gear, kind="gear"),
                    supports_color_temp=supports_tunable,
                    supports_rgb=supports_rgb,
                    min_kelvin=min_kelvin,
                    max_kelvin=max_kelvin,
                )
                if self.scan_groups and group_numbers:
                    memberships = await self._query_group_membership_by_gear(gear)
                    for group in memberships:
                        caps = group_caps.setdefault(
                            group,
                            {
                                "supports_color_temp": False,
                                "supports_rgb": False,
                                "min_kelvin": 0,
                                "max_kelvin": 0,
                            },
                        )
                        if supports_tunable:
                            caps["supports_color_temp"] = True
                            if min_kelvin is not None and (caps["min_kelvin"] == 0 or min_kelvin < caps["min_kelvin"]):
                                caps["min_kelvin"] = min_kelvin
                            if max_kelvin is not None and max_kelvin > caps["max_kelvin"]:
                                caps["max_kelvin"] = max_kelvin
                        if supports_rgb:
                            caps["supports_rgb"] = True

        await self._discover_pir_instances()

        if self.scan_groups:
            for group in group_numbers:
                label = await self._query_group_label(group)
                name = label or f"Group {group}"
                uid = f"group_{group}"
                caps = group_caps.get(group, {})
                min_kelvin = int(caps["min_kelvin"]) if caps.get("min_kelvin") else None
                max_kelvin = int(caps["max_kelvin"]) if caps.get("max_kelvin") else None
                entities[uid] = ZenEntityDescription(
                    unique_id=uid,
                    name=name,
                    endpoint=ZenEndpoint(address=64 + group, kind="group"),
                    supports_color_temp=bool(caps.get("supports_color_temp")),
                    supports_rgb=bool(caps.get("supports_rgb")),
                    min_kelvin=min_kelvin,
                    max_kelvin=max_kelvin,
                )

        if not entities:
            raise ZenTPIError("No groups or control gear discovered")

        self.entities = entities
        self._uid_by_address = {
            desc.endpoint.address: uid for uid, desc in self.entities.items()
        }

    async def _refresh_states_locked(self) -> None:
        states: dict[str, ZenEntityState] = {}
        for uid, entity in self.entities.items():
            level = await self._query_level(entity.endpoint.address)
            is_on = (level or 0) > 0
            state = ZenEntityState(is_on=is_on, brightness=level if level is not None else 0)

            if entity.supports_color_temp or entity.supports_rgb:
                colour = await self._query_colour(entity.endpoint.address)
                if colour is not None:
                    ctype = colour[0]
                    if ctype == COLOUR_TYPE_TC and len(colour) >= 3:
                        kelvin = (colour[1] << 8) | colour[2]
                        state.color_temp_kelvin = kelvin
                    elif ctype == COLOUR_TYPE_RGBWAF and len(colour) >= 4:
                        state.rgb_color = (colour[1], colour[2], colour[3])

            states[uid] = state

        self.states = states
        self._refresh_pir_timeouts()
        await self._refresh_group_occupancy_locked()

    async def async_set_level(self, uid: str, level: int) -> None:
        """Set DALI arc level (0..254)."""
        entity = self.entities[uid]
        _rtype, _payload = await self.client.request_basic(
            COMMAND_DALI_ARC_LEVEL,
            address=entity.endpoint.address,
            data=[0x00, 0x00, max(0, min(254, level))],
        )

    async def async_turn_off(self, uid: str) -> None:
        """Send DALI OFF."""
        entity = self.entities[uid]
        _rtype, _payload = await self.client.request_basic(
            COMMAND_DALI_OFF,
            address=entity.endpoint.address,
            data=[0x00, 0x00, 0x00],
        )

    async def async_set_color_temp_kelvin(self, uid: str, kelvin: int, arc_level: int = 0xFF) -> None:
        """Set tunable white color using DALI_COLOUR Tc payload."""
        entity = self.entities[uid]
        hi = (kelvin >> 8) & 0xFF
        lo = kelvin & 0xFF
        rtype = await self.client.request_dali_colour(
            address=entity.endpoint.address,
            arc_level=arc_level,
            colour_type=COLOUR_TYPE_TC,
            colour_data=[hi, lo],
        )
        if rtype not in (RESPONSE_OK, RESPONSE_NO_ANSWER):
            raise ZenTPIError(f"Colour temp command failed with response type 0x{rtype:02X}")

    async def async_set_rgb(self, uid: str, rgb: tuple[int, int, int], arc_level: int = 0xFF) -> None:
        """Set RGB via RGBWAF colour frame (W/A/F left at 0)."""
        entity = self.entities[uid]
        rtype = await self.client.request_dali_colour(
            address=entity.endpoint.address,
            arc_level=arc_level,
            colour_type=COLOUR_TYPE_RGBWAF,
            colour_data=[rgb[0], rgb[1], rgb[2], 0x00, 0x00],
        )
        if rtype not in (RESPONSE_OK, RESPONSE_NO_ANSWER):
            raise ZenTPIError(f"RGB command failed with response type 0x{rtype:02X}")

    async def _query_group_numbers(self) -> list[int]:
        rtype, payload = await self.client.request_basic(COMMAND_QUERY_GROUP_NUMBERS)
        if rtype != RESPONSE_ANSWER:
            return []
        return sorted(payload)

    async def _query_group_label(self, group_number: int) -> str | None:
        rtype, payload = await self.client.request_basic(
            COMMAND_QUERY_GROUP_LABEL,
            address=group_number,
        )
        if rtype != RESPONSE_ANSWER:
            return None
        return payload.decode("ascii", errors="ignore") or None

    async def _query_group_membership_by_gear(self, gear_address: int) -> list[int]:
        rtype, payload = await self.client.request_basic(
            COMMAND_QUERY_GROUP_MEMBERSHIP_BY_ADDRESS,
            address=gear_address,
        )
        if rtype != RESPONSE_ANSWER or len(payload) != 2:
            return []

        groups: list[int] = []
        high_byte = payload[0]
        low_byte = payload[1]
        for i in range(8):
            if low_byte & (1 << i):
                groups.append(i)
            if high_byte & (1 << i):
                groups.append(i + 8)
        return groups

    async def _refresh_group_occupancy_locked(self) -> None:
        """Poll current occupancy state for all discovered groups."""
        if not self.group_occupancy:
            return
        for group_number in list(self.group_occupancy.keys()):
            occupied = await self._query_group_occupancy(group_number)
            if occupied is not None:
                self.group_occupancy[group_number] = occupied

    async def _query_group_occupancy(self, group_number: int) -> bool | None:
        """Query group occupancy using QUERY_GROUP_BY_NUMBER."""
        rtype, payload = await self.client.request_basic(
            COMMAND_QUERY_GROUP_BY_NUMBER,
            address=group_number,
        )
        if rtype != RESPONSE_ANSWER or len(payload) < 3:
            return None
        # payload: [group_num, occupancy, level]
        return payload[1] == 0x01

    async def _query_control_gear_addresses(self) -> list[int]:
        rtype, payload = await self.client.request_basic(COMMAND_QUERY_CONTROL_GEAR_DALI_ADDRESSES)
        if rtype != RESPONSE_ANSWER or len(payload) != 8:
            return []

        addresses: list[int] = []
        for byte_index, byte_value in enumerate(payload):
            for bit_index in range(8):
                if byte_value & (1 << bit_index):
                    addresses.append(byte_index * 8 + bit_index)
        return addresses

    async def _query_gear_label(self, address: int) -> str | None:
        rtype, payload = await self.client.request_basic(
            COMMAND_QUERY_DALI_DEVICE_LABEL,
            address=address,
        )
        if rtype != RESPONSE_ANSWER:
            return None
        return payload.decode("ascii", errors="ignore") or None

    async def _query_gear_color_caps(self, address: int) -> tuple[bool, bool, int | None, int | None]:
        supports_tunable = False
        supports_rgb = False
        min_kelvin: int | None = None
        max_kelvin: int | None = None

        rtype, payload = await self.client.request_basic(COMMAND_QUERY_DALI_COLOUR_FEATURES, address=address)
        if rtype == RESPONSE_ANSWER and len(payload) == 1:
            features = payload[0]
            supports_tunable = bool(features & 0x02)
            supports_rgb = ((features & 0xE0) >> 5) > 0

        if supports_tunable:
            rtype, payload = await self.client.request_basic(COMMAND_QUERY_DALI_COLOUR_TEMP_LIMITS, address=address)
            if rtype == RESPONSE_ANSWER and len(payload) == 10:
                soft_warmest = (payload[4] << 8) | payload[5]
                soft_coolest = (payload[6] << 8) | payload[7]
                # HA expects min < max in Kelvin.
                min_kelvin = min(soft_warmest, soft_coolest)
                max_kelvin = max(soft_warmest, soft_coolest)

        return supports_tunable, supports_rgb, min_kelvin, max_kelvin

    async def _query_level(self, address: int) -> int | None:
        rtype, payload = await self.client.request_basic(COMMAND_DALI_QUERY_LEVEL, address=address)
        if rtype != RESPONSE_ANSWER or len(payload) != 1:
            return None
        if payload[0] == 255:
            return None
        return payload[0]

    async def _query_colour(self, address: int) -> list[int] | None:
        rtype, payload = await self.client.request_basic(COMMAND_QUERY_DALI_COLOUR, address=address)
        if rtype != RESPONSE_ANSWER or not payload:
            return None
        return list(payload)

    def get_kelvin_limits(self, uid: str) -> tuple[int | None, int | None]:
        """Return color temp limits in Kelvin if available."""
        entity = self.entities[uid]
        if not entity.min_kelvin or not entity.max_kelvin:
            return None, None
        return entity.min_kelvin, entity.max_kelvin

    async def _event_listener_loop(self) -> None:
        """Listen for Zen multicast events and apply in-memory state updates."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", EVENT_MULTICAST_PORT))
            mreq = socket.inet_aton(EVENT_MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setblocking(False)
            loop = asyncio.get_running_loop()
            while not self._event_stop.is_set():
                try:
                    raw, _addr = await loop.sock_recvfrom(sock, 2048)
                    if await self._process_event(raw):
                        await self._notify_callbacks()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    continue
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("ZenControls: multicast listener stopped: %s", err)
        finally:
            sock.close()

    async def _process_event(self, raw: bytes) -> bool:
        if len(raw) < 13 or raw[:2] != EVENT_HEADER:
            return False
        if ZenTPIClient._checksum(raw[:-1]) != raw[-1]:
            return False

        target = (raw[8] << 8) | raw[9]
        event_type = raw[10]
        data_len = raw[11]
        payload = raw[12:-1]
        if len(payload) != data_len:
            return False

        if event_type in (EVENT_LEVEL_CHANGE, EVENT_LEVEL_CHANGE_V2):
            return self._apply_level_event(target, payload)
        if event_type == EVENT_GROUP_LEVEL_CHANGE:
            group_target = 64 + target if target < 16 else target
            return self._apply_level_event(group_target, payload)
        if event_type == EVENT_OCCUPANCY:
            return self._apply_pir_event(target, payload)
        if event_type == EVENT_COLOUR_CHANGED:
            return self._apply_colour_event(target, payload)
        if event_type == EVENT_GROUP_OCCUPANCY:
            return self._apply_group_occupancy_event(target, payload)
        return False

    def _apply_level_event(self, address: int, payload: bytes) -> bool:
        uid = self._uid_by_address.get(address)
        if not uid or len(payload) < 1:
            return False
        level = payload[0]
        state = self.states.get(uid)
        if not state:
            return False
        if level == 255:
            return False
        state.brightness = level
        state.is_on = level > 0
        return True

    def _apply_colour_event(self, address: int, payload: bytes) -> bool:
        uid = self._uid_by_address.get(address)
        if not uid or len(payload) < 1:
            return False
        state = self.states.get(uid)
        if not state:
            return False

        ctype = payload[0]
        if ctype == COLOUR_TYPE_TC and len(payload) >= 3:
            state.color_temp_kelvin = (payload[1] << 8) | payload[2]
            state.rgb_color = None
            return True
        if ctype == COLOUR_TYPE_RGBWAF and len(payload) >= 4:
            state.rgb_color = (payload[1], payload[2], payload[3])
            state.color_temp_kelvin = None
            return True
        return False

    def _apply_group_occupancy_event(self, target: int, payload: bytes) -> bool:
        # Target is usually group + 64 in this event family.
        group_number = target - 64 if 64 <= target <= 79 else target
        if group_number not in self.group_occupancy:
            return False
        if len(payload) < 2:
            return False
        occupied = payload[1] == 0x01
        self.group_occupancy[group_number] = occupied
        return True

    def _apply_pir_event(self, target: int, payload: bytes) -> bool:
        # Target for occupancy event is control device address encoded as 64..127.
        if len(payload) < 1:
            return False
        instance = payload[0]
        uid = self._pir_uid_by_target_instance.get((target, instance))
        if not uid:
            return False
        self.pir_states[uid] = True
        self._pir_expiry[uid] = monotonic() + PIR_CLEAR_SECONDS
        return True

    async def _discover_pir_instances(self) -> None:
        """Discover occupancy instances on control devices (ECD 64..127)."""
        pir_entities: dict[str, ZenPirDescription] = {}
        pir_states: dict[str, bool] = {}
        pir_map: dict[tuple[int, int], str] = {}

        for target in range(64, 128):
            rtype, payload = await self.client.request_basic(
                COMMAND_QUERY_INSTANCES_BY_ADDRESS,
                address=target,
            )
            if rtype != RESPONSE_ANSWER or len(payload) < 4:
                continue

            label = await self._query_gear_label(target)
            base_name = label or f"Control Device {target - 64}"
            for i in range(0, len(payload), 4):
                if i + 3 >= len(payload):
                    break
                instance = payload[i]
                instance_type = payload[i + 1]
                if instance_type != INSTANCE_TYPE_OCCUPANCY:
                    continue
                uid = f"pir_{target - 64}_{instance}"
                pir_entities[uid] = ZenPirDescription(
                    unique_id=uid,
                    name=f"{base_name} PIR {instance}",
                    control_device=target - 64,
                    target_address=target,
                    instance=instance,
                )
                pir_states[uid] = False
                pir_map[(target, instance)] = uid

        self.pir_entities = pir_entities
        self.pir_states = pir_states
        self._pir_uid_by_target_instance = pir_map
        self._pir_expiry = {}

    def _refresh_pir_timeouts(self) -> None:
        """Auto-clear PIR states when hold time elapses without new events."""
        if not self._pir_expiry:
            return
        now = monotonic()
        for uid, expiry in list(self._pir_expiry.items()):
            if now >= expiry:
                self.pir_states[uid] = False
                del self._pir_expiry[uid]

    async def _notify_callbacks(self) -> None:
        for callback in self._callbacks:
            try:
                await callback()
            except Exception:
                continue

    async def _ensure_multicast_events_enabled(self) -> None:
        """Try to enable TPI event emission in multicast mode."""
        try:
            rtype, payload = await self.client.request_basic(COMMAND_QUERY_TPI_EVENT_EMIT_STATE)
            if rtype == RESPONSE_ANSWER and len(payload) == 1 and payload[0] == 0x01:
                return
            # 0x01 -> enabled, filtering off, unicast off, multicast on
            await self.client.request_basic(COMMAND_ENABLE_TPI_EVENT_EMIT, address=0x01)
            _LOGGER.info("ZenControls: requested controller to enable TPI multicast events")
        except Exception as err:
            _LOGGER.warning("ZenControls: unable to enable/query TPI multicast events: %s", err)
