# Device Patterns

The framework provides six base device classes for different connection patterns. Choose the one that matches your device's communication method.

## Separation of Concerns

The device layer has one job: **manage the connection and store raw hardware state**. It does not know about ucapi entities, attribute keys, or the Remote. When state changes, it calls `push_update()` to signal subscribers.

Entities subscribe to the device via `subscribe_to_device(device)` and translate raw state into ucapi attributes in their `sync_state()` method.

```
Device                         Entity
──────────────────             ──────────────────────────────
self.power = "PLAYING"   →     subscribe_to_device(device)
self.volume = 42         →     sync_state() called automatically
self.push_update()       →     self.update({Attributes.STATE: ..., Attributes.VOLUME: ...})
```

This separation means:

- The device can be used with any combination of entity types without changes
- Entities can be tested independently by injecting a mock device
- Adding a second entity type (e.g., a Remote alongside a MediaPlayer) requires zero changes to the device

---

## StatelessHTTPDevice

For devices with REST APIs where each request creates a new HTTP session.

**Good for:** REST APIs, simple HTTP devices

**You implement:**

- `verify_connection()` — Test device is reachable
- Property accessors (`identifier`, `name`, `address`, `log_id`)
- Any methods to send commands or fetch state

**Framework handles:**

- Connection verification
- Error handling

### Example

```python
from ucapi_framework import StatelessHTTPDevice
import aiohttp

class MyRESTDevice(StatelessHTTPDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(device_config, config_manager=config_manager)
        # Raw device state
        self.power: str = "OFF"
        self.volume: int = 0

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"

    async def verify_connection(self) -> None:
        """Verify device is reachable."""
        url = f"http://{self.address}/api/status"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()

    async def fetch_state(self) -> None:
        """Fetch current state and notify subscribers."""
        url = f"http://{self.address}/api/state"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                self.power = data["power"]
                self.volume = data["volume"]
                self.push_update()  # Notify subscribed entities

    async def send_command(self, command: str, params: dict | None = None) -> None:
        """Send command to device."""
        url = f"http://{self.address}/api/command"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"command": command, **(params or {})}) as response:
                response.raise_for_status()
```

---

## PollingDevice

For devices that need periodic state checks.

**Good for:** Devices without push notifications, devices with changing state

**You implement:**

- `establish_connection()` — Initial connection setup
- `poll_device()` — Periodic state check; update raw state and call `push_update()`
- Property accessors

**Framework handles:**

- Polling loop with configurable interval
- Automatic reconnection on errors
- Task management and cleanup

### Example

```python
from ucapi_framework import PollingDevice
import aiohttp

class MyPollingDevice(PollingDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,  # Poll every 30 seconds
            config_manager=config_manager,
        )
        self.power: str = "OFF"
        self.volume: int = 0

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"

    async def establish_connection(self) -> None:
        """Initial connection — fetch current state."""
        await self._fetch_and_notify()

    async def poll_device(self) -> None:
        """Called on each poll interval — update state and notify subscribers."""
        await self._fetch_and_notify()

    async def _fetch_and_notify(self) -> None:
        url = f"http://{self.address}/api/state"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                self.power = data["power"]
                self.volume = data["volume"]
                self.push_update()  # Notify subscribed entities
```

---

## WebSocketDevice

For devices with WebSocket APIs providing real-time updates.

**Good for:** Devices with WebSocket APIs, real-time updates

**You implement:**

- `create_websocket()` — Establish WebSocket connection
- `close_websocket()` — Close WebSocket connection
- `receive_message()` — Receive a single message from the WebSocket
- `handle_message()` — Process received message; update raw state and call `push_update()`
- Property accessors

**Framework handles:**

- WebSocket lifecycle (connect, reconnect, disconnect)
- Exponential backoff on connection failures
- Ping/pong keepalive
- Message loop and error handling

### Example

```python
from ucapi_framework import WebSocketDevice
import websockets
import json

class MyWebSocketDevice(WebSocketDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            reconnect=True,
            ping_interval=30,
            config_manager=config_manager,
        )
        self.power: str = "OFF"
        self.volume: int = 0
        self.source: str = ""

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"

    async def create_websocket(self):
        """Establish WebSocket connection."""
        uri = f"ws://{self.address}/ws"
        return await websockets.connect(uri)

    async def close_websocket(self) -> None:
        """Close WebSocket connection."""
        if self._ws:
            await self._ws.close()

    async def receive_message(self):
        """Receive a message."""
        return await self._ws.recv()

    async def handle_message(self, message: str) -> None:
        """
        Process a received message.

        Update raw device state, then call push_update() to notify all
        subscribed entities. Entities will call sync_state() to read the
        new values and push updated attributes to the Remote.
        """
        data = json.loads(message)
        self.power = data.get("power", self.power)
        self.volume = data.get("volume", self.volume)
        self.source = data.get("source", self.source)
        self.push_update()

    async def establish_connection(self) -> None:
        """Called after WebSocket is connected — fetch initial state."""
        # Optionally fetch full state before first push
        self.push_update()
```

