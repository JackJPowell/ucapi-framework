# Changelog

## 1.9.9 - 2026-11-14

### Fixed

- Retry failed initial `ExternalClientDevice` connections when watchdog monitoring
  and automatic reconnection are enabled.
- Stop automatic retries when the configured reconnection limit is reached,
  while allowing an explicit `connect()` call to restart connection attempts.
- Return `False` from `ExternalClientDevice.connect()` when the device is still
  disconnected and the watchdog is waiting to reconnect.

## 1.9.8 - 2026-10-12

### Fixed

- Complete subscriptions that arrive before device connection or entity discovery,
  and refresh state when the requested entity becomes available.
- Discard pending subscriptions on unsubscribe, client disconnection, or device removal.
- Register missing hub entities when a background connection becomes ready.

## 1.9.7 - 2026-09-24

### Fixed

- Clean up the WebSocket and ping task when a connection closes normally.
- Wait before reconnecting after a normal WebSocket close to avoid rapid retries.
