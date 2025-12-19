"""Tests for BaseIntegrationDriver."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import ucapi
from ucapi import media_player

from ucapi_framework.device import BaseDeviceInterface, DeviceEvents
from ucapi_framework.driver import BaseIntegrationDriver, create_entity_id
from ucapi import EntityTypes


@dataclass
class DeviceConfigForTests:
    """Test device configuration."""

    identifier: str
    name: str
    address: str


class DeviceForTests(BaseDeviceInterface):
    """Test device implementation."""

    def __init__(self, device_config, loop=None, config_manager=None):
        super().__init__(device_config, loop, config_manager)
        self._connected = False
        self._state = None

    @property
    def identifier(self) -> str:
        return self.device_config.identifier

    @property
    def name(self) -> str:
        return self.device_config.name

    @property
    def address(self) -> str:
        return self.device_config.address

    @property
    def log_id(self) -> str:
        return f"{self.name}[{self.identifier}]"

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    async def connect(self) -> bool:
        self._connected = True
        self.events.emit(DeviceEvents.CONNECTED, self.identifier)
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)


class EntityForTests(media_player.MediaPlayer):
    """Test entity class."""

    pass


class ConcreteDriver(BaseIntegrationDriver[DeviceForTests, DeviceConfigForTests]):
    """Concrete driver implementation for testing."""

    def map_device_state(self, device_state) -> media_player.States:
        """Map device state to media player state."""
        # Handle both uppercase and lowercase for testing
        state = device_state.lower() if isinstance(device_state, str) else device_state
        if state == "playing":
            return media_player.States.PLAYING
        elif state == "paused":
            return media_player.States.PAUSED
        elif state == "on":
            return media_player.States.ON
        elif state == "off":
            return media_player.States.OFF
        return media_player.States.UNKNOWN

    def create_entities(
        self, device_config: DeviceConfigForTests, device: DeviceForTests
    ) -> list:
        """Create entities for a device - uses standard entity ID format."""
        entity = media_player.MediaPlayer(
            f"media_player.{device_config.identifier}",
            device_config.name,
            [media_player.Features.ON_OFF],
            {media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )
        return [entity]

    def entity_type_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract entity type from entity ID.

        Overridden because create_entities is overridden.
        Since we use the standard format (entity_type.device_id), we delegate to the parent.
        """
        return super().entity_type_from_entity_id(entity_id)

    def device_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract device ID from entity ID.

        Overridden because create_entities is overridden.
        Since we use the standard format (entity_type.device_id), we delegate to the parent.
        """
        return super().device_from_entity_id(entity_id)

    def sub_device_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract sub-device ID from entity ID.

        Overridden because create_entities is overridden.
        Since we use the standard format (no sub-devices in this test), we delegate to the parent.
        """
        return super().sub_device_from_entity_id(entity_id)


