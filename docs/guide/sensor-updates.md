# Sensor Update Patterns

Sensors are unique among entity types because they're read-only - they don't have command handlers where state updates naturally occur. This guide covers two framework-provided patterns for updating sensor entities from device events.

## Overview

The framework provides two complementary approaches for updating sensor entities:

1. **Entity Registry Pattern** - Direct method calls using `update_entity()`
2. **Event-Based Pattern** - Using `DeviceEvents.UPDATE` with entity_id

Both patterns integrate seamlessly with the dataclass attribute system and work with `get_device_attributes()`.

## Pattern 1: Entity Registry (Recommended)

The entity registry pattern provides a simple API where entities register themselves during initialization, and the device calls `update_entity()` when state changes.

### How It Works

1. Entity registers itself during `__init__` using `device.register_entity()`
2. Device updates internal state
3. Device calls `update_entity(entity_id)` to push to Remote
4. Framework retrieves attributes via `get_device_attributes()` and calls `entity.update()`

### Example: Sensor with Polling Device

```python
from ucapi import sensor
from ucapi_framework import (
    Entity,
    PollingDevice,
    SensorAttributes,
    create_entity_id
)

class MySensor(sensor.Sensor, Entity):
    """Sensor that registers with device for updates."""
    
    def __init__(self, device_config, device, sensor_config):
        entity_id = create_entity_id(
            "sensor",
            device_config.id,
            sensor_config.id
        )
        
        super().__init__(
            entity_id,
            sensor_config.name,
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNAVAILABLE,
                sensor.Attributes.UNIT: sensor_config.unit
            }
        )
        
        self._device = device
        self.sensor_id = sensor_config.id
        
        # Register with device for updates
        device.register_entity(self.id, self)


class MyDevice(PollingDevice):
    """Device with sensors that updates via registry."""
    
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,
            config_manager=config_manager
        )
        # Track sensor data by sensor_id
        self.sensor_data = {}
    
    def get_device_attributes(self, entity_id: str) -> SensorAttributes:
        """Return current sensor attributes."""
        # Extract sensor_id from entity_id (e.g., "sensor.device.temp" -> "temp")
        sensor_id = entity_id.split('.')[-1]
        data = self.sensor_data.get(sensor_id, {})
        
        return SensorAttributes(
            STATE=sensor.States.ON if data else sensor.States.UNAVAILABLE,
            VALUE=data.get('value'),
            UNIT=data.get('unit', '°C')
        )
    
    async def poll_device(self):
        """Poll device and update all sensors."""
        # Fetch sensor readings from device API
        readings = await self.api.get_sensor_readings()
        
        for sensor_id, reading in readings.items():
            # Update internal state
            self.sensor_data[sensor_id] = {
                'value': reading.value,
                'unit': reading.unit
            }
            
            # Push to Remote - super clean!
            entity_id = f"sensor.{self.device_id}.{sensor_id}"
            self.update_entity(entity_id)
```

### Example: Sensor with WebSocket Device

```python
class MyDevice(WebSocketDevice):
    """Device with sensors that updates via registry."""
    
    def __init__(self, device_config, config_manager=None):
        super().__init__(device_config, config_manager=config_manager)
        self.sensor_data = {}
    
    def get_device_attributes(self, entity_id: str) -> SensorAttributes:
        """Return current sensor attributes."""
        sensor_id = entity_id.split('.')[-1]
        data = self.sensor_data.get(sensor_id, {})
        
        return SensorAttributes(
            STATE=sensor.States.ON if data else sensor.States.UNAVAILABLE,
            VALUE=data.get('value'),
            UNIT=data.get('unit')
        )
    
    async def handle_message(self, message):
        """Handle incoming WebSocket message."""
        if message['type'] == 'sensor_update':
            sensor_id = message['sensor_id']
            
            # Update internal state
            self.sensor_data[sensor_id] = {
                'value': message['value'],
                'unit': message['unit']
            }
            
            # Push to Remote
            entity_id = f"sensor.{self.device_id}.{sensor_id}"
            self.update_entity(entity_id)
```

### Benefits

- ✅ **Simple API** - Just call `update_entity(entity_id)`
- ✅ **Type-safe** - Works with dataclass attributes
- ✅ **No manual wiring** - Framework handles everything
- ✅ **Automatic validation** - Checks for Entity inheritance
- ✅ **Override detection** - Warns if `get_device_attributes()` not implemented

