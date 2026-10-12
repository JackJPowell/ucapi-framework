# Changelog

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
