"""Tests for BaseIntegrationDriver."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
import ucapi
from ucapi import media_player

from ucapi_framework.device import BaseDeviceInterface, DeviceEvents
from ucapi_framework.driver import BaseIntegrationDriver


@dataclass
class DeviceConfigForTests:
    """Test device configuration."""

    identifier: str
    name: str
    address: str


class DeviceForTests(BaseDeviceInterface):
    """Test device implementation."""

    def __init__(self, device_config, loop=None):
        super().__init__(device_config, loop)
        self.connected = False

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

    async def connect(self) -> None:
        self.connected = True
        self.events.emit(DeviceEvents.CONNECTED, self.identifier)

    async def disconnect(self) -> None:
        self.connected = False
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)


class EntityForTests(media_player.MediaPlayer):
    """Test entity class."""

    pass


class ConcreteDriver(BaseIntegrationDriver[DeviceForTests, DeviceConfigForTests]):
    """Concrete driver implementation for testing."""

    def device_from_entity_id(self, entity_id: str) -> str | None:
        """Extract device ID from entity ID."""
        # Entity ID format: "media_player.device_id"
        if "." in entity_id:
            return entity_id.split(".", 1)[1]
        return None

    def get_entity_ids_for_device(self, device_id: str) -> list[str]:
        """Get entity IDs for a device."""
        return [f"media_player.{device_id}"]

    def map_device_state(self, device_state) -> media_player.States:
        """Map device state to media player state."""
        if device_state == "playing":
            return media_player.States.PLAYING
        elif device_state == "paused":
            return media_player.States.PAUSED
        elif device_state == "on":
            return media_player.States.ON
        elif device_state == "off":
            return media_player.States.OFF
        return media_player.States.UNKNOWN

    def create_entities(
        self, device_config: DeviceConfigForTests, device: DeviceForTests
    ) -> list:
        """Create entities for a device."""
        entity = media_player.MediaPlayer(
            f"media_player.{device_config.identifier}",
            device_config.name,
            [media_player.Features.ON_OFF],
            {media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )
        return [entity]


@pytest.fixture
def mock_loop():
    """Create a mock event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def driver(mock_loop):
    """Create a test driver instance."""
    driver = ConcreteDriver(
        loop=mock_loop,
        device_class=DeviceForTests,
        entity_classes=[media_player.MediaPlayer],
    )
    # Mock the API
    driver.api = MagicMock()
    driver.api.configured_entities = MagicMock()
    driver.api.available_entities = MagicMock()
    driver.api.set_device_state = AsyncMock()
    return driver


class TestBaseIntegrationDriver:
    """Tests for BaseIntegrationDriver."""

    def test_init(self, mock_loop):
        """Test driver initialization."""
        driver = ConcreteDriver(
            loop=mock_loop,
            device_class=DeviceForTests,
            entity_classes=[media_player.MediaPlayer],
        )

        assert driver._device_class == DeviceForTests
        assert driver._entity_classes == [media_player.MediaPlayer]
        assert driver._configured_devices == {}

    @pytest.mark.asyncio
    async def test_on_r2_connect_cmd(self, driver, mock_loop):
        """Test Remote Two connect command."""
        # Add a device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        await driver.on_r2_connect_cmd()

        # Should set device state
        driver.api.set_device_state.assert_called_once_with(
            ucapi.DeviceStates.CONNECTED
        )

        # Should connect all devices
        device = driver._configured_devices["dev1"]
        assert device.connected is True

    @pytest.mark.asyncio
    async def test_on_r2_disconnect_cmd(self, driver):
        """Test Remote Two disconnect command."""
        # Add and connect a device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        await device.connect()

        await driver.on_r2_disconnect_cmd()

        assert device.connected is False

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

        assert dev1.connected is False
        assert dev2.connected is False

    @pytest.mark.asyncio
    async def test_on_r2_exit_standby(self, driver):
        """Test exiting standby mode."""
        # Add devices
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        await driver.on_r2_exit_standby()

        device = driver._configured_devices["dev1"]
        assert device.connected is True

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_existing_device(self, driver):
        """Test subscribing to entities with existing configured device."""
        # Add device
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)
        device = driver._configured_devices["dev1"]
        device._state = "on"

        # Mock configured entity
        mock_entity = Mock()
        driver.api.configured_entities.get.return_value = mock_entity

        await driver.on_subscribe_entities(["media_player.dev1"])

        # Should update entity state
        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_subscribe_entities_new_device(self, driver):
        """Test subscribing to entities for a new device."""
        # Mock config
        driver.config = MagicMock()
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.config.get.return_value = config

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
        assert device.connected is False

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

        # Mock entity
        driver.api.configured_entities.get.return_value = Mock()

        device = driver._configured_devices["dev1"]
        device._state = "on"

        await driver.on_device_connected("dev1")

        # Should update entity attributes and set device state
        driver.api.configured_entities.update_attributes.assert_called()
        driver.api.set_device_state.assert_called_with(ucapi.DeviceStates.CONNECTED)

    @pytest.mark.asyncio
    async def test_on_device_disconnected(self, driver):
        """Test device disconnected event handler."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Mock entity
        driver.api.configured_entities.get.return_value = Mock()

        await driver.on_device_disconnected("dev1")

        # Should update entity to UNAVAILABLE
        driver.api.configured_entities.update_attributes.assert_called()

    @pytest.mark.asyncio
    async def test_on_device_connection_error(self, driver):
        """Test device connection error handler."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        # Mock entity
        driver.api.configured_entities.get.return_value = Mock()

        await driver.on_device_connection_error("dev1", "Connection timeout")

        # Should update entity to UNAVAILABLE and set device state to ERROR
        driver.api.configured_entities.update_attributes.assert_called()
        driver.api.set_device_state.assert_called_with(ucapi.DeviceStates.ERROR)

    def test_get_device_config(self, driver):
        """Test getting device configuration."""
        config = DeviceConfigForTests("dev1", "Device 1", "192.168.1.1")
        driver.add_configured_device(config, connect=False)

        retrieved = driver.get_device_config("dev1")

        assert retrieved.identifier == "dev1"
        assert retrieved.name == "Device 1"

    def test_get_device_config_from_config_manager(self, driver):
        """Test getting device configuration from config manager."""
        driver.config = MagicMock()
        config = DeviceConfigForTests("dev2", "Device 2", "192.168.1.2")
        driver.config.get.return_value = config

        retrieved = driver.get_device_config("dev2")

        assert retrieved.identifier == "dev2"
        driver.config.get.assert_called_once_with("dev2")

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

    def test_device_from_entity_id(self, driver):
        """Test extracting device ID from entity ID."""
        device_id = driver.device_from_entity_id("media_player.dev1")

        assert device_id == "dev1"

    def test_get_entity_ids_for_device(self, driver):
        """Test getting entity IDs for a device."""
        entity_ids = driver.get_entity_ids_for_device("dev1")

        assert entity_ids == ["media_player.dev1"]

    def test_map_device_state(self, driver):
        """Test mapping device state to media player state."""
        assert driver.map_device_state("playing") == media_player.States.PLAYING
        assert driver.map_device_state("paused") == media_player.States.PAUSED
        assert driver.map_device_state("on") == media_player.States.ON
        assert driver.map_device_state("off") == media_player.States.OFF
        assert driver.map_device_state("unknown") == media_player.States.UNKNOWN

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