@pytest.fixture
def mock_loop():
    """Create a mock event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Mock collection that tracks added entities
class MockEntityCollection:
    def __init__(self):
        self._entities = []

    def add(self, entity):
        self._entities.append(entity)

    def remove(self, entity_id):
        self._entities = [e for e in self._entities if e.id != entity_id]

    def contains(self, entity_id):
        return any(e.id == entity_id for e in self._entities)

    def get(self, entity_id):
        for e in self._entities:
            if e.id == entity_id:
                return e
        return None

    def get_all(self):
        # Return list of dicts matching ucapi Entities.get_all() behavior
        return [
            {
                "entity_id": entity.id,
                "entity_type": entity.entity_type,
                "device_id": getattr(entity, "device_id", None),
                "features": entity.features,
                "name": entity.name,
            }
            for entity in self._entities
        ]

    def clear(self):
        self._entities.clear()

    def __iter__(self):
        return iter(self._entities)


@pytest.fixture
def driver(mock_loop):
    """Create a test driver instance."""
    driver = ConcreteDriver(
        DeviceForTests,
        [media_player.MediaPlayer],
        loop=mock_loop,
    )
    # Mock the API
    driver.api = MagicMock()
    driver.api.configured_entities = MagicMock()
    driver.api.available_entities = MockEntityCollection()
    driver.api.set_device_state = AsyncMock()
    return driver


class TestBaseIntegrationDriver:
    """Tests for BaseIntegrationDriver."""

    def test_init(self, mock_loop):
        """Test driver initialization."""
        driver = ConcreteDriver(
            DeviceForTests, [media_player.MediaPlayer], loop=mock_loop
        )

        assert driver._device_class == DeviceForTests
        assert driver._entity_classes == [media_player.MediaPlayer]
        assert driver._configured_devices == {}

    @pytest.mark.asyncio
    async def test_on_r2_connect_cmd(self):
        """Test Remote Two connect command."""
        # Use real loop for this test since we need background tasks
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Add a device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        await driver.on_r2_connect_cmd()

        # Should set device state
        driver.api.set_device_state.assert_called_once_with(
            ucapi.DeviceStates.CONNECTED
        )

        # Give the background task time to start and run
        await asyncio.sleep(0.01)

        # Should connect all devices
        device = driver._configured_devices["dev1"]
        assert device.is_connected is True

        # Wait for all pending tasks to complete (event handlers)
        pending = [
            t
            for t in asyncio.all_tasks(loop)
            if t != asyncio.current_task(loop) and not t.done()
        ]
        if pending:
            await asyncio.wait(pending, timeout=0.1)

    @pytest.mark.asyncio
    async def test_on_r2_disconnect_cmd(self):
        """Test Remote Two disconnect command."""
        # Use real loop for this test since we need background tasks
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Add and connect a device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()

        await driver.on_r2_disconnect_cmd()

        # Give the background task time to start and run
        await asyncio.sleep(0.01)

        assert device.is_connected is False

        # Wait for all pending tasks to complete (event handlers)
        pending = [
            t
            for t in asyncio.all_tasks(loop)
            if t != asyncio.current_task(loop) and not t.done()
        ]
        if pending:
            await asyncio.wait(pending, timeout=0.1)

    @pytest.mark.asyncio
    async def test_on_r2_enter_standby(self, driver):
        """Test entering standby mode."""
        # Add and connect devices
        config1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config2 = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        driver.add_configured_device(config1, connect=False)
        driver.add_configured_device(config2, connect=False)

        dev1 = driver._configured_devices["dev1"]
        dev2 = driver._configured_devices["dev2"]
        await dev1.connect()
        await dev2.connect()

        await driver.on_r2_enter_standby()

        assert dev1.is_connected is False
        assert dev2.is_connected is False

    @pytest.mark.asyncio
    async def test_on_r2_exit_standby(self):
        """Test exiting standby mode."""
        # Use real loop for this test since we need background tasks
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Add devices
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        await driver.on_r2_exit_standby()

        # Give the background task time to start and run
        await asyncio.sleep(0.01)

        device = driver._configured_devices["dev1"]
        assert device.is_connected is True

        # Wait for all pending tasks to complete (event handlers)
        # Get all tasks except the current one
        pending = [
            t
            for t in asyncio.all_tasks(loop)
            if t != asyncio.current_task(loop) and not t.done()
        ]
        if pending:
            await asyncio.wait(pending, timeout=0.1)

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_existing_device(self, driver):
        """Test subscribing to entities with existing configured device."""
        # Add device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        device._state = "on"

        # Mock configured entity with entity_type
        mock_entity = Mock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get.return_value = mock_entity

        await driver.on_subscribe_entities(["media_player.dev1"])

        # Should update entity state
        driver.api.configured_entities.update_attributes.assert_called()

        # Give any background event handler tasks time to complete
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_new_device(self, driver):
        """Test subscribing to entities for a new device."""
        # Mock config
        driver.config_manager = MagicMock()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.config_manager.get.return_value = config

        await driver.on_subscribe_entities(["media_player.dev1"])

        # Device should be added
        assert "dev1" in driver._configured_devices

    @pytest.mark.asyncio
    async def test_on_unsubscribe_entities(self, driver):
        """Test unsubscribing from entities."""
        # Add device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()

        # Mock that no entities are configured
        driver.api.configured_entities.get.return_value = None

        await driver.on_unsubscribe_entities(["media_player.dev1"])

        # Device should be disconnected and removed
        assert "dev1" not in driver._configured_devices
        assert device.is_connected is False

    def test_add_configured_device(self, driver):
        """Test adding a configured device."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        driver.add_configured_device(config, connect=False)

        assert "dev1" in driver._configured_devices
        device = driver._configured_devices["dev1"]
        assert device.identifier == "dev1"
        assert device.name == "Device 1"

    def test_add_configured_device_twice(self, driver):
        """Test adding the same device twice doesn't create duplicates."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        driver.add_configured_device(config, connect=False)
        driver.add_configured_device(config, connect=False)

        assert len(driver._configured_devices) == 1

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_without_connection_requirement(
        self, mock_loop
    ):
        """Test registration with require_connection_before_registry=False uses add_configured_device."""
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=False,
            loop=mock_loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        # Create mock config manager
        config1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config2 = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        mock_config_manager = MagicMock()
        mock_config_manager.all.return_value = [config1, config2]
        driver.config_manager = mock_config_manager

        await driver.register_all_configured_devices(connect=False)

        # Both devices should be registered
        assert "dev1" in driver._configured_devices
        assert "dev2" in driver._configured_devices
        assert len(driver._configured_devices) == 2

        # Devices should NOT be connected (connect=False)
        assert driver._configured_devices["dev1"].is_connected is False
        assert driver._configured_devices["dev2"].is_connected is False

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_with_connection_requirement(
        self, mock_loop
    ):
        """Test registration with require_connection_before_registry=True uses async_add_configured_device."""
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=mock_loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        # Create mock config manager
        config1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config2 = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        mock_config_manager = MagicMock()
        mock_config_manager.all.return_value = [config1, config2]
        driver.config_manager = mock_config_manager

        await driver.register_all_configured_devices()

        # Both devices should be registered
        assert "dev1" in driver._configured_devices
        assert "dev2" in driver._configured_devices
        assert len(driver._configured_devices) == 2

        # Devices should be connected (async_add_configured_device always connects)
        assert driver._configured_devices["dev1"].is_connected is True
        assert driver._configured_devices["dev2"].is_connected is True

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_with_no_config_manager(
        self, mock_loop, caplog
    ):
        """Test that registration logs warning and returns when config_manager is None."""
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            loop=mock_loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        # config_manager is None by default
        assert driver.config_manager is None

        await driver.register_all_configured_devices()

        # Should log warning
        assert "Cannot register devices: config_manager is not set" in caplog.text

        # No devices should be registered
        assert len(driver._configured_devices) == 0

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_with_connect_parameter(self):
        """Test that connect parameter is passed through to add_configured_device."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=False,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Create mock config manager
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        mock_config_manager = MagicMock()
        mock_config_manager.all.return_value = [config]
        driver.config_manager = mock_config_manager

        # Register with connect=True
        await driver.register_all_configured_devices(connect=True)

        # Device should be registered
        assert "dev1" in driver._configured_devices

        # Give the background connection task time to run
        await asyncio.sleep(0.05)

        # Wait for pending tasks to complete
        pending = [
            t
            for t in asyncio.all_tasks(loop)
            if t != asyncio.current_task(loop) and not t.done()
        ]
        if pending:
            await asyncio.wait(pending, timeout=0.1)

        # Device should be connected
        assert driver._configured_devices["dev1"].is_connected is True

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_multiple_devices(self, mock_loop):
        """Test registration of multiple devices from the config manager."""
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=False,
            loop=mock_loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        # Create mock config manager with 5 devices
        configs = [
            DeviceConfigForTests(f"dev{i}", f"Device {i}", f"192.168.1.{i}")
            for i in range(1, 6)
        ]
        mock_config_manager = MagicMock()
        mock_config_manager.all.return_value = configs
        driver.config_manager = mock_config_manager

        await driver.register_all_configured_devices(connect=False)

        # All 5 devices should be registered
        assert len(driver._configured_devices) == 5
        for i in range(1, 6):
            assert f"dev{i}" in driver._configured_devices
            device = driver._configured_devices[f"dev{i}"]
            assert device.identifier == f"dev{i}"
            assert device.name == f"Device {i}"

    @pytest.mark.asyncio
    async def test_register_all_configured_devices_empty_config_manager(
        self, mock_loop
    ):
        """Test registration with empty config manager registers no devices."""
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            loop=mock_loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        # Create mock config manager with no devices
        mock_config_manager = MagicMock()
        mock_config_manager.all.return_value = []
        driver.config_manager = mock_config_manager

        await driver.register_all_configured_devices()

        # No devices should be registered
        assert len(driver._configured_devices) == 0

    def test_setup_device_event_handlers(self, driver):
        """Test that event handlers are attached to devices."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        device = driver._configured_devices["dev1"]

        # Verify event handlers are attached
        assert device.events._events.get(DeviceEvents.CONNECTED) is not None
        assert device.events._events.get(DeviceEvents.DISCONNECTED) is not None
        assert device.events._events.get(DeviceEvents.ERROR) is not None
        assert device.events._events.get(DeviceEvents.UPDATE) is not None

    @pytest.mark.asyncio
    async def test_on_device_connected(self, driver):
        """Test device connected event handler."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Mock entity with entity_type
        mock_entity = Mock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get.return_value = mock_entity

        device = driver._configured_devices["dev1"]
        device._state = "on"

        await driver.on_device_connected("dev1")

        # Should update entity attributes and set device state
        driver.api.configured_entities.update_attributes.assert_called()
        driver.api.set_device_state.assert_called_with(ucapi.DeviceStates.CONNECTED)

        # Give any background event handler tasks time to complete
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_on_device_disconnected(self, driver):
        """Test device disconnected event handler."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Mock entity with entity_type
        mock_entity = Mock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get.return_value = mock_entity

        await driver.on_device_disconnected("dev1")

        # Should update entity to UNAVAILABLE
        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_connection_error(self, driver):
        """Test device connection error handler."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Mock entity with entity_type
        mock_entity = Mock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get.return_value = mock_entity

        await driver.on_device_connection_error("dev1", "Connection timeout")

        # Should update entity to UNAVAILABLE (don't set integration to ERROR per reference implementation)
        driver.api.configured_entities.update_attributes.assert_called()

    def test_get_device_config(self, driver):
        """Test getting device configuration."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        retrieved = driver.get_device_config("dev1")

        assert retrieved.identifier == "dev1"
        assert retrieved.name == "Device 1"

    def test_get_device_config_from_config_manager(self, driver):
        """Test getting device configuration from config manager."""
        driver.config_manager = MagicMock()
        config = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        driver.config_manager.get.return_value = config

        retrieved = driver.get_device_config("dev2")

        assert retrieved.identifier == "dev2"
        driver.config_manager.get.assert_called_once_with("dev2")

    def test_get_device_id(self, driver):
        """Test extracting device ID from config."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        device_id = driver.get_device_id(config)

        assert device_id == "dev1"

    def test_get_device_name(self, driver):
        """Test extracting device name from config."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        name = driver.get_device_name(config)

        assert name == "Device 1"

    def test_get_device_address(self, driver):
        """Test extracting device address from config."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        address = driver.get_device_address(config)

        assert address == "192.168.1.1"

    def test_remove_device(self, driver):
        """Test removing a device."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        driver.remove_device("dev1")

        assert "dev1" not in driver._configured_devices

    def test_clear_devices(self, driver):
        """Test clearing all devices."""
        config1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config2 = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        driver.add_configured_device(config1, connect=False)
        driver.add_configured_device(config2, connect=False)

        driver.clear_devices()

        assert len(driver._configured_devices) == 0

    def test_on_device_added_callback(self, driver):
        """Test on_device_added callback."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        driver.on_device_added(config)

        assert "dev1" in driver._configured_devices

    def test_on_device_removed_callback(self, driver):
        """Test on_device_removed callback."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        driver.on_device_removed(config)

        assert "dev1" not in driver._configured_devices

    def test_on_device_removed_none_clears_all(self, driver):
        """Test that on_device_removed with None clears all devices."""
        config1 = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        config2 = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        driver.add_configured_device(config1, connect=False)
        driver.add_configured_device(config2, connect=False)

        driver.on_device_removed(None)

        assert len(driver._configured_devices) == 0

    def test_entity_type_from_entity_id(self, driver):
        """Test extracting entity type from entity ID."""
        entity_type = driver.entity_type_from_entity_id("media_player.dev1")

        assert entity_type == "media_player"

    def test_entity_type_from_entity_id_with_sub_entity(self, driver):
        """Test extracting entity type from entity ID with sub-entity."""
        entity_type = driver.entity_type_from_entity_id("light.hub_1.bedroom")

        assert entity_type == "light"

    def test_entity_type_from_entity_id_invalid(self, driver):
        """Test entity_type_from_entity_id with invalid entity ID raises ValueError."""
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            driver.entity_type_from_entity_id("invalid")

    def test_entity_type_from_entity_id_none(self, driver):
        """Test entity_type_from_entity_id with None."""
        entity_type = driver.entity_type_from_entity_id(None)

        assert entity_type is None

    def test_device_from_entity_id(self, driver):
        """Test extracting device ID from entity ID."""
        device_id = driver.device_from_entity_id("media_player.dev1")

        assert device_id == "dev1"

    def test_sub_device_from_entity_id_simple_format(self, driver):
        """Test sub_device_from_entity_id with simple 2-part format returns None."""
        sub_device = driver.sub_device_from_entity_id("media_player.dev1")

        assert sub_device is None

    def test_sub_device_from_entity_id_with_sub_device(self, driver):
        """Test extracting sub-device from 3-part entity ID."""
        sub_device = driver.sub_device_from_entity_id("light.hub_1.bedroom")

        assert sub_device == "bedroom"

    def test_sub_device_from_entity_id_with_multiple_parts(self, driver):
        """Test sub_device_from_entity_id with more than 3 parts returns everything after second period."""
        sub_device = driver.sub_device_from_entity_id("switch.bridge.zone.outlet_1")

        # Returns everything after second period: "zone.outlet_1"
        # This supports sub-devices with dots in their IDs
        assert sub_device == "zone.outlet_1"

    def test_sub_device_from_entity_id_invalid(self, driver):
        """Test sub_device_from_entity_id with invalid entity ID raises ValueError."""
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            driver.sub_device_from_entity_id("invalid")

    def test_sub_device_from_entity_id_none(self, driver):
        """Test sub_device_from_entity_id with None."""
        sub_device = driver.sub_device_from_entity_id(None)

        assert sub_device is None

    def test_device_from_entity_id_default_implementation(self, mock_loop):
        """Test the default device_from_entity_id implementation."""

        class MinimalDriver(BaseIntegrationDriver):
            """Minimal driver using default device_from_entity_id."""

            def get_entity_ids_for_device(self, device_id):
                return [f"media_player.{device_id}"]

        driver = MinimalDriver(DeviceForTests, [], loop=mock_loop)

        # Test simple format: entity_type.device_id
        assert driver.device_from_entity_id("media_player.dev1") == "dev1"
        assert driver.device_from_entity_id("remote.my_device") == "my_device"
        assert driver.device_from_entity_id("light.hub_123") == "hub_123"

        # Test format with sub-entity: entity_type.device_id.entity_id
        assert driver.device_from_entity_id("light.hub_1.bedroom") == "hub_1"
        assert (
            driver.device_from_entity_id("media_player.receiver.zone_2") == "receiver"
        )
        assert (
            driver.device_from_entity_id("switch.bridge_abc.switch_1") == "bridge_abc"
        )

        # Test invalid formats
        assert driver.device_from_entity_id("") is None
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            driver.device_from_entity_id("invalid")
        assert driver.device_from_entity_id("only.one") == "one"

    def test_sub_device_from_entity_id_requires_override_when_3_part_format_used(
        self, mock_loop
    ):
        """Test that sub_device_from_entity_id works with standard 2-part format."""

        class DriverWith2PartEntities(BaseIntegrationDriver):
            """Driver that overrides create_entities with 2-part format."""

            def create_entities(self, device_config, device):
                # Custom entity creation with 2-part format (no sub-devices)
                return []

            def get_entity_ids_for_device(self, device_id):
                return [f"media_player.{device_id}"]  # 2-part format

        driver = DriverWith2PartEntities(DeviceForTests, [], loop=mock_loop)

        # Should work fine with 2-part format (using default separator)
        result = driver.sub_device_from_entity_id("media_player.dev1")
        assert result is None  # 2-part format has no sub-device

    def test_device_from_entity_id_works_when_both_overridden(self, mock_loop):
        """Test that both methods can be overridden together successfully."""

        class DriverWithCustomFormat(BaseIntegrationDriver):
            """Driver with custom entity ID format and matching parser."""

            def create_entities(self, device_config, device):
                # Custom format where entity_id IS the device_id
                return []

            def device_from_entity_id(self, entity_id):
                # Custom parser for custom format
                return entity_id  # In this format, entity_id IS device_id

            def get_entity_ids_for_device(self, device_id):
                return [device_id]

        driver = DriverWithCustomFormat(DeviceForTests, [], loop=mock_loop)

        # Should work fine with both overridden
        assert driver.device_from_entity_id("my_device_id") == "my_device_id"
        assert driver.device_from_entity_id("account_123") == "account_123"

    def test_custom_entity_id_separator(self, mock_loop):
        """Test using a custom entity_id_separator."""

        class DriverWithCustomSeparator(BaseIntegrationDriver):
            """Driver using underscore as separator."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.entity_id_separator = "_"

            def create_entities(self, device_config, device):
                return []

            def get_entity_ids_for_device(self, device_id):
                return []

        driver = DriverWithCustomSeparator(DeviceForTests, [], loop=mock_loop)

        # Should parse using underscore separator
        assert driver.entity_type_from_entity_id("media_player_dev1") == "media"
        assert driver.device_from_entity_id("media_player_dev1") == "player"
        assert driver.sub_device_from_entity_id("light_hub1_bedroom") == "bedroom"

    def test_custom_separator_raises_error_for_wrong_format(self, mock_loop):
        """Test that ValueError is raised when entity_id doesn't contain custom separator."""

        class DriverWithCustomSeparator(BaseIntegrationDriver):
            """Driver using underscore as separator."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.entity_id_separator = "_"

            def create_entities(self, device_config, device):
                return []

            def get_entity_ids_for_device(self, device_id):
                return []

        driver = DriverWithCustomSeparator(DeviceForTests, [], loop=mock_loop)

        # Should raise ValueError when period is used instead of underscore
        # Use an entity_id that has period but no underscore
        with pytest.raises(
            ValueError, match="does not contain the expected separator '_'"
        ):
            driver.entity_type_from_entity_id("type.dev1")

    def test_get_entity_ids_for_device(self, driver):
        """Test getting entity IDs for a device."""
        # Add a device so entities are registered
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        entity_ids = driver.get_entity_ids_for_device("dev1")

        assert entity_ids == ["media_player.dev1"]

    def test_map_device_state(self, driver):
        """Test mapping device state to media player state."""
        assert driver.map_device_state("playing") == media_player.States.PLAYING
        assert driver.map_device_state("paused") == media_player.States.PAUSED
        assert driver.map_device_state("on") == media_player.States.ON
        assert driver.map_device_state("off") == media_player.States.OFF
        assert driver.map_device_state("unknown") == media_player.States.UNKNOWN

    def test_map_device_state_default_implementation(self, mock_loop):
        """Test the default map_device_state implementation with various inputs."""

        # Create a minimal driver that uses the default implementation
        class MinimalDriver(BaseIntegrationDriver):
            """Minimal driver using default map_device_state."""

            def device_from_entity_id(self, entity_id):
                return entity_id.split(".")[-1]

            def get_entity_ids_for_device(self, device_id):
                return [f"media_player.{device_id}"]

        driver = MinimalDriver(DeviceForTests, [], loop=mock_loop)

        # Test all media player states with exact matches
        assert driver.map_device_state("UNAVAILABLE") == media_player.States.UNAVAILABLE
        assert driver.map_device_state("unavailable") == media_player.States.UNAVAILABLE
        assert driver.map_device_state("UNKNOWN") == media_player.States.UNKNOWN
        assert driver.map_device_state("unknown") == media_player.States.UNKNOWN

        # Test ON state variants
        assert driver.map_device_state("ON") == media_player.States.ON
        assert driver.map_device_state("on") == media_player.States.ON
        assert driver.map_device_state("MENU") == media_player.States.ON
        assert driver.map_device_state("menu") == media_player.States.ON
        assert driver.map_device_state("IDLE") == media_player.States.ON
        assert driver.map_device_state("ACTIVE") == media_player.States.ON
        assert driver.map_device_state("READY") == media_player.States.ON

        # Test OFF state variants
        assert driver.map_device_state("OFF") == media_player.States.OFF
        assert driver.map_device_state("off") == media_player.States.OFF
        assert driver.map_device_state("POWER_OFF") == media_player.States.OFF
        assert driver.map_device_state("POWERED_OFF") == media_player.States.OFF

        # Test PLAYING state variants
        assert driver.map_device_state("PLAYING") == media_player.States.PLAYING
        assert driver.map_device_state("playing") == media_player.States.PLAYING
        assert driver.map_device_state("PLAY") == media_player.States.PLAYING

        # Test PAUSED state variants
        assert driver.map_device_state("PAUSED") == media_player.States.PAUSED
        assert driver.map_device_state("paused") == media_player.States.PAUSED
        assert driver.map_device_state("PAUSE") == media_player.States.PAUSED

        # Test STANDBY state variants
        assert driver.map_device_state("STANDBY") == media_player.States.STANDBY
        assert driver.map_device_state("standby") == media_player.States.STANDBY
        assert driver.map_device_state("SLEEP") == media_player.States.STANDBY

        # Test BUFFERING state variants
        assert driver.map_device_state("BUFFERING") == media_player.States.BUFFERING
        assert driver.map_device_state("buffering") == media_player.States.BUFFERING
        assert driver.map_device_state("LOADING") == media_player.States.BUFFERING

        # Test None and unrecognized states default to UNKNOWN
        assert driver.map_device_state(None) == media_player.States.UNKNOWN
        assert driver.map_device_state("random_state") == media_player.States.UNKNOWN
        assert driver.map_device_state("anything") == media_player.States.UNKNOWN

    async def test_create_entities(self, driver):
        """Test creating entities for a device."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        device = DeviceForTests(config)

        entities = driver.create_entities(config, device)

        assert len(entities) == 1
        assert entities[0].id == "media_player.dev1"
        # Entity name is a dict with language codes
        assert entities[0].name == {"en": "Device 1"} or entities[0].name == "Device 1"

    @pytest.mark.asyncio
    async def test_on_device_update(self, driver):
        """Test default on_device_update handler."""
        # Should not raise
        await driver.on_device_update("dev1", {"state": "playing"})
        await driver.on_device_update("dev1", None)

    @pytest.mark.asyncio
    async def test_on_device_update_media_player(self):
        """Test on_device_update with media_player entity."""
        # Use real event loop and real entity collections
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        # Use real entity collections
        driver.api = MagicMock()
        driver.api.configured_entities = ucapi.Entities("configured", loop)
        driver.api.available_entities = ucapi.Entities("available", loop)
        driver.api.set_device_state = AsyncMock()

        # Create a device (but don't add it - we're manually managing entities for this test)
        device_config = DeviceConfigForTests("mp1", "Media Player", "192.168.1.100")
        device = DeviceForTests(device_config)
        driver._configured_devices["mp1"] = device

        # Create a media player entity
        entity = ucapi.MediaPlayer(
            "media_player.mp1",
            "Media Player",
            [media_player.Features.ON_OFF, media_player.Features.VOLUME],
            {
                media_player.Attributes.STATE: media_player.States.OFF,
                media_player.Attributes.VOLUME: 50,
                media_player.Attributes.MUTED: False,
            },
        )
        entity.device_id = "mp1"
        driver.api.configured_entities.add(entity)

        # Send update with media player attributes
        update = {
            "state": media_player.States.PLAYING.value,
            "volume": 75,
            "muted": True,
            "media_title": "Test Song",
            "media_artist": "Test Artist",
            "source": "Spotify",
        }
        await driver.on_device_update("media_player.mp1", update)

        # Verify attributes were updated
        updated_entity = driver.api.configured_entities.get("media_player.mp1")
        assert (
            updated_entity.attributes[media_player.Attributes.STATE]
            == media_player.States.PLAYING
        )
        assert updated_entity.attributes[media_player.Attributes.VOLUME] == 75
        assert updated_entity.attributes[media_player.Attributes.MUTED] is True
        assert (
            updated_entity.attributes[media_player.Attributes.MEDIA_TITLE]
            == "Test Song"
        )
        assert (
            updated_entity.attributes[media_player.Attributes.MEDIA_ARTIST]
            == "Test Artist"
        )
        assert updated_entity.attributes[media_player.Attributes.SOURCE] == "Spotify"

    @pytest.mark.asyncio
    async def test_on_device_update_multiple_entities(self):
        """Test on_device_update with multiple entities on same device."""
        # Use real event loop and real entity collections
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = ucapi.Entities("configured", loop)
        driver.api.available_entities = ucapi.Entities("available", loop)
        driver.api.set_device_state = AsyncMock()

        # Create a device (but don't add it - we're manually managing entities for this test)
        device_config = DeviceConfigForTests("multi1", "Multi Device", "192.168.1.101")
        device = DeviceForTests(device_config)
        driver._configured_devices["multi1"] = device

        # Create multiple entities
        mp_entity = ucapi.MediaPlayer(
            "media_player.multi1",
            "Media Player",
            [media_player.Features.ON_OFF],
            {media_player.Attributes.STATE: media_player.States.OFF},
        )
        mp_entity.device_id = "multi1"
        driver.api.configured_entities.add(mp_entity)

        # Send update with state change
        update = {"state": media_player.States.ON.value}
        await driver.on_device_update("media_player.multi1", update)

        # Verify entity was updated
        updated_mp = driver.api.configured_entities.get("media_player.multi1")
        assert (
            updated_mp.attributes[media_player.Attributes.STATE]
            == media_player.States.ON
        )

    @pytest.mark.asyncio
    async def test_on_device_update_partial_attributes(self):
        """Test on_device_update only updates attributes present in update dict."""
        # Use real event loop and real entity collections
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = ucapi.Entities("configured", loop)
        driver.api.available_entities = ucapi.Entities("available", loop)
        driver.api.set_device_state = AsyncMock()

        # Create a device
        device_config = DeviceConfigForTests("mp2", "Media Player 2", "192.168.1.102")
        device = DeviceForTests(device_config)
        driver.add_configured_device(device)

        # Create entity with multiple attributes
        entity = ucapi.MediaPlayer(
            "media_player.mp2",
            "Media Player 2",
            [media_player.Features.ON_OFF, media_player.Features.VOLUME],
            {
                media_player.Attributes.STATE: media_player.States.ON,
                media_player.Attributes.VOLUME: 50,
                media_player.Attributes.MUTED: False,
            },
        )
        entity.device_id = "mp2"
        driver.api.configured_entities.add(entity)

        # Send update with only volume (not state)
        update = {"volume": 80}
        await driver.on_device_update("media_player.mp2", update)

        # Verify only volume was updated, state unchanged
        updated_entity = driver.api.configured_entities.get("media_player.mp2")
        assert (
            updated_entity.attributes[media_player.Attributes.STATE]
            == media_player.States.ON
        )
        assert updated_entity.attributes[media_player.Attributes.VOLUME] == 80
        assert updated_entity.attributes[media_player.Attributes.MUTED] is False

    @pytest.mark.asyncio
    async def test_on_device_update_available_entities(self):
        """Test on_device_update works with available entities too."""
        # Use real event loop and real entity collections
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = ucapi.Entities("configured", loop)
        driver.api.available_entities = ucapi.Entities("available", loop)
        driver.api.set_device_state = AsyncMock()

        # Create a device (but don't add it - we're manually managing entities for this test)
        device_config = DeviceConfigForTests(
            "avail1", "Available Device", "192.168.1.103"
        )
        device = DeviceForTests(device_config)
        driver._configured_devices["avail1"] = device

        # Create an available entity (not configured)
        entity = ucapi.MediaPlayer(
            "media_player.avail1",
            "Available Player",
            [media_player.Features.ON_OFF],
            {media_player.Attributes.STATE: media_player.States.OFF},
        )
        entity.device_id = "avail1"
        driver.api.available_entities.add(entity)

        # Send update
        update = {"state": media_player.States.PLAYING.value}
        await driver.on_device_update("media_player.avail1", update)

        # Verify available entity was updated
        updated_entity = driver.api.available_entities.get("media_player.avail1")
        assert (
            updated_entity.attributes[media_player.Attributes.STATE]
            == media_player.States.PLAYING
        )

    @pytest.mark.asyncio
    async def test_on_device_update_entity_id_without_prefix(self):
        """Test on_device_update with entity_id that matches device_id (no type prefix)."""
        # Use real event loop and real entity collections
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = ucapi.Entities("configured", loop)
        driver.api.available_entities = ucapi.Entities("available", loop)
        driver.api.set_device_state = AsyncMock()

        # Create a device
        device_config = DeviceConfigForTests("mydevice", "My Device", "192.168.1.100")
        device = DeviceForTests(device_config)
        driver._configured_devices["mydevice"] = device

        # Create an entity where entity_id equals device_id (no prefix like "media_player.")
        entity = ucapi.MediaPlayer(
            "mydevice",  # entity_id matches device_id exactly
            "My Device",
            [media_player.Features.ON_OFF, media_player.Features.VOLUME],
            {
                media_player.Attributes.STATE: media_player.States.OFF,
                media_player.Attributes.VOLUME: 50,
            },
        )
        entity.device_id = "mydevice"
        driver.api.configured_entities.add(entity)

        # Send update using entity_id (which equals device_id)
        update = {
            "state": media_player.States.PLAYING.value,
            "volume": 75,
        }
        await driver.on_device_update("mydevice", update)

        # Verify attributes were updated
        updated_entity = driver.api.configured_entities.get("mydevice")
        assert (
            updated_entity.attributes[media_player.Attributes.STATE]
            == media_player.States.PLAYING
        )
        assert updated_entity.attributes[media_player.Attributes.VOLUME] == 75

    @pytest.mark.asyncio
    async def test_on_device_update_nonexistent_entity(self, driver):
        """Test on_device_update with no entities for device."""
        # Should not raise even if device has no entities
        await driver.on_device_update("nonexistent", {"state": "on"})


