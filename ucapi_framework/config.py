"""
Base device configuration manager for Unfolded Circle Remote integrations.

Provides reusable device configuration storage and management.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import dataclasses
import json
import logging
import os
from abc import ABC
from typing import Any, Callable, Generic, Iterator, TypeVar, get_args, get_origin

_LOG = logging.getLogger(__name__)

_CFG_FILENAME = "config.json"

# Type variable for device configuration
DeviceT = TypeVar("DeviceT")


def get_config_path(default_path: str) -> str:
    """
    Get the appropriate configuration path for the current environment.

    Handles three deployment scenarios:
    1. **Remote Two (production)**: Uses the default path provided by driver.api.config_dir_path
    2. **Docker container**: Uses UC_CONFIG_HOME environment variable (typically /config)
    3. **Local development**: Uses {cwd}/config/ as absolute path

    The detection logic:
    - If UC_CONFIG_HOME is set → use it (Docker environment)
    - If driver.json exists in current directory → local development
    - Otherwise → production (Remote Two)

    :param default_path: Default path from driver.api.config_dir_path
    :return: Configuration directory path (always absolute)

    Example usage::

        driver = MyIntegrationDriver(device_class=MyDevice, ...)

        config_path = get_config_path(driver.api.config_dir_path)

        driver.config_manager = BaseConfigManager(
            config_path,
            driver.on_device_added,
            driver.on_device_removed,
            config_class=MyDeviceConfig,
        )
    """
    # Check for Docker environment (UC_CONFIG_HOME is set in Dockerfile)
    if docker_config_home := os.getenv("UC_CONFIG_HOME"):
        _LOG.debug(
            "Docker environment detected, using UC_CONFIG_HOME: %s", docker_config_home
        )
        return docker_config_home

    # Auto-detect local development: driver.json exists in current directory
    if os.path.exists("driver.json"):
        # Use absolute path based on current working directory
        local_path = os.path.abspath("config")
        _LOG.debug("Local development detected, using config path: %s", local_path)
        return local_path

    # Production environment (Remote Two) - use default path from API
    _LOG.debug("Production environment, using default path: %s", default_path)
    return default_path


class _EnhancedJSONEncoder(json.JSONEncoder):
    """
    Custom JSON encoder with support for dataclass serialization.

    The standard json.JSONEncoder doesn't know how to serialize dataclasses.
    This encoder extends it to automatically convert dataclass instances to
    dictionaries using dataclasses.asdict(), enabling seamless JSON persistence
    of device configurations.

    This is preferred over manual dict conversion because:
    - Automatic serialization of nested dataclasses
    - Type safety maintained through dataclass definitions
    - No need to manually implement to_dict() on every config class
    """

    def default(self, o: Any) -> Any:
        """
        Override default serialization for unsupported types.

        :param o: Object to serialize
        :return: JSON-serializable representation
        """
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class BaseConfigManager(ABC, Generic[DeviceT]):
    """
    Base class for device configuration management.

    Handles:
    - Loading/storing configuration from/to JSON
    - CRUD operations (add, update, remove, get)
    - Configuration callbacks
    - Optional backup/restore support

    Type Parameters:
        DeviceT: The device configuration dataclass type
    """

    def __init__(
        self,
        data_path: str,
        add_handler: Callable[[DeviceT], None] | None = None,
        remove_handler: Callable[[DeviceT | None], None] | None = None,
        config_class: type[DeviceT] | None = None,
    ):
        """
        Create a configuration instance.

        :param data_path: Configuration path for the configuration file
        :param add_handler: Optional callback when device is added
        :param remove_handler: Optional callback when device is removed
        :param config_class: The configuration dataclass type (optional, auto-detected from type hints if not provided)
        """
        self._data_path: str = data_path
        self._cfg_file_path: str = os.path.join(data_path, _CFG_FILENAME)
        self._config: list[DeviceT] = []
        self._add_handler = add_handler
        self._remove_handler = remove_handler
        self._config_class = config_class
        self.load()

    @property
    def data_path(self) -> str:
        """Return the configuration path."""
        return self._data_path

    def all(self) -> Iterator[DeviceT]:
        """Get an iterator for all device configurations."""
        return iter(self._config)

    def contains(self, device_id: str) -> bool:
        """
        Check if there's a device with the given device identifier.

        :param device_id: Device identifier
        :return: True if device exists
        """
        return any(self.get_device_id(item) == device_id for item in self._config)

    def add_or_update(self, device: DeviceT) -> None:
        """
        Add a new device or update if it already exists.

        :param device: Device configuration to add or update
        """
        if not self.update(device):
            self._config.append(device)
            self.store()
            if self._add_handler is not None:
                self._add_handler(device)

    def get(self, device_id: str) -> DeviceT | None:
        """
        Get device configuration for given identifier.

        :param device_id: Device identifier
        :return: Device configuration or None
        """
        for item in self._config:
            if self.get_device_id(item) == device_id:
                # Return a copy
                return dataclasses.replace(item)
        return None

    def update(self, device: DeviceT) -> bool:
        """
        Update a configured device and persist configuration.

        :param device: Device configuration with updated values
        :return: True if device was updated, False if not found
        """
        device_id = self.get_device_id(device)
        for item in self._config:
            if self.get_device_id(item) == device_id:
                # Update the item in place
                self.update_device_fields(item, device)
                return self.store()
        return False

    def remove(self, device_id: str) -> bool:
        """
        Remove the given device configuration.

        :param device_id: Device identifier
        :return: True if device was removed
        """
        device = self.get(device_id)
        if device is None:
            return False
        try:
            # Remove the original object from config
            for item in self._config:
                if self.get_device_id(item) == device_id:
                    self._config.remove(item)
                    break

            if self._remove_handler is not None:
                self._remove_handler(device)
            self.store()
            return True
        except ValueError:
            pass
        return False

    def clear(self) -> None:
        """Remove all configuration."""
        self._config = []

        if os.path.exists(self._cfg_file_path):
            os.remove(self._cfg_file_path)

        if self._remove_handler is not None:
            self._remove_handler(None)

    def store(self) -> bool:
        """
        Store the configuration file.

        :return: True if the configuration could be saved
        """
        try:
            # Ensure directory exists
            os.makedirs(self._data_path, exist_ok=True)

            with open(self._cfg_file_path, "w+", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, cls=_EnhancedJSONEncoder)
            return True
        except OSError as err:
            _LOG.error("Cannot write the config file: %s", err)
            return False

    def load(self) -> bool:
        """
        Load the configuration from file.

        :return: True if the configuration could be loaded
        """
        if not os.path.exists(self._cfg_file_path):
            _LOG.info(
                "Configuration file not found, starting with empty configuration: %s",
                self._cfg_file_path,
            )
            return False

        try:
            with open(self._cfg_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for item in data:
                device = self.deserialize_device(item)
                if device:
                    self._config.append(device)

            _LOG.info("Loaded %d device(s) from configuration", len(self._config))
            return True
        except PermissionError as err:
            _LOG.error(
                "Permission denied reading config file %s: %s", self._cfg_file_path, err
            )
        except OSError as err:
            _LOG.error("Cannot read the config file %s: %s", self._cfg_file_path, err)
        except json.JSONDecodeError as err:
            _LOG.error("Invalid JSON in config file %s: %s", self._cfg_file_path, err)
        except (AttributeError, ValueError, TypeError) as err:
            _LOG.error("Invalid config file format in %s: %s", self._cfg_file_path, err)

        return False

    def get_device_id(self, device: DeviceT) -> str:
        """
        Extract device identifier from device configuration.

        Default implementation: tries common attribute names (identifier, id, device_id).
        Override this if your device config uses a different attribute name.

        :param device: Device configuration
        :return: Device identifier
        :raises AttributeError: If no valid ID attribute is found
        """
        for attr in ("identifier", "id", "device_id"):
            if hasattr(device, attr):
                value = getattr(device, attr)
                if value:
                    return str(value)

        raise AttributeError(
            f"Device config {type(device).__name__} has no 'identifier', 'id', or 'device_id' attribute. "
            f"Override get_device_id() to specify which attribute to use."
        )

    def get_backup_json(self) -> str:
        """
        Get configuration as JSON string for backup.

        :return: JSON string representation of configuration
        """
        try:
            return json.dumps(
                self._config, ensure_ascii=False, indent=2, cls=_EnhancedJSONEncoder
            )
        except (TypeError, ValueError) as err:
            _LOG.error("Failed to serialize configuration: %s", err)
            return "[]"

    def restore_from_backup_json(self, backup_json: str) -> bool:
        """
        Restore configuration from JSON string.

        :param backup_json: JSON string containing configuration backup
        :return: True if restore was successful
        """
        try:
            data = json.loads(backup_json)

            if not isinstance(data, list):
                _LOG.error(
                    "Invalid backup format: expected list, got %s", type(data).__name__
                )
                return False

            # Deserialize and validate all devices first
            new_config: list[DeviceT] = []
            for item in data:
                if not isinstance(item, dict):
                    _LOG.warning("Skipping invalid device entry: %s", item)
                    continue

                device = self.deserialize_device(item)
                if device:
                    new_config.append(device)
                else:
                    _LOG.warning("Failed to deserialize device: %s", item)

            if not new_config:
                _LOG.error("No valid devices found in backup")
                return False

            # Replace configuration and persist
            self._config = new_config
            if self.store():
                _LOG.info(
                    "Successfully restored %d device(s) from backup", len(self._config)
                )

                # Notify via add handler for each device
                if self._add_handler is not None:
                    for device in self._config:
                        self._add_handler(device)

                return True
            else:
                _LOG.error("Failed to persist restored configuration")
                return False

        except json.JSONDecodeError as err:
            _LOG.error("Invalid JSON in backup: %s", err)
            return False
        except (AttributeError, ValueError, TypeError) as err:
            _LOG.error("Failed to restore configuration: %s", err)
            return False

    # ========================================================================
    # Migration Support
    # ========================================================================

    def migration_required(self) -> bool:
        """
        Check if configuration migration is required.

        Override this method to implement migration detection logic.

        :return: True if migration is required
        """
        return False

    async def migrate(self) -> bool:
        """
        Migrate configuration if required.

        Override this method to implement migration logic.

        :return: True if migration was successful
        """
        return True

    # ========================================================================
    # Helper Methods
    # ========================================================================

    @staticmethod
    def _deserialize_field(field_value: Any, field_type: type) -> Any:
        """
        Recursively deserialize a field value based on its type annotation.

        Handles:
        - Dataclasses (single instances)
        - Lists of dataclasses (e.g., list[LutronLightInfo])
        - Primitive types (passed through)

        :param field_value: The value to deserialize
        :param field_type: The target type annotation
        :return: Deserialized value
        """
        # Handle None values
        if field_value is None:
            return None

        # Get the origin type (e.g., list from list[X])
        origin = get_origin(field_type)

        # Handle list types (e.g., list[SomeDataclass])
        if origin is list:
            args = get_args(field_type)
            if args and isinstance(field_value, list):
                item_type = args[0]
                # If list items are dataclasses, deserialize each one
                if dataclasses.is_dataclass(item_type):
                    return [
                        item_type(**item) if isinstance(item, dict) else item
                        for item in field_value
                    ]
            # Not a list of dataclasses, return as-is
            return field_value

        # Handle single dataclass instances
        if dataclasses.is_dataclass(field_type) and isinstance(field_value, dict):
            return field_type(**field_value)

        # For all other types (str, int, bool, etc.), return as-is
        return field_value

    def deserialize_device_auto(
        self, data: dict, device_class: type[DeviceT]
    ) -> DeviceT | None:
        """
        Automatically deserialize device configuration with nested dataclass support.

        This helper method automatically handles:
        - Nested dataclasses
        - Lists of dataclasses (e.g., list[LutronLightInfo])
        - Primitive types

        Use this in your deserialize_device() implementation:

        Example:
            def deserialize_device(self, data: dict) -> MyDeviceConfig | None:
                return self.deserialize_device_auto(data, MyDeviceConfig)

        For backward compatibility or custom logic, override specific fields:

        Example:
            def deserialize_device(self, data: dict) -> MyDeviceConfig | None:
                # Let auto-deserialize handle nested dataclasses
                device = self.deserialize_device_auto(data, MyDeviceConfig)
                if device:
                    # Add custom migration logic
                    if not hasattr(device, 'new_field'):
                        device.new_field = "default_value"
                return device

        :param data: Dictionary with device data
        :param device_class: The device dataclass type
        :return: Device configuration or None if invalid
        """
        try:
            # Get all fields from the dataclass
            field_dict = {}
            for field in dataclasses.fields(device_class):
                field_name = field.name
                if field_name in data:
                    # Deserialize the field value based on its type
                    field_dict[field_name] = self._deserialize_field(
                        data[field_name], field.type
                    )

            # Create the device instance
            return device_class(**field_dict)

        except (TypeError, ValueError) as err:
            _LOG.error("Failed to deserialize device: %s", err)
            return None

    # ========================================================================
    # Deserialization (Can be overridden for custom logic)
    # ========================================================================

    def deserialize_device(self, data: dict) -> DeviceT | None:
        """
        Deserialize device configuration from dictionary.

        **DEFAULT IMPLEMENTATION**: Uses deserialize_device_auto() with the config class
        provided during initialization or inferred from the Generic type parameter.

        Most integrations can use the default implementation without overriding:

            class MyConfigManager(BaseConfigManager[MyDeviceConfig]):
                pass  # No override needed!

        Or explicitly pass the config class:

            manager = MyConfigManager(data_path, config_class=MyDeviceConfig)

        **Override only if** you need custom logic:

            def deserialize_device(self, data: dict) -> MyDeviceConfig | None:
                # Auto-deserialize handles nested dataclasses
                device = self.deserialize_device_auto(data, MyDeviceConfig)
                if device:
                    # Custom migration logic
                    if 'old_field' in data:
                        device.new_field = migrate_value(data['old_field'])
                    # Custom post-processing
                    for light in device.lights:
                        light.name = light.name.replace("_", " ")
                return device

        :param data: Dictionary with device data
        :return: Device configuration or None if invalid
        """
        # Get config class if not provided during init
        if self._config_class is None:
            # Try to infer from Generic type parameter
            config_class = self._infer_config_class()
            if config_class is None:
                raise TypeError(
                    f"{type(self).__name__} must either:\n"
                    f"1. Pass config_class to __init__: MyManager(path, config_class=MyConfig)\n"
                    f"2. Override deserialize_device() with custom logic\n"
                    f"3. Use proper Generic syntax: class MyManager(BaseConfigManager[MyConfig])"
                )
            self._config_class = config_class

        # Use auto-deserialize with the config class
        return self.deserialize_device_auto(data, self._config_class)

    def _infer_config_class(self) -> type[DeviceT] | None:
        """
        Infer config class from Generic type parameter.

        :return: Config class or None if cannot be inferred
        """
        # Get the class's __orig_bases__ which contains Generic[DeviceT] information
        for base in getattr(type(self), "__orig_bases__", []):
            origin = get_origin(base)
            if origin is BaseConfigManager:
                args = get_args(base)
                if args:
                    return args[0]
        return None

    # ========================================================================
    # Optional Override Methods
    # ========================================================================

    def update_device_fields(self, existing: DeviceT, updated: DeviceT) -> None:
        """
        Update fields of existing device with values from updated device.

        Default implementation updates all fields. Override for custom behavior.

        :param existing: Existing device configuration (will be modified)
        :param updated: Updated device configuration (source of new values)
        """
        # Default: update all dataclass fields
        for field in dataclasses.fields(existing):
            setattr(existing, field.name, getattr(updated, field.name))
