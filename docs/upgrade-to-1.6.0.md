# Upgrading to ucapi-framework 1.6.0

This guide covers the new features and changes introduced in version 1.6.0, which add support for dynamic entity management and driver references in devices.

## What's New in 1.6.0

Version 1.6.0 introduces three major enhancements for more flexible device and entity management:

1. **Driver Reference in Devices** - Devices can now access their parent driver
2. **Dynamic Entity Registration** - Add entities at runtime via `driver.add_entity()`
3. **Entity Filtering by Type** - Query entities by type using `driver.filter_entities_by_type()`

These features enable advanced use cases like hub devices that discover sub-devices dynamically.

## New Features

### 1. Driver Reference in Devices

All device classes now accept an optional `driver` parameter, giving devices access to their parent driver.

#### What Changed

The `__init__` method signature for all device classes now includes an optional `driver` parameter:

- `BaseDeviceInterface`
- `StatelessHTTPDevice`
- `PollingDevice`
- `WebSocketDevice`
- `WebSocketPollingDevice`
- `ExternalClientDevice`
- `PersistentConnectionDevice`

#### Migration Required?

**No.** This change is fully backwards compatible. The `driver` parameter is optional and defaults to `None`.

#### New Usage Pattern

```python
from ucapi_framework import StatelessHTTPDevice

class MyDevice(StatelessHTTPDevice):
    async def verify_connection(self):
        # Access driver if available
        if self.driver:
            # Can now call driver methods
            sensors = self.driver.filter_entities_by_type("sensor")
            print(f"Found {len(sensors)} sensors")
        
        # Your connection verification logic
        return True
```

The driver automatically passes itself when creating devices:

```python
# In BaseIntegrationDriver.add_configured_device()
device = self._device_class(
    device_config,
    self._available_entities,
    driver=self  # Automatically passed
)
```

### 2. Dynamic Entity Registration

New `add_entity()` method on `BaseIntegrationDriver` allows adding entities at runtime.

#### Use Case

Perfect for hub devices that discover sub-devices after initial setup:

- Smart home hubs discovering new lights, sensors, or switches
- Media servers discovering new players
- Network devices discovering new endpoints

#### Method Signature

```python
def add_entity(self, entity: Entity | FrameworkEntity) -> None:
    """
    Dynamically add an entity to available entities at runtime.
    
    Args:
        entity: The entity to add (ucapi Entity or framework Entity)
    """
```

#### Example: Hub Discovering New Devices

```python
from ucapi_framework import WebSocketDevice, Entity
from ucapi import EntityTypes

class SmartHomeHub(WebSocketDevice):
    async def on_message(self, message):
        """Handle WebSocket messages from the hub."""
        if message.get("type") == "new_device_discovered":
            # Hub discovered a new light
            device_data = message["device"]
            
            # Create a new entity
            new_light = Entity(
                entity_id=f"light.{self.identifier}.{device_data['id']}",
                entity_type=EntityTypes.LIGHT,
                name=device_data["name"],
                features=[light.Features.ON_OFF, light.Features.DIM],
                attributes={light.Attributes.STATE: light.States.OFF}
            )
            
            # Dynamically register it with the driver
            if self.driver:
                self.driver.add_entity(new_light)
                _LOG.info(f"Added new light: {new_light.id}")
```

#### Key Features

- **Automatic `_api` injection** - Framework entities automatically get the API reference
- **Entity replacement** - Adding an entity with an existing ID replaces the old one
- **Works with both entity types** - Accepts `ucapi.Entity` or framework `Entity` objects

### 3. Entity Querying Methods

Two new methods for finding and retrieving entities: `filter_entities_by_type()` and `get_entity_by_id()`.

#### filter_entities_by_type()

Query entities by their type from available entities, configured entities, or both.

**Method Signature:**

```python
def filter_entities_by_type(
    self,
    entity_type: EntityTypes | str,
    source: EntitySource | str = EntitySource.ALL,
) -> list[Entity]:
    """
    Filter entities by entity type from available and/or configured collections.
    
    Args:
        entity_type: The entity type to filter by (e.g., EntityTypes.SENSOR, "light")
        source: Which collection(s) to search:
            - EntitySource.ALL or "all" (default): Both available and configured
            - EntitySource.AVAILABLE or "available": Only available entities
            - EntitySource.CONFIGURED or "configured": Only configured entities
    
    Returns:
        List of Entity objects matching the specified type
    """
```

#### EntitySource Enum

New enum for type-safe source specification:

```python
from ucapi_framework import EntitySource

class EntitySource(Enum):
    ALL = "all"              # Query both collections
    AVAILABLE = "available"  # Query only available entities
    CONFIGURED = "configured" # Query only configured entities
```

#### Examples

```python
from ucapi_framework import BaseIntegrationDriver, EntitySource
from ucapi import EntityTypes

class MyDriver(BaseIntegrationDriver):
    async def custom_logic(self):
        # Get all sensors (both available and configured)
        sensors = self.filter_entities_by_type(EntityTypes.SENSOR)
        for sensor in sensors:
            print(f"Sensor: {sensor.id}, State: {sensor.attributes.get('state')}")
        
        # Get only available lights using enum
        lights = self.filter_entities_by_type(
            "light",
            source=EntitySource.AVAILABLE
        )
        
        # Get configured media players using string
        players = self.filter_entities_by_type(
            EntityTypes.MEDIA_PLAYER,
            source="configured"
        )
        
        # Process entities
        for sensor in sensors:
            print(f"Sensor: {sensor.id}, Value: {sensor.attributes.get('value')}")
```

