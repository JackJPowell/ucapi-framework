# Advanced Entity Patterns

This guide covers advanced entity creation patterns introduced in the framework, including the Entity ABC for per-entity customization, factory functions for dynamic entity creation, and hub-based discovery patterns.

## Entity ABC for Per-Entity Customization

The framework provides an optional `Entity` ABC (Abstract Base Class) that allows individual entities to customize their behavior without overriding driver methods.

### Overview

By inheriting from `Entity` in addition to a ucapi entity class (like `MediaPlayer`, `Sensor`, etc.), you can:

- **Custom state mapping** per entity type
- **Automatic attribute filtering** to reduce unnecessary updates
- **Easy API access** for entity-specific operations

The framework automatically provides the `api` instance to entities - no manual initialization required!

### Basic Usage

```python
from ucapi import media_player
from ucapi_framework.entity import Entity

class MyMediaPlayer(media_player.MediaPlayer, Entity):
    def __init__(self, device_config, device):
        # Initialize the ucapi entity
        entity_id = self.create_entity_id(device.id, "media_player")
        media_player.MediaPlayer.__init__(
            self,
            entity_id,
            device.name,
            features=[media_player.Features.ON_OFF, media_player.Features.VOLUME],
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN}
        )
        # That's it! Framework sets self._api automatically
        # No need to call Entity.__init__()
    
    def map_entity_states(self, device_state):
        """Custom state mapping for this specific entity."""
        if device_state == "STREAM":
            return media_player.States.PLAYING
        elif device_state == "POWERING_ON":
            return media_player.States.ON
        # Use default mapping for other states
        return super().map_entity_states(device_state)
```

### Key Features

#### 1. Custom State Mapping

Override `map_entity_states()` to provide entity-specific state mapping:

```python
class ZoneMediaPlayer(media_player.MediaPlayer, Entity):
    def __init__(self, device_config, device, zone_id):
        self.zone_id = zone_id
        # ... entity initialization ...
    
    def map_entity_states(self, device_state):
        """Zone 2 has different state names."""
        if self.zone_id == 2:
            if device_state == "Z2_PLAYING":
                return media_player.States.PLAYING
            elif device_state == "Z2_STANDBY":
                return media_player.States.STANDBY
        return super().map_entity_states(device_state)
```

#### 2. Automatic Attribute Filtering

The `update_attributes()` method automatically filters out unchanged attributes to reduce API calls:

```python
class SmartSensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device):
        # ... entity initialization ...
    
    def process_reading(self, value):
        """Update sensor value with automatic filtering."""
        # Only changed attributes will be sent to the API
        self.update_attributes({
            sensor.Attributes.VALUE: value,
            sensor.Attributes.STATE: sensor.States.ON
        })
        # If value hasn't changed, nothing is sent!
```

You can also force updates:

```python
# Force update even if values haven't changed
self.update_attributes(attributes, force=True)
```

#### 3. Dataclass-Based State Management

Use `update_from_dataclass()` to manage entity state with dataclasses for better type safety and IDE support:

```python
from dataclasses import dataclass
from ucapi import media_player
from ucapi_framework import Entity

@dataclass
class MediaPlayerAttributes:
    STATE: media_player.States = media_player.States.UNKNOWN
    VOLUME: int = 0
    MUTED: bool = False

class MyMediaPlayer(media_player.MediaPlayer, Entity):
    def __init__(self, device_config, device):
        # Initialize ucapi entity
        entity_id = create_entity_id(device.id, "media_player")
        media_player.MediaPlayer.__init__(
            self, entity_id, device.name, features, attributes
        )
        self._device = device
        
        # Create attributes dataclass
        self.attrs = MediaPlayerAttributes()
    
    def sync_from_device(self):
        """Map device state to entity attributes."""
        self.attrs.STATE = self.map_entity_states(self._device.state)
        self.attrs.VOLUME = self._device.volume
        self.attrs.MUTED = self._device.is_muted
    
    async def handle_command(self, entity_id, cmd_id, params):
        """Handle commands and update state."""
        if cmd_id == media_player.Commands.ON:
            await self._device.turn_on()
            
            # Sync state from device
            self.sync_from_device()
            
            # Push to API - automatically filters unchanged attributes!
            self.update_from_dataclass(self.attrs)
        
        elif cmd_id == media_player.Commands.VOLUME:
            await self._device.set_volume(params['volume'])
            self.attrs.VOLUME = params['volume']
            self.update_from_dataclass(self.attrs)
```

