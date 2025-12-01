# Configuration Management

Configuration management in the framework is built around dataclasses and provides automatic JSON serialization, CRUD operations, and backup/restore functionality.

## Defining Configuration

Configuration is just a dataclass:

```python
from dataclasses import dataclass

@dataclass
class MyDeviceConfig:
    """Device configuration."""
    identifier: str
    name: str
    host: str
    port: int = 8080
    api_key: str = ""
```

The framework automatically handles:

- ✅ JSON serialization/deserialization
- ✅ Type validation
- ✅ Default values
- ✅ Nested dataclasses

## Creating a Config Manager

```python
from ucapi_framework import BaseConfigManager

config = BaseConfigManager[MyDeviceConfig](
    data_path="./config",
    add_handler=driver.on_device_added,
    remove_handler=driver.on_device_removed,
)
```

## CRUD Operations

### Add or Update

```python
device_config = MyDeviceConfig(
    identifier="device_1",
    name="My Device",
    host="192.168.1.100",
)

config.add_or_update(device_config)
```

### Get

```python
device = config.get("device_1")
if device:
    print(f"Found: {device.name}")
```

### Remove

```python
if config.remove("device_1"):
    print("Device removed")
```

### Iterate All

```python
for device in config.all():
    print(f"Device: {device.name} at {device.host}")
```

### Check Existence

```python
if config.contains("device_1"):
    print("Device exists")
```

### Clear All

```python
config.clear()  # Removes all devices
```

## Persistence

Configuration is automatically persisted to disk:

- **Auto-save** on add/update/remove
- **Auto-load** on initialization
- **Atomic writes** prevent corruption
- **Backup on changes** (optional)

## Backup & Restore

### Export Configuration

```python
json_backup = config.get_backup_json()
# Save to file or send to user
```

### Import Configuration

```python
success = config.restore_from_backup_json(json_backup)
if success:
    print("Configuration restored")
```

## Configuration Callbacks

The config manager can notify your driver when devices are added or removed:

```python
def on_device_added(device_config: MyDeviceConfig) -> None:
    """Called when device is added."""
    print(f"Device added: {device_config.name}")
    driver.add_configured_device(device_config)

def on_device_removed(device_config: MyDeviceConfig | None) -> None:
    """Called when device is removed."""
    if device_config is None:
        print("All devices removed")
        driver.clear_devices()
    else:
        print(f"Device removed: {device_config.name}")
        driver.remove_device(driver.get_device_id(device_config))

config = BaseConfigManager[MyDeviceConfig](
    data_path="./config",
    add_handler=on_device_added,
    remove_handler=on_device_removed,
)
```

## Dynamic Configuration Updates

Devices can update their own configuration at runtime:

```python
class MyDevice(StatelessHTTPDevice):
    async def authenticate(self) -> None:
        """Authenticate and update token."""
        new_token = await self._get_auth_token()
        
        # Update config with new token
        self.update_config(api_token=new_token)
        # Changes are automatically persisted!
```

## Type Safety

The config manager is fully typed:

```python
config = BaseConfigManager[MyDeviceConfig](...)

# IDE knows this returns MyDeviceConfig | None
device = config.get("device_1")

# Type checking works
if device:
    print(device.host)  # ✅ IDE autocomplete works
    print(device.invalid)  # ❌ Type error
```

## Migration Support

The framework supports configuration migration:

```python
class MyConfigManager(BaseConfigManager[MyDeviceConfig]):
    def migration_required(self) -> bool:
        """Check if migration is needed."""
        # Check for old config format
        return os.path.exists("old_config.json")
    
    async def migrate(self) -> bool:
        """Migrate from old format."""
        # Load old config
        with open("old_config.json") as f:
            old_data = json.load(f)
        
        # Convert to new format
        for item in old_data:
            new_config = MyDeviceConfig(
                identifier=item["id"],
                name=item["device_name"],
                host=item["ip"],
            )
            self.add_or_update(new_config)
        
        # Clean up old file
        os.remove("old_config.json")
        return True
```

## Best Practices

1. **Use dataclasses** - They're simple, type-safe, and work great with the framework
2. **Provide defaults** - Use default values for optional fields
3. **Keep it flat** - Avoid deep nesting when possible
4. **Use type hints** - Full type safety means fewer bugs
5. **Validate on load** - Use `__post_init__` for validation if needed

```python
@dataclass
class MyDeviceConfig:
    identifier: str
    name: str
    host: str
    port: int = 8080
    
    def __post_init__(self):
        """Validate configuration."""
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid port: {self.port}")
        
        # Normalize host
        self.host = self.host.strip()
```

See the [API Reference](../api/config.md) for complete documentation.