class TestEntityIdHelpers:
    """Tests for entity ID helper functions."""

    def test_create_entity_id_with_enum(self):
        """Test creating entity ID with EntityTypes enum."""
        entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, "device_123")
        assert entity_id == "media_player.device_123"

        entity_id = create_entity_id(EntityTypes.REMOTE, "my_device")
        assert entity_id == "remote.my_device"

        entity_id = create_entity_id(EntityTypes.LIGHT, "light_1")
        assert entity_id == "light.light_1"

    def test_create_entity_id_with_string(self):
        """Test creating entity ID with string entity type."""
        entity_id = create_entity_id("media_player", "device_123")
        assert entity_id == "media_player.device_123"

        entity_id = create_entity_id("remote", "my_device")
        assert entity_id == "remote.my_device"

        entity_id = create_entity_id("custom_type", "custom_id")
        assert entity_id == "custom_type.custom_id"

    def test_create_entity_id_various_device_ids(self):
        """Test create_entity_id with various device ID formats."""
        # Simple ID
        assert create_entity_id(EntityTypes.MEDIA_PLAYER, "dev1") == "media_player.dev1"

        # ID with underscores
        assert (
            create_entity_id(EntityTypes.MEDIA_PLAYER, "my_device_123")
            == "media_player.my_device_123"
        )

        # ID with dashes
        assert (
            create_entity_id(EntityTypes.REMOTE, "device-abc-123")
            == "remote.device-abc-123"
        )

        # Numeric ID
        assert create_entity_id(EntityTypes.SWITCH, "12345") == "switch.12345"

    def test_create_entity_id_with_sub_entity(self):
        """Test creating entity ID with optional sub-entity parameter."""
        # Hub with multiple lights
        entity_id = create_entity_id(EntityTypes.LIGHT, "hub_1", "bedroom_light")
        assert entity_id == "light.hub_1.bedroom_light"

        # Multi-zone receiver
        entity_id = create_entity_id(EntityTypes.MEDIA_PLAYER, "receiver_abc", "zone_2")
        assert entity_id == "media_player.receiver_abc.zone_2"

        # String entity type with sub-entity
        entity_id = create_entity_id("light", "device_123", "light_1")
        assert entity_id == "light.device_123.light_1"

    def test_create_entity_id_sub_entity_with_various_formats(self):
        """Test sub-entity parameter with various ID formats."""
        # Numeric sub-entity
        assert (
            create_entity_id(EntityTypes.LIGHT, "hub_main", "1") == "light.hub_main.1"
        )

        # Sub-entity with underscores
        assert (
            create_entity_id(EntityTypes.SWITCH, "hub_1", "switch_bedroom_1")
            == "switch.hub_1.switch_bedroom_1"
        )

        # Sub-entity with dashes
        assert (
            create_entity_id(EntityTypes.COVER, "hub-abc", "cover-1")
            == "cover.hub-abc.cover-1"
        )

        # Complex nested structure
        assert (
            create_entity_id(EntityTypes.SENSOR, "bridge_123", "temp_sensor_kitchen")
            == "sensor.bridge_123.temp_sensor_kitchen"
        )