Benefits of dataclass approach:

- Type hints and IDE autocomplete
- Easy to test and validate
- Clear separation of state from behavior
- Automatic change detection

#### 4. Manual Filtering

Use `filter_changed_attributes()` to check what would change before updating:

```python
update = {
    media_player.Attributes.STATE: media_player.States.PLAYING,
    media_player.Attributes.VOLUME: 50
}

# Get only the changed attributes
changed = self.filter_changed_attributes(update)
if changed:
    # Do something only if there are changes
    self._api.configured_entities.update_attributes(self.id, changed)
```

### Update Patterns

The framework supports two patterns for updating entity state:

#### Pattern 1: Device Event Updates (existing pattern)

```python
# In your device class
self.events.emit(
    DeviceEvents.UPDATE,
    entity_id,
    {
        media_player.Attributes.STATE: "PLAYING",
        media_player.Attributes.VOLUME: 50
    }
)

# Framework automatically:
# 1. Maps states via entity.map_entity_states() if entity inherits from Entity
# 2. Calls entity.update_attributes() which filters changes
# 3. Only sends changed attributes to the API
```

#### Pattern 2: Direct Entity Updates (new pattern)

```python
# In your entity's command handler
async def handle_command(self, entity_id, cmd_id, params):
    if cmd_id == media_player.Commands.ON:
        await self._device.turn_on()
        
        # Update attributes directly
        self.sync_from_device()  # Your method to read device state
        self.update_from_dataclass(self.attrs)  # Auto-filters!
```

Both patterns flow through the same `update_attributes()` → `filter_changed_attributes()` code path.

### Important Notes

- **MRO and `__init__()`**: Entity now has an `__init__()` that uses `*args, **kwargs` for cooperative multiple inheritance. You don't need to call it explicitly - Python's MRO handles it automatically when you call `super().__init__()`
- **Framework sets `_api` automatically**: After creating entities in `create_entities()`, the driver sets `entity._api = self.api`
- **No breaking changes**: Existing entities work without modification
- **Dataclasses optional**: Use dataclasses for convenience, or continue using dict-based updates

## Factory Functions for Dynamic Entities

The `entity_classes` parameter now supports **factory functions** in addition to entity classes. This enables powerful patterns for creating multiple entities dynamically.

### Basic Factory Pattern

Instead of a class, pass a callable that returns `Entity` or `list[Entity]`:

```python
from ucapi_framework import BaseIntegrationDriver

# In main function - no custom driver class needed!
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[
        MyMediaPlayer,  # Regular class
        lambda cfg, dev: MyRemote(cfg, dev),  # Factory returning single entity
        lambda cfg, dev: [  # Factory returning list
            MySensor(cfg, dev, "temperature"),
            MySensor(cfg, dev, "humidity"),
            MySensor(cfg, dev, "battery")
        ]
    ]
)
```

### Factory Function Signature

Factory functions receive the same parameters as entity class constructors:

```python
def create_sensors(device_config: MyConfig, device: MyDevice) -> list[Entity]:
    """Factory function that creates multiple sensors."""
    sensors = []
    for sensor_type in ["temperature", "humidity", "pressure"]:
        sensors.append(MySensor(device_config, device, sensor_type))
    return sensors
```

### Real-World Example: Static Sensor List

This pattern is useful when you have a fixed set of entities to create:

```python
# Define sensor configurations
SENSOR_TYPES = [
    {"id": "temp", "name": "Temperature", "unit": "°C"},
    {"id": "humidity", "name": "Humidity", "unit": "%"},
    {"id": "battery", "name": "Battery", "unit": "%"}
]

# In main function - no custom driver class needed
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[
        MyMediaPlayer,
        lambda cfg, dev: [
            MySensor(cfg, dev, sensor_config)
            for sensor_config in SENSOR_TYPES
        ]
    ]
)

class MySensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device, sensor_config):
        entity_id = create_entity_id(
            EntityTypes.SENSOR,
            device_config.id,
            sensor_config["id"]
        )
        sensor.Sensor.__init__(
            self,
            entity_id,
            sensor_config["name"],
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNAVAILABLE,
                sensor.Attributes.UNIT: sensor_config["unit"]
            }
        )
        self.sensor_type = sensor_config["id"]
```

