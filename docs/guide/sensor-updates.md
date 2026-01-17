# Sensor Update Patterns

Sensors are unique among entity types because they're read-only - they don't have command handlers where state updates naturally occur. This guide covers recommended patterns for updating sensor entities from device events.

## Overview

The framework supports sensor updates through:

1. **Direct Pattern** - Store entity references and call `update()` directly (Recommended)
2. **Event-Based Pattern** - Using `DeviceEvents.UPDATE` with entity_id

Both patterns integrate with `get_device_attributes()` for centralized attribute management.

## Pattern 1: Direct Updates (Recommended)

The direct pattern stores entity references in your device class and calls `update()` directly when state changes. This is the most straightforward and Pythonic approach.

### How It Works

1. Store entity references in your device (dict, list, whatever fits your needs)
2. Update internal state
3. Call `entity.update()` directly with your data
4. Framework handles the rest

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
    """Simple sensor entity."""
    
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


class MyDevice(PollingDevice):
    """Device with sensors that updates directly."""
    
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,
            config_manager=config_manager
        )
        # Store sensors however makes sense for your integration
        # Option 1: By sensor_id (natural lookup key)
        self.sensors = {}  # sensor_id -> MySensor instance
        
        # Option 2: By entity_id
        # self.sensors = {}  # entity_id -> MySensor instance
        
        # Option 3: With runtime data
        # self.sensors = {}  # sensor_id -> {"entity": MySensor, "value": x, "unit": y}
    
    async def poll_device(self):
        """Poll device and update all sensors."""
        # Fetch sensor readings from device API
        readings = await self.api.get_sensor_readings()
        
        for sensor_id, reading in readings.items():
            sensor_entity = self.sensors.get(sensor_id)
            if sensor_entity:
                # Update directly - clean and obvious!
                sensor_entity.update(SensorAttributes(
                    STATE=sensor.States.ON,
                    VALUE=reading.value,
                    UNIT=reading.unit
                ))
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

```

### Data Storage Patterns

Choose a data structure that fits your integration:

**Pattern A: Simple value storage**
```python
class MyDevice(PollingDevice):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.sensor_values = {}  # sensor_id -> value
        self.sensors = {}  # sensor_id -> MySensor entity
```

**Pattern B: Rich data with entity reference**
```python
class MyDevice(PollingDevice):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.sensors = {}  # sensor_id -> {"entity": MySensor, "value": x, "last_update": ts}
```

**Pattern C: Dataclass instances**
```python
class MyDevice(PollingDevice):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.sensors = {}  # sensor_id -> MySensor entity
        self.sensor_attrs = {}  # sensor_id -> SensorAttributes()
```

## Pattern 2: Event-Based Updates

The event-based pattern uses `DeviceEvents.UPDATE` event system with an optional `entity_id` parameter to target specific entities.

### How It Works

1. Device emits `DeviceEvents.UPDATE` with `entity_id` and `update` parameters
2. Framework's `on_device_update()` handler receives the event
3. Entity state is updated via framework routing
4. Works with both dataclass and dict updates

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

- Event-driven architecture with loose coupling
- Async-friendly - works naturally with WebSocket/async code
- Dataclass and dict support
- No need to store entity references

## Choosing a Pattern

**Use Direct Updates When:**

- You want the simplest, most straightforward code
- Entity references naturally fit your data model
- Debugging with direct calls is easier

**Use Event-Based When:**

- You prefer event-driven architecture
- You're already using events for other updates
- Multiple entities update from single device message

## Complete Working Example

Here's a complete example showing the direct pattern:

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

# Device class
class MyDevice(PollingDevice):
    def __init__(self, device_config, config_manager=None):
        super().__init__(
            device_config,
            poll_interval=30,
            config_manager=config_manager
        )
        # Store sensors by sensor_id for easy lookup
        self.sensors = {}  # sensor_id -> MySensor entity
    
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
    
    async def establish_connection(self):
        """Initial connection setup."""
        pass  # Your connection logic
    
    async def poll_device(self):
        """Poll device and update sensors."""
        # Simulate getting sensor readings
        readings = {
            'temp': {'value': 23.5, 'unit': '°C'},
            'humidity': {'value': 65, 'unit': '%'},
            'pressure': {'value': 1013, 'unit': 'hPa'}
        }
        
        for sensor_id, reading in readings.items():
            sensor_entity = self.sensors.get(sensor_id)
            if sensor_entity:
                # Direct update - simple and clean!
                sensor_entity.update(SensorAttributes(
                    STATE=sensor.States.ON,
                    VALUE=reading['value'],
                    UNIT=reading['unit']
                ))

# Driver factory function
def create_sensor_entities(device_config, device):
    """Factory function to create all sensor entities."""
    entities = []
    for sensor_config in SENSORS:
        entity = MySensor(device_config, device, sensor_config)
        # Store reference in device for updates
        device.sensors[sensor_config.id] = entity
        entities.append(entity)
    return entities

# Driver setup
driver = BaseIntegrationDriver(
    device_class=MyDevice,
    entity_classes=[create_sensor_entities]
)
```