### Warning System

If you call `update_entity()` without overriding `get_device_attributes()`, you'll see:

```
WARNING: update_entity() called but get_device_attributes() is not overridden.
Override get_device_attributes() to return entity attributes for sensor.device.temp
```

## Pattern 2: Event-Based Updates

The event-based pattern uses the existing `DeviceEvents.UPDATE` event system with an optional `entity_id` parameter.

### How It Works

1. Device emits `DeviceEvents.UPDATE` with `entity_id` and `update` parameters
2. Framework's `on_device_update()` handler receives the event
3. Framework calls `refresh_entity_state()` for the specific entity
4. Entity state is updated via `entity.update()`

### Example: Event-Based Sensor Updates

```python
class MyDevice(PollingDevice):
    """Device using event-based sensor updates."""
    
    async def poll_device(self):
        """Poll device and emit update events."""
        readings = await self.get_sensor_readings()
        
        for sensor_id, reading in readings.items():
            entity_id = f"sensor.{self.device_id}.{sensor_id}"
            
            # Emit event - framework handles the rest
            self.events.emit(
                DeviceEvents.UPDATE,
                entity_id=entity_id,
                update=SensorAttributes(
                    STATE=sensor.States.ON,
                    VALUE=reading.value,
                    UNIT=reading.unit
                )
            )
```

### Example: WebSocket with Event Updates

```python
class MyDevice(WebSocketDevice):
    """WebSocket device using event-based updates."""
    
    async def handle_message(self, message):
        """Handle incoming WebSocket message."""
        if message['type'] == 'sensor_update':
            entity_id = f"sensor.{self.device_id}.{message['sensor_id']}"
            
            # Emit event with dataclass
            self.events.emit(
                DeviceEvents.UPDATE,
                entity_id=entity_id,
                update=SensorAttributes(
                    STATE=sensor.States.ON,
                    VALUE=message['value'],
                    UNIT=message['unit']
                )
            )
```

### Benefits

- ✅ **Event-driven** - Loose coupling between device and entities
- ✅ **Async-friendly** - Works naturally with WebSocket/async code
- ✅ **Dataclass support** - Pass dataclass or dict
- ✅ **No registration** - No need to register entities

## Choosing a Pattern

### Use Entity Registry When:

- ✅ You prefer explicit, direct method calls
- ✅ Entity registration feels natural (entity knows its device)
- ✅ You want type checking at the call site
- ✅ Debugging is easier with direct calls

### Use Event-Based When:

- ✅ You prefer event-driven architecture
- ✅ You're already using events for other updates
- ✅ You want loose coupling
- ✅ Multiple entities update from single message

## Complete Working Example

Here's a complete example showing both patterns:

