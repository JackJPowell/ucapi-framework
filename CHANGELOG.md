# Changelog

## 1.9.10 - 2026-11-26

### Changed

- Expose WebSocket and persistent-connection retry backoff factors as keyword-only
  options, retaining the existing default multiplier of two.
- Use configurable exponential backoff for external-client recovery, starting at
  0.5 seconds and capped at 30 seconds by default. Initial failures no longer wait
  for a watchdog tick before starting the retry schedule; retry limits are preserved.
- Allow configuring the initial persistent-connection retry delay, reset it on a
  new connection cycle, and pace recovery after normal connection closure.

### Fixed

- Serialize concurrent external-client connection requests to avoid duplicate
  clients and connected events.
- Mark `ExternalClientDevice` connected, emit `CONNECTED` once, and start its
  watchdog when the external client is already connected. Thanks to
  [@guyp2k](https://github.com/guyp2k) for
  [PR #25](https://github.com/JackJPowell/ucapi-framework/pull/25).

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