## Migration from Custom Patterns

If you have existing sensor code, here's how to migrate:

**Before (Custom Pattern):**

```python
class MyDevice(PollingDevice):
    async def poll_device(self):
        for sensor in self.sensors:
            sensor.current_value = await self.read_sensor(sensor.id)
            # Custom update logic
            self.api.configured_entities.update_attributes(
                sensor.entity_id,
                {
                    sensor.Attributes.STATE: sensor.States.ON,
                    sensor.Attributes.VALUE: sensor.current_value
                }
            )
```

**After (Direct Pattern):**

```python
class MyDevice(PollingDevice):
    async def poll_device(self):
        for sensor_id, sensor_entity in self.sensors.items():
            value = await self.read_sensor(sensor_id)
            # Framework handles everything!
            sensor_entity.update(SensorAttributes(
                STATE=sensor.States.ON,
                VALUE=value
            ))
```

## Best Practices

1. **Choose your data structure** - Use whatever makes sense for your integration (dict by sensor_id, dict by entity_id, list, etc.)
2. **Store entity references** - Keep references to your sensor entities for easy updates
3. **Use dataclasses** - SensorAttributes provides type safety and automatic None filtering
4. **Keep it simple** - Direct calls to `entity.update()` are the most straightforward

## Common Patterns

### Pattern: Sensors with Different Types

```python
class MyDevice(PollingDevice):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.temperature_sensors = {}  # sensor_id -> MySensor
        self.binary_sensors = {}  # sensor_id -> MyBinarySensor
```

### Pattern: Sensors with Metadata

```python
class MyDevice(PollingDevice):
    def __init__(self, device_config):
        super().__init__(device_config)
        self.sensors = {}  # sensor_id -> {
                           #   "entity": MySensor,
                           #   "last_update": timestamp,
                           #   "native_id": device_native_id
                           # }
```

### Pattern: Dynamic Sensor Discovery

```python
class MyDevice(PollingDevice):
    async def establish_connection(self):
        # Discover sensors from device
        discovered = await self.device_api.discover_sensors()
        for sensor_info in discovered:
            # Sensors will be created by driver during entity registration
            pass
    
    async def poll_device(self):
        # Update only discovered sensors
        for sensor_id, sensor_entity in self.sensors.items():
            value = await self.read_sensor(sensor_id)
            sensor_entity.update(SensorAttributes(
                STATE=sensor.States.ON,
                VALUE=value
            ))
```

## Troubleshooting

### Entity Update Not Working

Check that:

1. You're storing the entity reference correctly
2. Entity inherits from `Entity` ABC
3. You're calling `entity.update()` with proper attributes
4. Entity `_api` is set by the framework (automatic)

### Type Errors with Dataclasses

Make sure you:

1. Import the correct dataclass (`from ucapi_framework import SensorAttributes`)
2. Use `None` for optional fields, not omitting them
3. Check attribute names match ucapi enum names (STATE, VALUE, UNIT)

### Performance Issues

If updating many sensors is slow:

- Batch updates when possible
- Use event-based pattern for async updates
- Consider update frequency - not all sensors need real-time updates

