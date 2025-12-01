# Driver Integration

The driver is the central coordinator of your integration, managing device lifecycle, entity registration, and Remote events.

## Core Responsibilities

The `BaseIntegrationDriver` handles:

- ✅ Remote Two event handling (connect, disconnect, standby)
- ✅ Entity subscription management
- ✅ Device lifecycle (add, remove, connect, disconnect)
- ✅ State propagation from devices to entities
- ✅ Event routing and coordination

## Default Implementations

The driver provides sensible defaults for common patterns. **You typically don't need to override these methods** unless you have specific requirements:

### 1. create_entities() ✅ Has Default

**Default behavior**: Creates one entity instance per entity type passed to `__init__`.

```python
# Works automatically for standard entity creation
driver = MyIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[EntityTypes.MEDIA_PLAYER, EntityTypes.REMOTE]
)
# Creates MyMediaPlayer and MyRemote automatically
```

**Override only if** you need conditional entity creation:

```python
def create_entities(
    self, device_config: MyDeviceConfig, device: MyDevice
) -> list[Entity]:
    """Create entities based on device capabilities."""
    entities = []
    
    # Conditionally create entities
    if device.supports_playback:
        entities.append(MyMediaPlayer(device_config, device))
    
    # Only create remote if device supports it
    if device.supports_remote_control:
        entities.append(MyRemote(device_config, device))
    
    return entities
```

### 2. map_device_state() ✅ Has Default

**Default behavior**: Converts common state strings to `media_player.States`:

- `"ON"`, `"MENU"`, `"IDLE"` → `States.ON`
- `"OFF"`, `"POWER_OFF"` → `States.OFF`
- `"PLAYING"`, `"PLAY"` → `States.PLAYING`
- `"PAUSED"` → `States.PAUSED`
- `"STANDBY"` → `States.STANDBY`
- `"BUFFERING"` → `States.BUFFERING`
- Everything else → `States.UNKNOWN`

```python
# Works automatically for common device states
device.state = "PLAYING"  # Maps to media_player.States.PLAYING
```

**Override only if** you have custom state enums:

```python
def map_device_state(self, device_state: Any) -> media_player.States:
    """Map custom device state enum."""
    if isinstance(device_state, MyDeviceState):
        match device_state:
            case MyDeviceState.POWERED_ON:
                return media_player.States.ON
            case MyDeviceState.POWERED_OFF:
                return media_player.States.OFF
            case MyDeviceState.PLAYING:
                return media_player.States.PLAYING
            case _:
                return media_player.States.UNKNOWN
    
    # Fallback to default for string states
    return super().map_device_state(device_state)
```

### 3. device_from_entity_id() ✅ Has Default

**Default behavior**: Parses standard entity ID format `"entity_type.device_id"` or `"entity_type.device_id.entity_id"`.

```python
# Works automatically with create_entity_id()
entity_id = "media_player.receiver_123"
device_id = driver.device_from_entity_id(entity_id)  # Returns "receiver_123"
```

**Override only if** you use a custom entity ID format:

```python
def create_entities(
    self, device_config: MyDeviceConfig, device: MyDevice
) -> list[Entity]:
    """Custom entity ID format."""
    # Entity ID IS the device ID (custom format)
    return [MyMediaPlayer(device_config.identifier, ...)]

def device_from_entity_id(self, entity_id: str) -> str | None:
    """Parse custom entity ID format."""
    # For this custom format, entity_id IS the device_id
    return entity_id
```

!!! warning "Important"
    If you override `create_entities()` with a custom entity ID format, you **must** also override `device_from_entity_id()` to match. The framework will raise an error if you forget.

### 5. entity_type_from_entity_id() ✅ Has Default

**Default behavior**: Extracts entity type from standard format `"entity_type.device_id"`.

```python
entity_id = "media_player.receiver_123"
entity_type = driver.entity_type_from_entity_id(entity_id)  # Returns "media_player"
```

**Override only if** you use a custom entity ID format (same conditions as `device_from_entity_id()`).

