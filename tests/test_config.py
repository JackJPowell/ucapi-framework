"""Tests for BaseDeviceManager configuration management."""

import json
import os
from dataclasses import dataclass

import pytest

from ucapi_framework.config import BaseDeviceManager


@dataclass
class DeviceConfig:
    """Test device configuration dataclass."""

    identifier: str
    name: str
    address: str
    port: int = 8080


class ConcreteDeviceManager(BaseDeviceManager[DeviceConfig]):
    """Concrete implementation of BaseDeviceManager for testing."""

    def deserialize_device(self, data: dict) -> DeviceConfig | None:
        """Deserialize device configuration from dictionary."""
        try:
            # Return None for invalid entries (missing required fields)
            identifier = data.get("identifier", "")
            name = data.get("name", "")
            address = data.get("address", "")

            # Skip if missing required fields
            if not identifier or not name or not address:
                return None

            return DeviceConfig(
                identifier=identifier,
                name=name,
                address=address,
                port=data.get("port", 8080),
            )
        except (KeyError, TypeError, ValueError):
            return None


class TestBaseDeviceManager:
    """Test suite for BaseDeviceManager."""

    def test_init_creates_empty_config(self, temp_config_dir):
        """Test that initialization creates an empty configuration."""
        manager = ConcreteDeviceManager(temp_config_dir)
        assert list(manager.all()) == []

    def test_init_with_handlers(self, temp_config_dir):
        """Test initialization with add/remove handlers."""
        add_called = []
        remove_called = []

        def add_handler(device):
            add_called.append(device)

        def remove_handler(device):
            remove_called.append(device)

        manager = ConcreteDeviceManager(
            temp_config_dir, add_handler=add_handler, remove_handler=remove_handler
        )
        assert manager is not None

    def test_add_device(self, temp_config_dir):
        """Test adding a device."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")

        manager.add_or_update(device)

        assert manager.contains("dev1")
        assert len(list(manager.all())) == 1

    def test_add_device_triggers_handler(self, temp_config_dir):
        """Test that adding a device triggers the add handler."""
        added_devices = []

        def add_handler(device):
            added_devices.append(device)

        manager = ConcreteDeviceManager(temp_config_dir, add_handler=add_handler)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")

        manager.add_or_update(device)

        assert len(added_devices) == 1
        assert added_devices[0].identifier == "dev1"

    def test_update_existing_device(self, temp_config_dir):
        """Test updating an existing device."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1", 8080)
        manager.add_or_update(device)

        # Update the device
        updated_device = DeviceConfig("dev1", "Device 1 Updated", "192.168.1.2", 9090)
        manager.add_or_update(updated_device)

        # Should still have only one device
        assert len(list(manager.all())) == 1

        # Device should be updated
        retrieved = manager.get("dev1")
        assert retrieved.name == "Device 1 Updated"
        assert retrieved.address == "192.168.1.2"
        assert retrieved.port == 9090

    def test_get_device(self, temp_config_dir):
        """Test retrieving a device by ID."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        retrieved = manager.get("dev1")

        assert retrieved is not None
        assert retrieved.identifier == "dev1"
        assert retrieved.name == "Device 1"

    def test_get_nonexistent_device(self, temp_config_dir):
        """Test retrieving a device that doesn't exist."""
        manager = ConcreteDeviceManager(temp_config_dir)

        retrieved = manager.get("nonexistent")

        assert retrieved is None

    def test_get_returns_copy(self, temp_config_dir):
        """Test that get() returns a copy of the device."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        retrieved = manager.get("dev1")
        retrieved.name = "Modified"

        # Original should not be modified
        original = manager.get("dev1")
        assert original.name == "Device 1"

    def test_contains(self, temp_config_dir):
        """Test checking if a device exists."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        assert manager.contains("dev1")
        assert not manager.contains("nonexistent")

    def test_remove_device(self, temp_config_dir):
        """Test removing a device."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        result = manager.remove("dev1")

        assert result is True
        assert not manager.contains("dev1")
        assert len(list(manager.all())) == 0

    def test_remove_nonexistent_device(self, temp_config_dir):
        """Test removing a device that doesn't exist."""
        manager = ConcreteDeviceManager(temp_config_dir)

        result = manager.remove("nonexistent")

        assert result is False

    def test_remove_triggers_handler(self, temp_config_dir):
        """Test that removing a device triggers the remove handler."""
        removed_devices = []

        def remove_handler(device):
            removed_devices.append(device)

        manager = ConcreteDeviceManager(temp_config_dir, remove_handler=remove_handler)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        manager.remove("dev1")

        assert len(removed_devices) == 1
        assert removed_devices[0].identifier == "dev1"

    def test_clear_devices(self, temp_config_dir):
        """Test clearing all devices."""
        manager = ConcreteDeviceManager(temp_config_dir)
        manager.add_or_update(DeviceConfig("dev1", "Device 1", "192.168.1.1"))
        manager.add_or_update(DeviceConfig("dev2", "Device 2", "192.168.1.2"))

        manager.clear()

        assert len(list(manager.all())) == 0
        assert not os.path.exists(os.path.join(temp_config_dir, "config.json"))

    def test_clear_triggers_handler_with_none(self, temp_config_dir):
        """Test that clearing triggers the remove handler with None."""
        removed_devices = []

        def remove_handler(device):
            removed_devices.append(device)

        manager = ConcreteDeviceManager(temp_config_dir, remove_handler=remove_handler)
        manager.add_or_update(DeviceConfig("dev1", "Device 1", "192.168.1.1"))

        manager.clear()

        assert len(removed_devices) == 1
        assert removed_devices[0] is None

    def test_store_and_load(self, temp_config_dir):
        """Test storing and loading configuration."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device1 = DeviceConfig("dev1", "Device 1", "192.168.1.1", 8080)
        device2 = DeviceConfig("dev2", "Device 2", "192.168.1.2", 9090)

        manager.add_or_update(device1)
        manager.add_or_update(device2)

        # Create new manager instance to load from file
        manager2 = ConcreteDeviceManager(temp_config_dir)

        assert manager2.contains("dev1")
        assert manager2.contains("dev2")
        assert len(list(manager2.all())) == 2

        dev1 = manager2.get("dev1")
        assert dev1.name == "Device 1"
        assert dev1.port == 8080

    def test_all_iterator(self, temp_config_dir):
        """Test iterating over all devices."""
        manager = ConcreteDeviceManager(temp_config_dir)
        manager.add_or_update(DeviceConfig("dev1", "Device 1", "192.168.1.1"))
        manager.add_or_update(DeviceConfig("dev2", "Device 2", "192.168.1.2"))
        manager.add_or_update(DeviceConfig("dev3", "Device 3", "192.168.1.3"))

        devices = list(manager.all())

        assert len(devices) == 3
        identifiers = {d.identifier for d in devices}
        assert identifiers == {"dev1", "dev2", "dev3"}

    def test_get_device_id_default(self, temp_config_dir):
        """Test default get_device_id implementation."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")

        device_id = manager.get_device_id(device)

        assert device_id == "dev1"

    def test_get_device_id_alternative_attributes(self, temp_config_dir):
        """Test get_device_id with alternative attribute names."""

        @dataclass
        class DeviceWithId:
            id: str
            name: str

        @dataclass
        class DeviceWithDeviceId:
            device_id: str
            name: str

        class TestManager(BaseDeviceManager):
            def deserialize_device(self, data):
                return None

        manager = TestManager(temp_config_dir)

        dev1 = DeviceWithId("id-123", "Test")
        assert manager.get_device_id(dev1) == "id-123"

        dev2 = DeviceWithDeviceId("device-456", "Test")
        assert manager.get_device_id(dev2) == "device-456"

    def test_get_device_id_raises_on_missing_attribute(self, temp_config_dir):
        """Test that get_device_id raises error when no valid attribute exists."""

        @dataclass
        class DeviceWithoutId:
            name: str
            address: str

        class TestManager(BaseDeviceManager):
            def deserialize_device(self, data):
                return None

        manager = TestManager(temp_config_dir)
        device = DeviceWithoutId("Test", "192.168.1.1")

        with pytest.raises(
            AttributeError, match="no 'identifier', 'id', or 'device_id'"
        ):
            manager.get_device_id(device)

    def test_backup_json(self, temp_config_dir):
        """Test getting configuration as JSON backup."""
        manager = ConcreteDeviceManager(temp_config_dir)
        manager.add_or_update(DeviceConfig("dev1", "Device 1", "192.168.1.1", 8080))
        manager.add_or_update(DeviceConfig("dev2", "Device 2", "192.168.1.2", 9090))

        backup_json = manager.get_backup_json()

        # Parse and verify
        backup_data = json.loads(backup_json)
        assert len(backup_data) == 2
        assert backup_data[0]["identifier"] == "dev1"
        assert backup_data[1]["identifier"] == "dev2"

    def test_restore_from_backup_json(self, temp_config_dir):
        """Test restoring configuration from JSON backup."""
        # Create initial config
        manager1 = ConcreteDeviceManager(temp_config_dir)
        manager1.add_or_update(DeviceConfig("dev1", "Device 1", "192.168.1.1", 8080))
        manager1.add_or_update(DeviceConfig("dev2", "Device 2", "192.168.1.2", 9090))

        backup_json = manager1.get_backup_json()

        # Clear and restore
        manager1.clear()
        assert len(list(manager1.all())) == 0

        result = manager1.restore_from_backup_json(backup_json)

        assert result is True
        assert len(list(manager1.all())) == 2
        assert manager1.contains("dev1")
        assert manager1.contains("dev2")

    def test_restore_from_invalid_json(self, temp_config_dir):
        """Test restoring from invalid JSON."""
        manager = ConcreteDeviceManager(temp_config_dir)

        result = manager.restore_from_backup_json("invalid json {")

        assert result is False

    def test_restore_from_invalid_format(self, temp_config_dir):
        """Test restoring from JSON with invalid format."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Not a list
        result = manager.restore_from_backup_json('{"identifier": "dev1"}')

        assert result is False

    def test_restore_triggers_add_handlers(self, temp_config_dir):
        """Test that restore triggers add handlers for each device."""
        added_devices = []

        def add_handler(device):
            added_devices.append(device)

        manager = ConcreteDeviceManager(temp_config_dir, add_handler=add_handler)
        backup_json = json.dumps(
            [
                {
                    "identifier": "dev1",
                    "name": "Device 1",
                    "address": "192.168.1.1",
                    "port": 8080,
                },
                {
                    "identifier": "dev2",
                    "name": "Device 2",
                    "address": "192.168.1.2",
                    "port": 9090,
                },
            ]
        )

        manager.restore_from_backup_json(backup_json)

        assert len(added_devices) == 2

    def test_load_nonexistent_file(self, temp_config_dir):
        """Test loading when config file doesn't exist."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Should not raise, just return False
        assert len(list(manager.all())) == 0

    def test_load_invalid_json(self, temp_config_dir):
        """Test loading invalid JSON file."""
        config_file = os.path.join(temp_config_dir, "config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("invalid json {")

        manager = ConcreteDeviceManager(temp_config_dir)

        # Should handle gracefully
        assert len(list(manager.all())) == 0

    def test_load_skips_invalid_devices(self, temp_config_dir):
        """Test that loading skips invalid device entries."""
        config_file = os.path.join(temp_config_dir, "config.json")
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "identifier": "dev1",
                        "name": "Device 1",
                        "address": "192.168.1.1",
                    },
                    {"invalid": "entry"},  # Missing required fields
                    {
                        "identifier": "dev3",
                        "name": "Device 3",
                        "address": "192.168.1.3",
                    },
                ],
                f,
            )

        manager = ConcreteDeviceManager(temp_config_dir)

        # Should load valid devices only
        assert len(list(manager.all())) == 2
        assert manager.contains("dev1")
        assert manager.contains("dev3")

    def test_data_path_property(self, temp_config_dir):
        """Test data_path property."""
        manager = ConcreteDeviceManager(temp_config_dir)

        assert manager.data_path == temp_config_dir

    def test_concurrent_add_and_get(self, temp_config_dir):
        """Test thread-safe add and get operations."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Add multiple devices
        for i in range(10):
            device = DeviceConfig(f"dev{i}", f"Device {i}", f"192.168.1.{i}")
            manager.add_or_update(device)

        # Verify all were added
        assert len(list(manager.all())) == 10

        # Verify we can retrieve all
        for i in range(10):
            device = manager.get(f"dev{i}")
            assert device is not None
            assert device.name == f"Device {i}"

    def test_update_device_fields_default(self, temp_config_dir):
        """Test default update_device_fields implementation."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1", 8080)
        manager.add_or_update(device)

        # Update with new values
        updated = DeviceConfig("dev1", "Updated Device", "192.168.1.2", 9090)
        manager.update(updated)

        retrieved = manager.get("dev1")
        assert retrieved.name == "Updated Device"
        assert retrieved.address == "192.168.1.2"
        assert retrieved.port == 9090

    def test_migration_methods(self, temp_config_dir):
        """Test migration support methods."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Default implementations
        assert manager.migration_required() is False

        # Test async migrate method
        import asyncio

        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(manager.migrate())
        loop.close()

        assert result is True

    def test_enhanced_json_encoder(self):
        """Test the EnhancedJSONEncoder handles non-dataclass objects."""
        from ucapi_framework.config import _EnhancedJSONEncoder

        # Test with regular dict (should use default behavior)
        regular_obj = {"key": "value"}
        encoded = json.dumps(regular_obj, cls=_EnhancedJSONEncoder)
        assert encoded == '{"key": "value"}'

        # Test with dataclass
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        encoded = json.dumps(device, cls=_EnhancedJSONEncoder)
        assert "dev1" in encoded
        assert "Device 1" in encoded

    def test_remove_nonexistent_returns_false(self, temp_config_dir):
        """Test that removing nonexistent device returns False."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Remove existing device - should return True
        assert manager.remove("dev1") is True

        # Try to remove same device again - should return False
        assert manager.remove("dev1") is False

    def test_load_handles_file_errors(self, temp_config_dir):
        """Test load method handles file permission errors gracefully."""
        import stat

        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Make file read-only to trigger permission error
        config_file = manager.data_path
        os.chmod(config_file, stat.S_IRUSR)

        try:
            # This should handle the error gracefully
            manager.load()
        finally:
            # Restore permissions
            os.chmod(config_file, stat.S_IRUSR | stat.S_IWUSR)

    def test_store_fails_gracefully_without_directory(self, temp_config_dir):
        """Test that store fails gracefully when directory doesn't exist."""
        import shutil

        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Remove the directory
        shutil.rmtree(temp_config_dir)

        # Store should fail gracefully and return False
        result = manager.store()
        assert result is False

    def test_backup_with_custom_path(self, temp_config_dir):
        """Test backup to a custom path."""
        from pathlib import Path

        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Create custom backup path
        custom_backup = Path(temp_config_dir) / "custom_backup.json"
        backup_json = manager.get_backup_json()

        # Write to custom path
        custom_backup.write_text(backup_json)

        # Verify it can be restored from custom path
        manager.clear()
        manager.restore_from_backup_json(custom_backup.read_text())

        assert len(list(manager.all())) == 1

    def test_get_device_id_with_missing_attributes(self, temp_config_dir):
        """Test get_device_id with objects missing specified attributes."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Create an object without expected attributes
        class BadConfig:
            pass

        bad_obj = BadConfig()

        with pytest.raises(AttributeError):
            manager.get_device_id(bad_obj)

    def test_json_encoder_with_non_dataclass(self):
        """Test JSON encoder handles non-dataclass objects."""
        from ucapi_framework.config import _EnhancedJSONEncoder
        from datetime import datetime

        # Test with an object that needs default JSON encoding
        data = {"timestamp": datetime(2025, 1, 1, 12, 0, 0)}

        # This should fail since datetime isn't serializable
        with pytest.raises(TypeError):
            json.dumps(data, cls=_EnhancedJSONEncoder)

    def test_load_handles_permission_error(self, temp_config_dir):
        """Test load handles permission errors gracefully."""
        import stat

        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Make file unreadable
        config_file = manager.data_path
        os.chmod(config_file, 0o000)

        try:
            result = manager.load()
            assert result is False
        finally:
            # Restore permissions for cleanup
            os.chmod(config_file, stat.S_IRUSR | stat.S_IWUSR)

    def test_load_handles_json_decode_error(self, temp_config_dir):
        """Test load handles JSON decode errors gracefully."""
        from pathlib import Path

        manager = ConcreteDeviceManager(temp_config_dir)

        # Write invalid JSON to config file
        # pylint: disable=protected-access
        Path(manager._cfg_file_path).write_text("{ invalid json }", encoding="utf-8")

        result = manager.load()
        assert result is False

    def test_load_handles_invalid_format(self, temp_config_dir):
        """Test load handles invalid config format gracefully."""
        from pathlib import Path

        manager = ConcreteDeviceManager(temp_config_dir)

        # Write valid JSON but wrong format (string instead of array)
        # pylint: disable=protected-access
        Path(manager._cfg_file_path).write_text(
            json.dumps("not an array"), encoding="utf-8"
        )

        result = manager.load()
        assert result is False

    def test_restore_handles_invalid_format(self, temp_config_dir):
        """Test restore handles invalid format errors."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Try to restore from invalid format
        invalid_backup = json.dumps({"not": "an array"})
        result = manager.restore_from_backup_json(invalid_backup)

        assert result is False

    def test_update_nonexistent_device(self, temp_config_dir):
        """Test update method with nonexistent device."""
        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")

        # Try to update device that doesn't exist
        manager.update(device)

        # Should not add it, just silently do nothing
        assert len(list(manager.all())) == 0

    def test_store_handles_write_error(self, temp_config_dir):
        """Test store handles OSError when writing fails."""
        from unittest.mock import patch, mock_open

        manager = ConcreteDeviceManager(temp_config_dir)
        device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        manager.add_or_update(device)

        # Make open() raise OSError
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = OSError("Disk full")
            result = manager.store()

        assert result is False

    def test_restore_with_invalid_devices(self, temp_config_dir):
        """Test restore with backup containing invalid device entries."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Create backup with mix of valid and invalid entries
        # Use the same format that ConcreteDeviceManager.serialize_device creates
        valid_device = DeviceConfig("dev1", "Device 1", "192.168.1.1")
        valid_dict = {
            "identifier": valid_device.identifier,
            "name": valid_device.name,
            "address": valid_device.address,
        }

        backup = json.dumps(
            [
                "not a dict",  # Invalid - not a dict
                valid_dict,  # Valid
                {"invalid": "structure"},  # Invalid - can't deserialize
            ]
        )

        result = manager.restore_from_backup_json(backup)

        # Should succeed with at least one valid device
        assert result is True
        assert len(list(manager.all())) == 1

    def test_restore_with_all_invalid_devices(self, temp_config_dir):
        """Test restore with backup containing only invalid entries."""
        manager = ConcreteDeviceManager(temp_config_dir)

        # Create backup with only invalid entries
        backup = json.dumps(
            [
                "not a dict",
                {"invalid": "structure"},
            ]
        )

        result = manager.restore_from_backup_json(backup)

        # Should fail with no valid devices
        assert result is False
