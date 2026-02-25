# Zen Controls Home Assistant Integration (TPI)

Custom Home Assistant integration for Zen Controls via TPI Advanced over UDP (`port 5108`).

## Current scope (MVP)

- Config flow setup (host + port)
- Auto-discovery of:
  - DALI groups
  - DALI control gear
- `light` entities for discovered groups/gears
- `binary_sensor` occupancy entities for discovered groups (PIR/group occupancy events)
- Dimming and on/off
- Color capability detection per gear (tunable white + RGB where reported)
- Group color capability inference from group members (enables group colour temperature and RGB where supported)
- Near real-time state updates via Zen TPI event multicast (`239.255.90.67:6969`)

## Install via HACS

1. In HACS, add this repository as a custom repository (`Integration`).
2. Install `Zen Controls TPI`.
3. Restart Home Assistant.
4. Add integration: `Settings -> Devices & Services -> Add Integration -> Zen Controls TPI`.
5. Enter controller IP (for example `10.127.127.99`) and port (`5108`).

## Notes

- Uses local UDP transport only.
- TCP mode is not required for this integration.
- Polling interval is currently 5 seconds as a fallback when event push is unavailable.
- After HA-issued light commands, the integration does a short 1-second settle polling loop for faster in-app feedback.
  - State is updated optimistically immediately, with settle polling running in the background.

## Planned next steps

- Improve RGBWAF channel mapping
- Add scene entities/services
- Add diagnostics + repair flow for connectivity