class TestHubBasedIntegration:
    """Tests for hub-based integrations with require_connection_before_registry=True."""

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_hub_based_new_device(self):
        """Test subscribe entities with hub-based integration for new device."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Mock config manager to return device config
        driver.config_manager = MagicMock()
        driver.config_manager.get = MagicMock(
            return_value=DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        )

        entity_ids = ["media_player.dev1"]

        # Mock configured_entities.get to return entity info
        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_subscribe_entities(entity_ids)

        # Device should be added and connected
        assert "dev1" in driver._configured_devices
        device = driver._configured_devices["dev1"]
        assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_hub_based_existing_disconnected_device(self):
        """Test subscribe entities reconnects disconnected hub device."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Mock config manager
        driver.config_manager = MagicMock()
        driver.config_manager.get = MagicMock(
            return_value=DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        )

        # Add a device that's not connected
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver._add_device_instance(config)
        device = driver._configured_devices["dev1"]
        assert device.is_connected is False

        entity_ids = ["media_player.dev1"]

        # Mock configured_entities.get to return entity info
        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_subscribe_entities(entity_ids)

        # Device should be connected
        assert device.is_connected is True

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_hub_based_no_config(self):
        """Test subscribe entities with hub-based when device config not found."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        # Config returns None
        driver.config_manager = MagicMock()
        driver.config_manager.get = MagicMock(return_value=None)

        entity_ids = ["media_player.dev1"]

        await driver.on_subscribe_entities(entity_ids)

        # Device should not be added
        assert "dev1" not in driver._configured_devices

    @pytest.mark.asyncio
    async def test_on_device_added_hub_based(self):
        """Test on_device_added schedules async task for hub-based integration."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        # Call on_device_added
        driver.on_device_added(config)

        # Give the background task time to run
        await asyncio.sleep(0.1)

        # Device should be added and connected
        assert "dev1" in driver._configured_devices
        device = driver._configured_devices["dev1"]
        assert device.is_connected is True