### 6. sub_device_from_entity_id() ✅ Has Default

**Default behavior**: Extracts sub-device ID from 3-part format `"entity_type.device_id.sub_device_id"`.

```python
# 2-part format returns None
entity_id = "media_player.receiver_123"
sub_device = driver.sub_device_from_entity_id(entity_id)  # Returns None

# 3-part format returns the sub-device
entity_id = "light.hub_1.bedroom"
sub_device = driver.sub_device_from_entity_id(entity_id)  # Returns "bedroom"
```

Useful for hub-based integrations where one device exposes multiple entities.

### 7. get_entity_ids_for_device() ✅ Has Default

**Default behavior**: Queries the API for all entities (both available and configured) and filters by device ID.

```python
# Works automatically - no override needed
entity_ids = driver.get_entity_ids_for_device("receiver_123")
# Returns ["media_player.receiver_123", "remote.receiver_123"]
```

**Override only if** you need performance optimization:

```python
def __init__(self, loop):
    super().__init__(...)
    self._entity_cache: dict[str, list[str]] = {}

def get_entity_ids_for_device(self, device_id: str) -> list[str]:
    """Cached entity lookup for performance."""
    if device_id not in self._entity_cache:
        self._entity_cache[device_id] = [
            f"media_player.{device_id}",
            f"remote.{device_id}",
        ]
    return self._entity_cache[device_id]
```

### 8. on_device_update() ✅ Has Default

**Default behavior**: Automatically extracts entity-type-specific attributes from the update dict and updates configured/available entities. Supports all entity types (Button, Climate, Cover, Light, Media Player, Remote, Sensor, Switch).

```python
# Works automatically - device sends update, entities get updated
device.events.emit(DeviceEvents.UPDATE, device_id, {
    "state": "PLAYING",
    "volume": 50,
    "media_title": "Song Name"
})
# Framework automatically updates the configured entity attributes
```

**Special feature for media players**: When state is `OFF`, all media attributes (title, artist, duration, etc.) are automatically cleared. Control this with the `clear_media_when_off` parameter.

**Override only if** you need custom state mapping or attribute transformation:

```python
async def on_device_update(
    self, device_id: str, update: dict[str, Any] | None
) -> None:
    """Custom update handling with state transformation."""
    if update:
        # Transform device-specific values before calling default
        if "power_state" in update:
            update["state"] = "ON" if update["power_state"] else "OFF"
    
    await super().on_device_update(device_id, update)
```

## Event Handlers

### Device Events

Override these to customize device event handling:

```python
async def on_device_connected(self, device_id: str) -> None:
    """Device connected."""
    await super().on_device_connected(device_id)
    # Custom logic...

async def on_device_disconnected(self, device_id: str) -> None:
    """Device disconnected."""
    await super().on_device_disconnected(device_id)
    # Custom logic...

async def on_device_connection_error(
    self, device_id: str, message: str
) -> None:
    """Device connection error."""
    await super().on_device_connection_error(device_id, message)
    # Custom logic...

async def on_device_update(
    self, device_id: str, update: dict[str, Any] | None,
    clear_media_when_off: bool = True
) -> None:
    """Device state update."""
    # Default implementation handles all entity types
    await super().on_device_update(device_id, update, clear_media_when_off)
```

### Remote Events

Override these to customize Remote Two event handling:

```python
async def on_r2_connect_cmd(self) -> None:
    """Remote connected."""
    # Custom pre-connect logic...
    await super().on_r2_connect_cmd()

async def on_r2_disconnect_cmd(self) -> None:
    """Remote disconnected."""
    await super().on_r2_disconnect_cmd()
    # Custom cleanup...

async def on_r2_enter_standby(self) -> None:
    """Remote entering standby."""
    await super().on_r2_enter_standby()
    # Save power...

async def on_r2_exit_standby(self) -> None:
    """Remote exiting standby."""
    await super().on_r2_exit_standby()
    # Wake devices...
```

