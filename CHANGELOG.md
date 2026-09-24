# Changelog

## 1.9.7 - 2026-09-24

### Fixed

- Clean up the WebSocket and ping task when a connection closes normally.
- Wait before reconnecting after a normal WebSocket close to avoid rapid retries.