---

## WebSocketPollingDevice

Hybrid device combining WebSocket for real-time updates with polling as a fallback.

**Good for:** Smart TVs, media players with WebSocket that may disconnect

**You implement:** Same as `WebSocketDevice` + `PollingDevice`

**Framework handles:**

- Runs both WebSocket and polling concurrently
- Continues polling if WebSocket fails
- Graceful degradation

### Example

```python
from ucapi_framework import WebSocketPollingDevice

class MyHybridDevice(WebSocketPollingDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,
            ping_interval=30,
            keep_polling_on_disconnect=True,
            config_manager=config_manager,
        )
        self.power: str = "OFF"
        self.volume: int = 0

    # Implement WebSocket methods (same as WebSocketDevice)
    async def create_websocket(self): ...
    async def close_websocket(self): ...
    async def receive_message(self): ...
    async def handle_message(self, message: str) -> None:
        ...
        self.push_update()

    # Implement Polling methods (same as PollingDevice)
    async def establish_connection(self): ...
    async def poll_device(self) -> None:
        ...
        self.push_update()
```

---

## PersistentConnectionDevice

For devices with persistent TCP connections or custom protocols.

**Good for:** Proprietary protocols, TCP connections, persistent sessions

**You implement:**

- `establish_connection()` — Create persistent connection
- `close_connection()` — Close connection
- `maintain_connection()` — Keep connection alive (blocking receive loop)
- Property accessors

**Framework handles:**

- Connection loop with automatic reconnection
- Exponential backoff on failures
- Task management

### Example

```python
from ucapi_framework import PersistentConnectionDevice
import asyncio

class MyTCPDevice(PersistentConnectionDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(device_config, config_manager=config_manager)
        self.power: str = "OFF"

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"

    async def establish_connection(self):
        """Establish TCP connection."""
        reader, writer = await asyncio.open_connection(self.address, 8080)
        return {"reader": reader, "writer": writer}

    async def close_connection(self) -> None:
        """Close TCP connection."""
        if self._connection:
            self._connection["writer"].close()
            await self._connection["writer"].wait_closed()

    async def maintain_connection(self) -> None:
        """Receive loop — called by framework, should block until disconnected."""
        reader = self._connection["reader"]
        while True:
            data = await reader.readline()
            if not data:
                break
            message = data.decode().strip()
            self.power = message  # Parse appropriately
            self.push_update()
```

---

## ExternalClientDevice

For devices using external client libraries that manage their own connections.

**Good for:** Z-Wave JS, Home Assistant WebSocket, MQTT clients, third-party APIs

**You implement:**

- `create_client()` — Create the external client instance
- `connect_client()` — Connect and set up event handlers
- `disconnect_client()` — Disconnect and remove event handlers
- `check_client_connected()` — Query actual client connection state
- Property accessors

**Framework handles:**

- Watchdog polling to detect silent disconnections
- Automatic reconnection with configurable retries
- Early exit if client is already connected
- Task management and cleanup

### Example

```python
from ucapi_framework import ExternalClientDevice

class MyExternalDevice(ExternalClientDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            enable_watchdog=True,
            watchdog_interval=30,
            reconnect_delay=5,
            max_reconnect_attempts=3,
            config_manager=config_manager,
        )
        self.power: str = "OFF"
        self.volume: int = 0

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str:
        return self._device_config.host

    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"

    async def create_client(self):
        from some_library import Client
        return Client(self.address)

    async def connect_client(self) -> None:
        await self._client.connect()
        self._client.on("state_changed", self._on_state_changed)

    async def disconnect_client(self) -> None:
        self._client.off("state_changed", self._on_state_changed)
        await self._client.disconnect()

    def check_client_connected(self) -> bool:
        return self._client is not None and self._client.connected

    def _on_state_changed(self, data: dict) -> None:
        """Handle state changes from the client library."""
        self.power = data.get("power", self.power)
        self.volume = data.get("volume", self.volume)
        self.push_update()  # Notify subscribed entities
```

---

## Choosing a Pattern

| Pattern | Use Case | Complexity |
|---|---|---|
| **StatelessHTTPDevice** | REST APIs, no real-time updates | ⭐ Simple |
| **PollingDevice** | Need periodic state checks | ⭐⭐ Moderate |
| **WebSocketDevice** | WebSocket APIs, real-time | ⭐⭐⭐ Complex |
| **WebSocketPollingDevice** | Hybrid with fallback | ⭐⭐⭐⭐ Advanced |
| **ExternalClientDevice** | Third-party client libraries | ⭐⭐⭐ Moderate |
| **PersistentConnectionDevice** | Custom protocols, TCP | ⭐⭐⭐⭐ Advanced |

See the [API Reference](../api/device.md) for complete documentation.
