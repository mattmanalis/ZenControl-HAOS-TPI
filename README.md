# Zen Controls Home Assistant Integration (TPI)

Custom Home Assistant integration for Zen Controls via TPI Advanced over UDP (`port 5108`).

## Current scope (MVP)

- Config flow setup (host + port)
- Auto-discovery of:
  - DALI groups
  - DALI control gear
- `light` entities for discovered groups/gears
- Dimming and on/off
- Color capability detection per gear (tunable white + RGB where reported)

## Install via HACS

1. In HACS, add this repository as a custom repository (`Integration`).
2. Install `Zen Controls TPI`.
3. Restart Home Assistant.
4. Add integration: `Settings -> Devices & Services -> Add Integration -> Zen Controls TPI`.
5. Enter controller IP (for example `10.127.127.99`) and port (`5108`).

## Notes

- Uses local UDP transport only.
- TCP mode is not required for this integration.
- Polling interval is currently 10 seconds.

## Planned next steps

- Add event/multicast listener for near-real-time updates
- Improve RGBWAF channel mapping
- Add scene entities/services
- Add diagnostics + repair flow for connectivity