class TestAsyncDeviceMethods:
    """Tests for async device management methods."""

    @pytest.mark.asyncio
    async def test_async_add_configured_device_success(self):
        """Test async_add_configured_device succeeds when device connects."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        result = await driver.async_add_configured_device(config)

        assert result is True
        assert "dev1" in driver._configured_devices
        assert driver._configured_devices["dev1"].is_connected is True
        # Check entities were registered
        assert len(driver.api.available_entities._entities) > 0

    @pytest.mark.asyncio
    async def test_async_add_configured_device_failure(self):
        """Test async_add_configured_device fails when device doesn't connect."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")

        # Add device first, then mock its connect to fail
        driver._add_device_instance(config)
        device = driver._configured_devices["dev1"]

        async def mock_connect():
            return False

        device.connect = mock_connect

        result = await driver.async_add_configured_device(config)

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_device_connected_already_connected(self):
        """Test _ensure_device_connected returns True when device already connected."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver._add_device_instance(config)
        device = driver._configured_devices["dev1"]
        await device.connect()

        result = await driver._ensure_device_connected("dev1")

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_device_connected_not_found(self):
        """Test _ensure_device_connected returns False when device not found."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.set_device_state = AsyncMock()

        result = await driver._ensure_device_connected("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_device_connected_with_retries(self):
        """Test _ensure_device_connected retries on failure."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver._add_device_instance(config)
        device = driver._configured_devices["dev1"]

        # Make connect fail twice then succeed
        connect_count = 0

        async def mock_connect():
            nonlocal connect_count
            connect_count += 1
            if connect_count < 3:
                return False
            device._connected = True
            return True

        device.connect = mock_connect

        result = await driver._ensure_device_connected("dev1")

        assert result is True
        assert connect_count == 3

    @pytest.mark.asyncio
    async def test_ensure_device_connected_all_retries_fail(self):
        """Test _ensure_device_connected returns False when all retries fail."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver._add_device_instance(config)
        device = driver._configured_devices["dev1"]

        # Make connect always fail
        async def mock_connect():
            return False

        device.connect = mock_connect

        result = await driver._ensure_device_connected("dev1")

        assert result is False


class TestAsyncRegisterEntities:
    """Tests for async_register_available_entities."""

    @pytest.mark.asyncio
    async def test_async_register_warns_when_not_overridden(self, caplog):
        """Test async_register_available_entities warns when require_connection_before_registry is True."""
        import logging

        caplog.set_level(logging.WARNING)

        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=True,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        device = DeviceForTests(config, loop)

        await driver.async_register_available_entities(config, device)

        # Should have logged a warning
        assert (
            "async_register_available_entities() called but not overridden"
            in caplog.text
        )

    @pytest.mark.asyncio
    async def test_async_register_no_warn_when_flag_false(self, caplog):
        """Test async_register_available_entities doesn't warn when flag is False."""
        import logging

        caplog.set_level(logging.WARNING)

        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            DeviceForTests,
            [media_player.MediaPlayer],
            require_connection_before_registry=False,
            loop=loop,
        )
        driver.api = MagicMock()
        driver.api.available_entities = MockEntityCollection()

        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        device = DeviceForTests(config, loop)

        await driver.async_register_available_entities(config, device)

        # Should NOT have logged a warning
        assert (
            "async_register_available_entities() called but not overridden"
            not in caplog.text
        )


