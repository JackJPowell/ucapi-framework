# Device Patterns

The framework provides four base device classes for different connection patterns. Choose the one that matches your device's communication method.

## StatelessHTTPDevice

For devices with REST APIs where each request creates a new HTTP session.

**Good for:** REST APIs, simple HTTP devices

**You implement:**

- `verify_connection()` - Test device is reachable
- Property accessors (`identifier`, `name`, `address`, `log_id`)

**Framework handles:**

- HTTP session management
- Connection verification
- Error handling

### Example

```python
from ucapi_framework import StatelessHTTPDevice
import aiohttp

class MyRESTDevice(StatelessHTTPDevice):
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
    
    async def send_command(self, command: str) -> None:
        """Send command to device."""
        url = f"http://{self.address}/api/command"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"command": command}) as response:
                response.raise_for_status()
```

## PollingDevice

For devices that need periodic state checks.

**Good for:** Devices without push notifications, devices with changing state

**You implement:**

- `establish_connection()` - Initial connection setup
- `poll_device()` - Periodic state check (emits UPDATE events)
- Property accessors

**Framework handles:**

- Polling loop with configurable interval
- Automatic reconnection on errors
- Task management and cleanup

### Example

```python
from ucapi_framework import PollingDevice, DeviceEvents
import aiohttp

class MyPollingDevice(PollingDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,  # Poll every 30 seconds
            config_manager=config_manager
        )
        self._session = None
    
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
        """Initial connection."""
        self._session = aiohttp.ClientSession()
    
    async def poll_device(self) -> None:
        """Poll device state."""
        url = f"http://{self.address}/api/state"
        async with self._session.get(url) as response:
            state = await response.json()
            self._state = state["power"]
            
            # Emit update event
            self.events.emit(
                DeviceEvents.UPDATE,
                self.identifier,
                {"state": state["power"], "volume": state["volume"]}
            )
```

## WebSocketDevice

For devices with WebSocket APIs providing real-time updates.

**Good for:** Devices with WebSocket APIs, real-time updates

**You implement:**

- `create_websocket()` - Establish WebSocket connection
- `close_websocket()` - Close WebSocket connection
- `receive_message()` - Receive message from WebSocket
- `handle_message()` - Process received message
- Property accessors

**Framework handles:**

- WebSocket lifecycle (connect, reconnect, disconnect)
- Exponential backoff on connection failures
- Ping/pong keepalive
- Message loop and error handling

### Example

```python
from ucapi_framework import WebSocketDevice, DeviceEvents
import websockets

class MyWebSocketDevice(WebSocketDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            reconnect=True,
            ping_interval=30,  # Ping every 30 seconds
            config_manager=config_manager
        )
    
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
        """Create WebSocket connection."""
        uri = f"ws://{self.address}/ws"
        return await websockets.connect(uri)
    
    async def close_websocket(self) -> None:
        """Close WebSocket connection."""
        if self._ws:
            await self._ws.close()
    
    async def receive_message(self):
        """Receive message from WebSocket."""
        return await self._ws.recv()
    
    async def handle_message(self, message: str) -> None:
        """Process received message."""
        import json
        data = json.loads(message)
        
        if data["type"] == "state_update":
            self._state = data["state"]
            self.events.emit(
                DeviceEvents.UPDATE,
                self.identifier,
                {"state": data["state"]}
            )
```

## WebSocketPollingDevice

Hybrid device combining WebSocket for real-time updates with polling as a fallback.

**Good for:** Smart TVs, media players with WebSocket that may disconnect

**You implement:** Same as WebSocketDevice + PollingDevice

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
            config_manager=config_manager
        )
    
    # Implement WebSocket methods
    async def create_websocket(self): ...
    async def close_websocket(self): ...
    async def receive_message(self): ...
    async def handle_message(self, message): ...
    
    # Implement Polling methods
    async def establish_connection(self): ...
    async def poll_device(self): ...
```

## PersistentConnectionDevice

For devices with persistent TCP connections or custom protocols.

**Good for:** Proprietary protocols, TCP connections, persistent sessions

**You implement:**

- `establish_connection()` - Create persistent connection
- `close_connection()` - Close connection
- `maintain_connection()` - Keep connection alive (blocking)
- Property accessors

**Framework handles:**

- Connection loop with automatic reconnection
- Exponential backoff on failures
- Task management

### Example

```python
from ucapi_framework import PersistentConnectionDevice, DeviceEvents

class MyTCPDevice(PersistentConnectionDevice):
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
        reader, writer = await asyncio.open_connection(
            self.address, 8080
        )
        return {"reader": reader, "writer": writer}
    
    async def close_connection(self) -> None:
        """Close TCP connection."""
        if self._connection:
            self._connection["writer"].close()
            await self._connection["writer"].wait_closed()
    
    async def maintain_connection(self) -> None:
        """Maintain connection and process messages."""
        reader = self._connection["reader"]
        
        while True:
            data = await reader.readline()
            if not data:
                break  # Connection closed
            
            # Process message
            message = data.decode().strip()
            self.events.emit(
                DeviceEvents.UPDATE,
                self.identifier,
                {"message": message}
            )
```

## ExternalClientDevice

For devices using external client libraries that manage their own connections.

**Good for:** Z-Wave JS, Home Assistant WebSocket, MQTT clients, third-party APIs

**You implement:**

- `create_client()` - Create the external client instance
- `connect_client()` - Connect and set up event handlers
- `disconnect_client()` - Disconnect and remove event handlers
- `check_client_connected()` - Query actual client connection state
- Property accessors

**Framework handles:**

- Watchdog polling to detect silent disconnections
- Automatic reconnection with configurable retries
- Early exit if client is already connected
- Task management and cleanup

### Example

```python
from ucapi_framework import ExternalClientDevice, DeviceEvents

class MyExternalDevice(ExternalClientDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            enable_watchdog=True,      # Monitor connection state
            watchdog_interval=30,       # Check every 30 seconds
            reconnect_delay=5,          # Wait 5s between reconnect attempts
            max_reconnect_attempts=3,   # Give up after 3 failures (0 = infinite)
            config_manager=config_manager
        )
    
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
        """Create the external client instance."""
        from some_library import Client
        return Client(self.address)
    
    async def connect_client(self) -> None:
        """Connect the client and set up event handlers."""
        await self._client.connect()
        self._client.on("state_changed", self._on_state_changed)
    
    async def disconnect_client(self) -> None:
        """Disconnect and clean up."""
        self._client.off("state_changed", self._on_state_changed)
        await self._client.disconnect()
    
    def check_client_connected(self) -> bool:
        """Check actual client connection state."""
        return self._client is not None and self._client.connected
    
    def _on_state_changed(self, state):
        """Handle state changes from the client."""
        self.events.emit(
            DeviceEvents.UPDATE,
            self.identifier,
            {"state": state}
        )
```

## Choosing a Pattern

| Pattern | Use Case | Complexity |
|---------|----------|------------|
| **StatelessHTTPDevice** | REST APIs, no real-time updates | ⭐ Simple |
| **PollingDevice** | Need periodic state checks | ⭐⭐ Moderate |
| **WebSocketDevice** | WebSocket APIs, real-time | ⭐⭐⭐ Complex |
| **WebSocketPollingDevice** | Hybrid with fallback | ⭐⭐⭐⭐ Advanced |
| **ExternalClientDevice** | Third-party client libraries | ⭐⭐⭐ Moderate |
| **PersistentConnectionDevice** | Custom protocols, TCP | ⭐⭐⭐⭐ Advanced |

See the [API Reference](../api/device.md) for complete documentation.