#### Using in Devices

Devices can use this method via their driver reference:

```python
class MyHub(WebSocketDevice):
    async def handle_update_request(self):
        """Update all light entities."""
        if not self.driver:
            return
        
        # Get all light entities
        lights = self.driver.filter_entities_by_type(
            EntityTypes.LIGHT,
            source=EntitySource.CONFIGURED
        )
        
        # Update each light
        for light_entity in lights:
            await self.update_light_state(light_entity.id)
```

#### get_entity_by_id()

Retrieve a specific entity by its ID from available or configured entities.

**Method Signature:**

```python
def get_entity_by_id(
    self,
    entity_id: str,
    source: EntitySource | str = EntitySource.ALL,
) -> Entity | None:
    """
    Get a specific entity by its ID.
    
    Args:
        entity_id: Entity identifier to search for
        source: Which collection(s) to search:
            - EntitySource.ALL or "all" (default): Both available and configured
            - EntitySource.AVAILABLE or "available": Only available entities
            - EntitySource.CONFIGURED or "configured": Only configured entities
    
    Returns:
        Entity object if found, None otherwise
    """
```

**Examples:**

```python
# Get an entity from any source
entity = driver.get_entity_by_id("light.living_room.main")
if entity:
    print(f"Found: {entity.name}, State: {entity.attributes.get('state')}")

# Get only from configured entities
entity = driver.get_entity_by_id(
    "sensor.bedroom.temp",
    source=EntitySource.CONFIGURED
)

# Get only from available entities
entity = driver.get_entity_by_id(
    "media_player.zone1",
    source=EntitySource.AVAILABLE
)
```

**Using in Devices:**

```python
class MyDevice(WebSocketDevice):
    async def handle_command(self, entity_id: str, command: str):
        """Handle a command for a specific entity."""
        if not self.driver:
            return
        
        # Get the specific entity
        entity = self.driver.get_entity_by_id(entity_id)
        if entity:
            await self.execute_command(entity, command)
```

## Complete Example: Dynamic Hub Device

Here's a complete example combining all three new features:

```python
from ucapi_framework import (
    WebSocketDevice,
    BaseIntegrationDriver,
    Entity,
    EntitySource,
)
from ucapi import EntityTypes, light
import logging

_LOG = logging.getLogger(__name__)


class HubDevice(WebSocketDevice):
    """Hub device that discovers sub-devices dynamically."""
    
    async def on_message(self, message):
        """Handle messages from the hub."""
        msg_type = message.get("type")
        
        if msg_type == "device_discovered":
            await self._handle_new_device(message["device"])
        elif msg_type == "status_update":
            await self._handle_status_update(message)
    
    async def _handle_new_device(self, device_data):
        """Register a newly discovered device."""
        if not self.driver:
            _LOG.warning("No driver reference, cannot add entity")
            return
        
        # Create entity for the new device
        entity_id = f"{device_data['type']}.{self.identifier}.{device_data['id']}"
        new_entity = Entity(
            entity_id=entity_id,
            entity_type=EntityTypes.LIGHT,  # or determine from device_data
            name=device_data["name"],
            features=[light.Features.ON_OFF],
            attributes={light.Attributes.STATE: light.States.OFF}
        )
        
        # Dynamically add to driver
        self.driver.add_entity(new_entity)
        _LOG.info(f"Discovered and added: {entity_id}")
    
    async def _handle_status_update(self, update):
        """Update all entities of a specific type."""
        if not self.driver:
            return
        
        # Get all light entities managed by this hub
        lights = self.driver.filter_entities_by_type(
            EntityTypes.LIGHT,
            source=EntitySource.CONFIGURED
        )
        
        # Filter to just this hub's entities
        hub_lights = [
            light for light in lights
            if light.id.startswith(f"light.{self.identifier}.")
        ]
        
        # Update each light's state
        for light_entity in hub_lights:
            # Update logic here
            _LOG.debug(f"Updating {light_entity.id}")


class HubDriver(BaseIntegrationDriver):
    """Driver for hub devices with dynamic entity support."""
    
    def __init__(self):
        super().__init__(
            HubDevice,
            []  # Initial entities - hub will add more dynamically
        )
```

## Breaking Changes

**None.** Version 1.6.0 is fully backwards compatible.

- The `driver` parameter is optional with a default value of `None`
- Existing code that doesn't use the new features continues to work unchanged
- All device classes maintain their existing signatures with the optional parameter added

## Migration Checklist

Since there are no breaking changes, migration is optional. To take advantage of new features:

- [ ] **Update to 1.6.0**: `pip install --upgrade ucapi-framework`
- [ ] **Review use cases**: Identify devices that could benefit from dynamic entity management
- [ ] **Add driver references**: Update devices that need to call `add_entity()` or `filter_entities_by_type()`
- [ ] **Implement dynamic discovery**: For hub devices, add logic in WebSocket/polling handlers
- [ ] **Test thoroughly**: Verify dynamic entity registration works as expected

## Additional Resources

- [Driver API Reference](api/driver.md) - Full API documentation
- [Device Patterns Guide](guide/device-patterns.md) - Device implementation patterns
- [Advanced Entity Patterns](guide/advanced-entity-patterns.md) - Entity management strategies

## Support

If you encounter issues upgrading or have questions:

- GitHub Issues: [ucapi-framework/issues](https://github.com/JackJPowell/ucapi-framework/issues)
- Discord: [Unfolded Circle Community](https://discord.gg/zGVYf58)