class TestRefreshEntityState:
    """Tests for refresh_entity_state with different entity types."""

    def _create_driver(self):
        """Create a driver for refresh_entity_state testing."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()
        return driver

    @pytest.mark.asyncio
    async def test_refresh_entity_state_device_not_found(self):
        """Test refresh_entity_state when device not found."""
        driver = self._create_driver()
        driver.api.configured_entities.get = MagicMock(return_value=None)

        # Should not raise
        await driver.refresh_entity_state("media_player.nonexistent")

    @pytest.mark.asyncio
    async def test_refresh_entity_state_entity_not_configured(self):
        """Test refresh_entity_state when entity not configured."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        driver.api.configured_entities.get = MagicMock(return_value=None)

        # Should not raise
        await driver.refresh_entity_state("media_player.dev1")

    @pytest.mark.asyncio
    async def test_refresh_entity_state_media_player(self):
        """Test refresh_entity_state for media_player entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "playing"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_button(self):
        """Test refresh_entity_state for button entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.BUTTON
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_light(self):
        """Test refresh_entity_state for light entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.LIGHT
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_switch(self):
        """Test refresh_entity_state for switch entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.SWITCH
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_climate(self):
        """Test refresh_entity_state for climate entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.CLIMATE
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_cover(self):
        """Test refresh_entity_state for cover entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.COVER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_remote(self):
        """Test refresh_entity_state for remote entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.REMOTE
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_sensor(self):
        """Test refresh_entity_state for sensor entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()
        device._state = "on"

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.SENSOR
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        driver.api.configured_entities.update_attributes.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_entity_state_disconnected(self):
        """Test refresh_entity_state when device is disconnected."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        # Device is not connected

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)

        await driver.refresh_entity_state("media_player.dev1")

        # Should update with UNAVAILABLE state
        driver.api.configured_entities.update_attributes.assert_called_once()


class TestOnSubscribeEntitiesEdgeCases:
    """Tests for on_subscribe_entities edge cases."""

    def _create_driver(self):
        """Create a driver for subscribe testing."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()
        return driver

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_empty_list(self):
        """Test on_subscribe_entities with empty entity list."""
        driver = self._create_driver()
        await driver.on_subscribe_entities([])

        # Should return early without error
        assert len(driver._configured_devices) == 0

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_invalid_entity_id(self):
        """Test on_subscribe_entities with invalid entity ID format raises ValueError."""
        driver = self._create_driver()
        # Entity ID without dots can't be parsed and should raise ValueError
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            await driver.on_subscribe_entities(["invalid_entity_id"])

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_no_device_config(self):
        """Test on_subscribe_entities when device config not found."""
        driver = self._create_driver()
        driver.config_manager = MagicMock()
        driver.config_manager.get = MagicMock(return_value=None)

        entity_ids = ["media_player.dev1"]

        # Mock configured_entities.get to return None (not configured yet)
        driver.api.configured_entities.get = MagicMock(return_value=None)

        await driver.on_subscribe_entities(entity_ids)

        # Should not add any device
        assert "dev1" not in driver._configured_devices