## Hub-Based Discovery Pattern

For integrations where entities are discovered from a hub after connection, use `require_connection_before_registry=True` and factory functions that access device data.

### Setup

```python
# In main function
driver = BaseIntegrationDriver(
    device_class=LutronHub,
    entity_classes=[
        # Lights discovered from hub
        lambda cfg, dev: [
            LutronLight(cfg, dev, light)
            for light in dev.lights
        ],
        # Scenes discovered from hub
        lambda cfg, dev: [
            LutronScene(cfg, dev, scene)
            for scene in dev.scenes
        ]
    ],
    require_connection_before_registry=True  # Connect before creating entities
)
```

### Hub Device Implementation

The device populates entity data during connection:

```python
from ucapi_framework import BaseDeviceInterface, DeviceEvents

class LutronHub(BaseDeviceInterface):
    def __init__(self, device_config, loop=None, config_manager=None):
        super().__init__(device_config, loop, config_manager)
        self.lights = []
        self.scenes = []
    
    async def connect(self) -> bool:
        """Connect to hub and discover entities."""
        try:
            # Connect to the hub
            await self._client.connect()
            
            # Query available lights
            lights_data = await self._client.get_lights()
            self.lights = [
                LightInfo(id=light["id"], name=light["name"], zone=light["zone"])
                for light in lights_data
            ]
            
            # Query available scenes
            scenes_data = await self._client.get_scenes()
            self.scenes = [
                SceneInfo(id=scene["id"], name=scene["name"])
                for scene in scenes_data
            ]
            
            self.events.emit(DeviceEvents.CONNECTED, self.device_config.id)
            return True
        except Exception as e:
            self.events.emit(DeviceEvents.ERROR, self.device_config.id, str(e))
            return False
```

### Entity Implementation

Entities access the hub data passed from the factory:

```python
class LutronLight(light.Light, Entity):
    def __init__(self, device_config, device, light_info):
        self.light_info = light_info
        self.hub = device
        
        entity_id = create_entity_id(
            EntityTypes.LIGHT,
            device_config.id,
            light_info.id
        )
        
        light.Light.__init__(
            self,
            entity_id,
            light_info.name,
            features=[light.Features.ON_OFF, light.Features.DIM],
            attributes={
                light.Attributes.STATE: light.States.UNKNOWN,
                light.Attributes.BRIGHTNESS: 0
            },
            cmd_handler=self.handle_command
        )
    
    async def handle_command(self, entity_id, cmd_id, params):
        """Handle light commands."""
        if cmd_id == light.Commands.ON:
            await self.hub.set_light(self.light_info.id, True)
        elif cmd_id == light.Commands.OFF:
            await self.hub.set_light(self.light_info.id, False)
        # ... more commands ...
```

### How It Works

1. **Driver initialization**: Factory functions are stored but not called yet
2. **Device added**: When `async_add_configured_device()` is called (or via `on_subscribe_entities()`):
   - Device instance is created
   - `device.connect()` is called and awaited
   - During connection, device populates `lights`, `scenes`, etc.
3. **Entity creation**: After successful connection:
   - Driver calls factory functions with the connected device
   - Factories access `dev.lights`, `dev.scenes`, etc.
   - Multiple entities are created from the discovered data
4. **Entity registration**: Entities are registered with the API

**Note**: With factory functions, you don't need to override `async_register_available_entities()`.
The factory functions in `entity_classes` handle entity creation automatically after the device
connects and populates its data.

### Connection Flow

```text
on_subscribe_entities()
    └─> async_add_configured_device()
            ├─> _add_device_instance()  # Create device
            ├─> device.connect()        # Await connection
            │       └─> Populate device.lights, device.scenes
            └─> create_entities()       # Call factories
                    └─> Factory sees device.lights, device.scenes
                            └─> Creates Light and Scene entities
```