```python
from dataclasses import dataclass
from ucapi import sensor
from ucapi_framework import (
    BaseIntegrationDriver,
    Entity,
    PollingDevice,
    SensorAttributes,
    create_entity_id
)

# Sensor configuration
@dataclass
class SensorConfig:
    id: str
    name: str
    unit: str

SENSORS = [
    SensorConfig("temp", "Temperature", "°C"),
    SensorConfig("humidity", "Humidity", "%"),
    SensorConfig("pressure", "Pressure", "hPa")
]

# Entity class
class MySensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device, sensor_config):
        entity_id = create_entity_id("sensor", device_config.id, sensor_config.id)
        
        super().__init__(
            entity_id,
            sensor_config.name,
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNAVAILABLE,
                sensor.Attributes.UNIT: sensor_config.unit
            }
        )
        
        self._device = device
        self.sensor_id = sensor_config.id
        
        # Register with device (for registry pattern)
        device.register_entity(self.id, self)

# Device class
class MyDevice(PollingDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,
            config_manager=config_manager
        )
        self.sensor_data = {}
    
    @property
    def identifier(self) -> str:
        return self._device_config.id
    
    @property
    def name(self) -> str:
        return self._device_config.name
    
    @property
    def address(self) -> str:
        return self._device_config.host
    
    @property
    def log_id(self) -> str:
        return f"Device[{self.identifier}]"
    
    def get_device_attributes(self, entity_id: str) -> SensorAttributes:
        """Return sensor attributes (for registry pattern)."""
        sensor_id = entity_id.split('.')[-1]
        data = self.sensor_data.get(sensor_id, {})
        
        return SensorAttributes(
            STATE=sensor.States.ON if data else sensor.States.UNAVAILABLE,
            VALUE=data.get('value'),
            UNIT=data.get('unit')
        )
    
    async def establish_connection(self):
        """Initial connection setup."""
        pass  # Your connection logic
    
    async def poll_device(self):
        """Poll device - demonstrates both patterns."""
        # Simulate getting sensor readings
        readings = {
            'temp': {'value': 23.5, 'unit': '°C'},
            'humidity': {'value': 65, 'unit': '%'},
            'pressure': {'value': 1013, 'unit': 'hPa'}
        }
        
        for sensor_id, reading in readings.items():
            # Update internal state
            self.sensor_data[sensor_id] = reading
            
            entity_id = f"sensor.{self.identifier}.{sensor_id}"
            
            # Choose one pattern:
            
            # Pattern 1: Registry (recommended)
            self.update_entity(entity_id)
            
            # OR Pattern 2: Event-based
            # self.events.emit(
            #     DeviceEvents.UPDATE,
            #     entity_id=entity_id,
            #     update=SensorAttributes(
            #         STATE=sensor.States.ON,
            #         VALUE=reading['value'],
            #         UNIT=reading['unit']
            #     )
            # )

# Driver setup with factory function
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[
        lambda cfg, dev: [
            MySensor(cfg, dev, sensor_config)
            for sensor_config in SENSORS
        ]
    ]
)
```

## Best Practices

1. **Override `get_device_attributes()`** - Always implement this method when using the registry pattern
2. **Use dataclasses** - Prefer `SensorAttributes` over dict for type safety
3. **Filter None values** - Dataclasses automatically filter None, dict updates should too
4. **Be consistent** - Choose one pattern and stick with it per device class
5. **Log sensor updates** - Help debugging with clear log messages

## Common Pitfalls

### Forgetting to Override get_device_attributes()

```python
# ❌ Won't work - no attributes returned
class MyDevice(PollingDevice):
    async def poll_device(self):
        self.update_entity("sensor.device.temp")  # Warning logged!

# ✅ Correct - implements get_device_attributes()
class MyDevice(PollingDevice):
    def get_device_attributes(self, entity_id: str) -> SensorAttributes:
        return SensorAttributes(STATE=sensor.States.ON, VALUE=23.5)
    
    async def poll_device(self):
        self.update_entity("sensor.device.temp")  # Works!
```

### Not Registering Entity

```python
# ❌ Won't work - entity not registered
class MySensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device, sensor_config):
        super().__init__(...)
        # Forgot to register!

# ✅ Correct - registers during init
class MySensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device, sensor_config):
        super().__init__(...)
        device.register_entity(self.id, self)  # Required!
```

## Migration from Custom Patterns

If you implemented a custom sensor update pattern:

### Before (Custom Pattern)

```python
class MySensor(sensor.Sensor, Entity):
    def refresh_from_device(self):
        attrs = self._device.get_sensor_data(self.sensor_id)
        self.update_attributes(attrs)

class MyDevice(PollingDevice):
    def __init__(self):
        self._sensors = {}
    
    def register_sensor(self, sensor_id, sensor_entity):
        self._sensors[sensor_id] = sensor_entity
    
    async def poll_device(self):
        for sensor_id, entity in self._sensors.items():
            entity.refresh_from_device()
```

### After (Framework Pattern)

```python
class MySensor(sensor.Sensor, Entity):
    def __init__(self, device_config, device, sensor_config):
        super().__init__(...)
        device.register_entity(self.id, self)  # Use framework registry

class MyDevice(PollingDevice):
    def get_device_attributes(self, entity_id: str) -> SensorAttributes:
        sensor_id = entity_id.split('.')[-1]
        return self.get_sensor_data(sensor_id)
    
    async def poll_device(self):
        for sensor_id in self.sensor_ids:
            entity_id = f"sensor.{self.device_id}.{sensor_id}"
            self.update_entity(entity_id)  # Framework handles the rest!
```

Benefits of migration:
- Less boilerplate code
- Framework handles validation
- Consistent with other integrations
- Better error messages