## Hub-Based Integrations

For integrations where entities are discovered dynamically from a hub device (like smart home bridges or multi-zone receivers), use the `require_connection_before_registry` flag:

```python
class MyHubDriver(BaseIntegrationDriver[MyHub, MyHubConfig]):
    def __init__(self):
        super().__init__(
            device_class=MyHub,
            entity_classes=[EntityTypes.LIGHT, EntityTypes.SWITCH],
            require_connection_before_registry=True  # Enable hub mode
        )
```

### How It Works

When `require_connection_before_registry=True`:

1. **Device Addition**: Uses `async_add_configured_device()` which connects first, then registers entities
2. **Entity Subscription**: Waits for connection before calling `async_register_available_entities()`
3. **Entity Discovery**: Entities are populated from the hub after connection

### Required Override

You must override `async_register_available_entities()` to populate entities from the hub:

```python
async def async_register_available_entities(
    self, device_config: MyHubConfig, device: MyHub
) -> None:
    """Register entities discovered from the hub."""
    # Get entities from connected hub
    hub_devices = await device.get_discovered_devices()
    
    for hub_device in hub_devices:
        entity_id = create_entity_id(
            EntityTypes.LIGHT, 
            device_config.identifier,
            hub_device.id  # Sub-entity ID
        )
        entity = Light(
            entity_id,
            hub_device.name,
            features=[light.Features.ON_OFF, light.Features.DIM]
        )
        self.api.available_entities.add(entity)
```

### Entity ID Helpers for Hubs

Use the 3-part entity ID format for hub devices:

```python
# Create entity ID with sub-device
entity_id = create_entity_id(EntityTypes.LIGHT, "hub_1", "bedroom_light")
# Result: "light.hub_1.bedroom_light"

# Parse it back
device_id = driver.device_from_entity_id(entity_id)  # "hub_1"
entity_type = driver.entity_type_from_entity_id(entity_id)  # "light"
sub_device = driver.sub_device_from_entity_id(entity_id)  # "bedroom_light"
```

## Minimal Example

Most drivers work with just the defaults:

```python
from ucapi_framework import BaseIntegrationDriver
from ucapi import EntityTypes

class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    """Simple integration driver - uses all defaults."""
    
    def __init__(self):
        super().__init__(
            device_class=MyDevice,
            entity_classes=EntityTypes.MEDIA_PLAYER,  # Or list of types
        )
    
    # That's it! The framework handles:
    # ✅ Entity creation (one per entity_class)
    # ✅ State mapping (common state strings)
    # ✅ Entity ID parsing (standard format)
    # ✅ Device updates (all entity types)
    # ✅ Event propagation
```

## Custom Example

Override only what you need:

```python
from ucapi_framework import BaseIntegrationDriver
from ucapi import EntityTypes, media_player

class MyDriver(BaseIntegrationDriver[MyDevice, MyDeviceConfig]):
    """Custom driver with specific requirements."""
    
    def __init__(self):
        super().__init__(
            device_class=MyDevice,
            entity_classes=[
                EntityTypes.MEDIA_PLAYER,
                EntityTypes.REMOTE,
            ]
        )
    
    def map_device_state(self, device_state: Any) -> media_player.States:
        """Custom state mapping for device-specific enums."""
        if isinstance(device_state, MyDeviceState):
            match device_state:
                case MyDeviceState.POWERED_ON:
                    return media_player.States.ON
                case MyDeviceState.POWERED_OFF:
                    return media_player.States.OFF
                case MyDeviceState.STREAMING:
                    return media_player.States.PLAYING
                case _:
                    return super().map_device_state(device_state)
        return super().map_device_state(device_state)
    
    async def on_device_connected(self, device_id: str) -> None:
        """Custom logic when device connects."""
        await super().on_device_connected(device_id)
        # Send notification or update UI
        _LOG.info(f"Device {device_id} is now online!")
```

See the [API Reference](../api/driver.md) for complete documentation of all methods and event handlers.