class TestDeviceEventHandlersEntityTypes:
    """Tests for device event handlers with different entity types."""

    def _create_driver(self):
        """Create a driver for event handler testing."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()
        return driver

    @pytest.mark.asyncio
    async def test_on_device_connected_different_entity_types(self):
        """Test on_device_connected updates various entity types."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        device._state = "on"

        # Test with different entity types
        for entity_type in [
            EntityTypes.BUTTON,
            EntityTypes.CLIMATE,
            EntityTypes.COVER,
            EntityTypes.LIGHT,
            EntityTypes.REMOTE,
            EntityTypes.SENSOR,
            EntityTypes.SWITCH,
            EntityTypes.IR_EMITTER,
            EntityTypes.VOICE_ASSISTANT,
        ]:
            mock_entity = MagicMock()
            mock_entity.entity_type = entity_type
            driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
            driver.api.configured_entities.update_attributes = MagicMock()

            await driver.on_device_connected("dev1")

            driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_disconnected_different_entity_types(self):
        """Test on_device_disconnected updates various entity types."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Test with different entity types
        for entity_type in [
            EntityTypes.BUTTON,
            EntityTypes.CLIMATE,
            EntityTypes.COVER,
            EntityTypes.LIGHT,
            EntityTypes.REMOTE,
            EntityTypes.SENSOR,
            EntityTypes.SWITCH,
            EntityTypes.IR_EMITTER,
            EntityTypes.VOICE_ASSISTANT,
        ]:
            mock_entity = MagicMock()
            mock_entity.entity_type = entity_type
            driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
            driver.api.configured_entities.update_attributes = MagicMock()

            await driver.on_device_disconnected("dev1")

            driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_connection_error_different_entity_types(self):
        """Test on_device_connection_error updates various entity types."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Test with different entity types
        for entity_type in [
            EntityTypes.BUTTON,
            EntityTypes.CLIMATE,
            EntityTypes.COVER,
            EntityTypes.LIGHT,
            EntityTypes.REMOTE,
            EntityTypes.SENSOR,
            EntityTypes.SWITCH,
            EntityTypes.IR_EMITTER,
            EntityTypes.VOICE_ASSISTANT,
        ]:
            mock_entity = MagicMock()
            mock_entity.entity_type = entity_type
            driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
            driver.api.configured_entities.update_attributes = MagicMock()

            await driver.on_device_connection_error("dev1", "Test error")

            driver.api.configured_entities.update_attributes.assert_called()


class TestOnDeviceUpdateEntityTypes:
    """Tests for on_device_update with various entity types."""

    def _create_driver(self):
        """Create a driver for update testing."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()
        return driver

    @pytest.mark.asyncio
    async def test_on_device_update_button(self):
        """Test on_device_update for button entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.BUTTON
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update("dev1", {"state": "on"})

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_climate(self):
        """Test on_device_update for climate entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.CLIMATE
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update(
            "dev1",
            {
                "state": "on",
                "current_temperature": 22,
                "target_temperature": 24,
            },
        )

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_cover(self):
        """Test on_device_update for cover entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.COVER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update(
            "dev1",
            {
                "state": "open",
                "position": 75,
            },
        )

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_light(self):
        """Test on_device_update for light entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.LIGHT
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update(
            "dev1",
            {
                "state": "on",
                "brightness": 255,
                "hue": 180,
                "saturation": 100,
            },
        )

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_remote(self):
        """Test on_device_update for remote entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.REMOTE
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update("dev1", {"state": "on"})

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_sensor(self):
        """Test on_device_update for sensor entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.SENSOR
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update(
            "dev1",
            {
                "state": "on",
                "value": 42,
                "unit": "°C",
            },
        )

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_switch(self):
        """Test on_device_update for switch entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.SWITCH
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update("dev1", {"state": "on"})

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_ir_emitter(self):
        """Test on_device_update for IR emitter entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.IR_EMITTER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update("dev1", {"state": "on"})

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_voice_assistant(self):
        """Test on_device_update for voice assistant entity."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.VOICE_ASSISTANT
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        await driver.on_device_update("dev1", {"state": "on"})

        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_update_unknown_entity_type(self, caplog):
        """Test on_device_update with unknown entity type logs warning."""
        import logging

        caplog.set_level(logging.WARNING)

        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = "unknown_type"
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)

        await driver.on_device_update("dev1", {"state": "on"})

        assert "Unknown entity type" in caplog.text

    @pytest.mark.asyncio
    async def test_on_device_update_none_update(self, caplog):
        """Test on_device_update with None update logs warning."""
        import logging

        caplog.set_level(logging.WARNING)

        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        await driver.on_device_update("dev1", None)

        assert "Received None update" in caplog.text


class TestDriverCoverageGaps:
    """Additional tests to fill coverage gaps."""

    def _create_driver(self):
        """Create a driver for testing."""
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(DeviceForTests, [media_player.MediaPlayer], loop=loop)
        driver.api = MagicMock()
        driver.api.configured_entities = MagicMock()
        driver.api.available_entities = MockEntityCollection()
        driver.api.set_device_state = AsyncMock()
        return driver

    @pytest.mark.asyncio
    async def test_on_device_connected_unknown_device(self, caplog):
        """Test on_device_connected with unknown device logs warning."""
        import logging

        caplog.set_level(logging.WARNING)

        driver = self._create_driver()
        # Don't add any device - call on_device_connected with unknown device
        await driver.on_device_connected("unknown_device")

        assert "Device unknown_device is not configured" in caplog.text

    @pytest.mark.asyncio
    async def test_on_device_update_media_player_clears_media_when_off(self):
        """Test on_device_update clears media attributes when media player turns OFF."""
        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        mock_entity = MagicMock()
        mock_entity.entity_type = EntityTypes.MEDIA_PLAYER
        driver.api.configured_entities.get = MagicMock(return_value=mock_entity)
        driver.api.configured_entities.contains = MagicMock(return_value=True)
        driver.api.configured_entities.update_attributes = MagicMock()

        # Send update with OFF state
        await driver.on_device_update("dev1", {"state": "OFF"})

        # Should have cleared media attributes
        call_args = driver.api.configured_entities.update_attributes.call_args
        assert call_args is not None
        attributes = call_args[0][1]

        # Check that media attributes are cleared
        assert media_player.Attributes.MEDIA_DURATION in attributes
        assert media_player.Attributes.MEDIA_POSITION in attributes
        assert media_player.Attributes.MEDIA_TITLE in attributes

    @pytest.mark.asyncio
    async def test_on_device_update_entity_not_found(self, caplog):
        """Test on_device_update when entity is not found in configured or available."""
        import logging

        caplog.set_level(logging.DEBUG)

        driver = self._create_driver()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Entity not found
        driver.api.configured_entities.get = MagicMock(return_value=None)
        driver.api.available_entities = MockEntityCollection()  # Empty

        await driver.on_device_update("dev1", {"state": "on"})

        assert "Entity not found" in caplog.text

    def test_entity_type_from_entity_id_no_period(self):
        """Test entity_type_from_entity_id with entity_id that has no period raises ValueError."""
        driver = self._create_driver()
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            driver.entity_type_from_entity_id("no_period")

    def test_entity_type_from_entity_id_empty(self):
        """Test entity_type_from_entity_id with empty entity_id."""
        driver = self._create_driver()
        result = driver.entity_type_from_entity_id("")
        assert result is None

    def test_device_from_entity_id_no_period(self):
        """Test device_from_entity_id with entity_id that has no period raises ValueError."""
        driver = self._create_driver()
        with pytest.raises(ValueError, match="does not contain the expected separator"):
            driver.device_from_entity_id("no_period")

    def test_device_from_entity_id_empty(self):
        """Test device_from_entity_id with empty entity_id."""
        driver = self._create_driver()
        result = driver.device_from_entity_id("")
        assert result is None

    def test_sub_device_from_entity_id_no_sub_device(self):
        """Test sub_device_from_entity_id when no sub-device present."""
        driver = self._create_driver()
        result = driver.sub_device_from_entity_id("media_player.dev1")
        assert result is None

    def test_sub_device_from_entity_id_with_sub_device(self):
        """Test sub_device_from_entity_id with sub-device."""
        driver = self._create_driver()
        result = driver.sub_device_from_entity_id("media_player.dev1.zone2")
        assert result == "zone2"

    def test_remove_device_not_found(self, caplog):
        """Test remove_device when device is not found."""
        import logging

        caplog.set_level(logging.WARNING)

        driver = self._create_driver()
        driver.remove_device("nonexistent")

        assert "Device nonexistent not found" in caplog.text


