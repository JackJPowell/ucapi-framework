# Changelog

## Unreleased

### Added

- Web view support with `WebViewEntity`, `WebViewAttributes`, optional state
  routing and constructor options passed through to ucapi. Web view availability
  remains independent of the driver connection; commands run on the Remote UI.
- Native ucapi number support with `NumberEntity`, `NumberAttributes`, driver
  state routing, and explicit null value updates.
- Support and examples for sensor date, timestamp and duration device classes
  and the `custom_label` option through the standard ucapi constructor.

### Changed

- Require ucapi 0.7.1 or newer. Release is pending the upstream package.
- Web view support requires the upcoming ucapi release containing `ucapi.webview`.

### Fixed

- Align web view inheritance and attribute mapping with upstream's `Webview`
  class, and update capability tests for per-client contexts. Track the upstream
  unknown-capability filtering regression as expected failures.
- Continue to the default state refresh when a device returns an empty attribute
  dictionary.

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