## Conditional Entity Creation

You can conditionally create entities based on device capabilities:

```python
# In main function
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[
        lambda cfg, dev: create_conditional_entities(cfg, dev)
    ]
)

def create_conditional_entities(device_config, device):
    """Create entities based on device capabilities."""
    entities = []
    
    # Always create media player
    entities.append(MyMediaPlayer(device_config, device))
    
    # Only create remote if supported
    if device.supports_remote:
        entities.append(MyRemote(device_config, device))
    
    # Create sensors only for certain models
    if device.model in ["Premium", "Pro"]:
        entities.extend([
            MySensor(device_config, device, "temperature"),
            MySensor(device_config, device, "power")
        ])
    
    return entities
```

## Migration from Override Pattern

### Old Pattern (Override `create_entities()`)

```python
class MyDriver(BaseIntegrationDriver):
    def create_entities(self, device_config, device):
        """Override to create multiple entities."""
        entities = []
        for zone in device_config.zones:
            if zone.enabled:
                entities.append(MyMediaPlayer(device_config, device, zone))
        return entities
```

### New Pattern (Factory Function in Constructor)

```python
# In main function - no custom driver class needed!
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[
        lambda cfg, dev: [
            MyMediaPlayer(cfg, dev, zone)
            for zone in cfg.zones
            if zone.enabled
        ]
    ]
)
```

### When to Still Override

Override `create_entities()` only for complex cases that can't be expressed in a factory:

- Custom parameters beyond `(device_config, device)`
- Complex initialization sequences
- Special error handling during entity creation

For most cases, use the factory function pattern in the driver constructor.

## Best Practices

### 1. Use Factory Functions for Multi-Entity Patterns

✅ **Do**: Use factory functions for lists of similar entities

```python
entity_classes=[
    lambda cfg, dev: [
        MySensor(cfg, dev, sensor_type)
        for sensor_type in SENSOR_TYPES
    ]
]
```

❌ **Don't**: Override `create_entities()` unless necessary

```python
def create_entities(self, device_config, device):
    return [MySensor(device_config, device, t) for t in SENSOR_TYPES]
```

### 2. Keep Factories Simple

✅ **Do**: Simple list comprehensions or helper functions

```python
lambda cfg, dev: [MySensor(cfg, dev, t) for t in SENSOR_TYPES]
```

❌ **Don't**: Complex logic in lambdas

```python
lambda cfg, dev: [
    MySensor(cfg, dev, t) if some_complex_condition(cfg, dev, t) 
    else MyOtherSensor(cfg, dev, t) 
    for t in SENSOR_TYPES
]
```

Instead, use a named function:

```python
def create_sensors(cfg, dev):
    sensors = []
    for t in SENSOR_TYPES:
        if some_complex_condition(cfg, dev, t):
            sensors.append(MySensor(cfg, dev, t))
        else:
            sensors.append(MyOtherSensor(cfg, dev, t))
    return sensors

# In driver:
entity_classes=[create_sensors]
```

### 3. Inherit from Entity When Needed

Only inherit from `Entity` ABC when you need:

- Custom state mapping per entity
- Automatic attribute filtering
- Easy access to the API in entity methods

Don't inherit from `Entity` for simple entities that use default behavior.

### 4. Document Hub Data Requirements

When using hub-based patterns, document what data the device must populate:

```python
class MyHub(BaseDeviceInterface):
    """
    Hub device for MyIntegration.
    
    Entity Creation Requirements:
        After successful connection, this device must populate:
        - self.lights: List[LightInfo] - Available lights
        - self.scenes: List[SceneInfo] - Available scenes
        
    These are accessed by factory functions in MyDriver.entity_classes.
    """
```

## Summary

The framework's entity system now provides:

1. **Entity ABC**: Optional per-entity customization without driver overrides
2. **Factory Functions**: Clean pattern for creating multiple entities dynamically
3. **Hub-Based Discovery**: Native support for hub integrations with `require_connection_before_registry`
4. **Backward Compatible**: All existing code continues to work

These patterns make it easier to build complex integrations while keeping code organized and maintainable.