class TestCreateEntities:
    """Tests for create_entities() override pattern."""

    def test_create_entities_default_uses_entity_classes(self, mock_loop):
        """Test default create_entities instantiates from entity_classes."""

        # Create a custom entity class that accepts (device_config, device)
        class TestMediaPlayer(media_player.MediaPlayer):
            def __init__(self, device_config, device):
                super().__init__(
                    f"media_player.{device_config.identifier}",
                    device_config.name,
                    features=[media_player.Features.ON_OFF],
                    attributes={
                        media_player.Attributes.STATE: media_player.States.UNKNOWN
                    },
                )

        class MinimalDriver(BaseIntegrationDriver):
            pass

        # Pass actual entity class
        driver = MinimalDriver(
            device_class=DeviceForTests,
            entity_classes=[TestMediaPlayer],
            loop=mock_loop,
        )
        config = DeviceConfigForTests("test", "Test Device", "192.168.1.1")
        device = DeviceForTests(config, loop=mock_loop)

        entities = driver.create_entities(config, device)
        # Should use default: instantiate from entity_classes
        assert len(entities) == 1
        assert isinstance(entities[0], media_player.MediaPlayer)
        assert entities[0].id == "media_player.test"

    def test_create_entities_override_for_multiple_zones(self, mock_loop):
        """Test overriding create_entities for multiple zones pattern."""

        @dataclass
        class ZoneConfig:
            id: str
            name: str

        @dataclass
        class MultiZoneConfig:
            identifier: str
            name: str
            address: str
            zones: list[ZoneConfig]

        class MultiZoneDriver(BaseIntegrationDriver):
            def create_entities(self, device_config, device):
                entities = []
                for zone in device_config.zones:
                    entities.append(
                        media_player.MediaPlayer(
                            f"media_player.{device_config.identifier}_zone_{zone.id}",
                            f"{device_config.name} {zone.name}",
                            features=[media_player.Features.ON_OFF],
                            attributes={
                                media_player.Attributes.STATE: media_player.States.UNKNOWN
                            },
                        )
                    )
                return entities

        driver = MultiZoneDriver(
            device_class=DeviceForTests,
            entity_classes=EntityTypes.MEDIA_PLAYER,
            loop=mock_loop,
        )
        config = MultiZoneConfig(
            "receiver",
            "AV Receiver",
            "192.168.1.100",
            [
                ZoneConfig("1", "Main"),
                ZoneConfig("2", "Zone 2"),
                ZoneConfig("3", "Zone 3"),
            ],
        )
        device = DeviceForTests(config, loop=mock_loop)

        entities = driver.create_entities(config, device)
        assert len(entities) == 3
        assert entities[0].id == "media_player.receiver_zone_1"
        assert entities[0].name["en"] == "AV Receiver Main"
        assert entities[1].id == "media_player.receiver_zone_2"
        assert entities[2].id == "media_player.receiver_zone_3"

    def test_create_entities_override_hub_discovery(self, mock_loop):
        """Test overriding create_entities for hub discovery with multiple entity types."""
        from ucapi import light, cover

        class HubDriver(BaseIntegrationDriver):
            def create_entities(self, device_config, device):
                entities = []
                # Simulate hub discovery
                entities.append(
                    light.Light(
                        f"light.{device_config.identifier}_light1",
                        "Living Room Light",
                        features=[light.Features.ON_OFF, light.Features.DIM],
                        attributes={light.Attributes.STATE: light.States.OFF},
                    )
                )
                entities.append(
                    light.Light(
                        f"light.{device_config.identifier}_light2",
                        "Bedroom Light",
                        features=[light.Features.ON_OFF],
                        attributes={light.Attributes.STATE: light.States.OFF},
                    )
                )
                entities.append(
                    cover.Cover(
                        f"cover.{device_config.identifier}_cover1",
                        "Living Room Blinds",
                        features=[cover.Features.OPEN, cover.Features.CLOSE],
                        attributes={cover.Attributes.STATE: cover.States.CLOSED},
                    )
                )
                return entities

        driver = HubDriver(
            device_class=DeviceForTests,
            entity_classes=[EntityTypes.LIGHT, EntityTypes.COVER],
            loop=mock_loop,
        )
        config = DeviceConfigForTests("hub1", "Smart Hub", "192.168.1.50")
        device = DeviceForTests(config, loop=mock_loop)

        entities = driver.create_entities(config, device)
        assert len(entities) == 3
        assert entities[0].id == "light.hub1_light1"
        assert entities[1].id == "light.hub1_light2"
        assert entities[2].id == "cover.hub1_cover1"

    def test_create_entities_conditional_based_on_capabilities(self, mock_loop):
        """Test conditional entity creation based on device capabilities."""
        from ucapi import remote

        @dataclass
        class CapableDeviceConfig:
            identifier: str
            name: str
            address: str
            supports_playback: bool
            supports_remote: bool

        class CapableDevice(DeviceForTests):
            def __init__(self, device_config, loop):
                super().__init__(device_config, loop)
                self.supports_playback = device_config.supports_playback
                self.supports_remote = device_config.supports_remote

        class ConditionalDriver(BaseIntegrationDriver):
            def create_entities(self, device_config, device):
                entities = []
                if device.supports_playback:
                    entities.append(
                        media_player.MediaPlayer(
                            f"media_player.{device_config.identifier}",
                            device_config.name,
                            features=[media_player.Features.ON_OFF],
                            attributes={
                                media_player.Attributes.STATE: media_player.States.UNKNOWN
                            },
                        )
                    )
                if device.supports_remote:
                    entities.append(
                        remote.Remote(
                            f"remote.{device_config.identifier}",
                            device_config.name,
                            features=[remote.Features.SEND_CMD],
                            attributes={remote.Attributes.STATE: remote.States.UNKNOWN},
                        )
                    )
                return entities

        driver = ConditionalDriver(
            device_class=CapableDevice,
            entity_classes=[EntityTypes.MEDIA_PLAYER, EntityTypes.REMOTE],
            loop=mock_loop,
        )

        # Test with both capabilities
        config_both = CapableDeviceConfig(
            "test1", "Test Both", "192.168.1.1", True, True
        )
        device_both = CapableDevice(config_both, loop=mock_loop)
        entities = driver.create_entities(config_both, device_both)
        assert len(entities) == 2

        # Test with only playback
        config_playback = CapableDeviceConfig(
            "test2", "Test Playback", "192.168.1.2", True, False
        )
        device_playback = CapableDevice(config_playback, loop=mock_loop)
        entities = driver.create_entities(config_playback, device_playback)
        assert len(entities) == 1
        assert entities[0].id == "media_player.test2"

        # Test with neither
        config_none = CapableDeviceConfig(
            "test3", "Test None", "192.168.1.3", False, False
        )
        device_none = CapableDevice(config_none, loop=mock_loop)
        entities = driver.create_entities(config_none, device_none)
        assert len(entities) == 0
