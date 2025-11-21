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
        """Create entities for a device - uses standard entity ID format."""
        entity = media_player.MediaPlayer(
            f"media_player.{device_config.identifier}",
            device_config.name,
            [media_player.Features.ON_OFF],
            {media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )
        return [entity]

    def device_from_entity_id(self, entity_id: str) -> str | None:
        """
        Extract device ID from entity ID.

        Overridden because create_entities is overridden.
        Since we use the standard format (entity_type.device_id), we delegate to the parent.
        """
        return super().device_from_entity_id(entity_id)


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

    def clear(self):
        self._entities.clear()

    def __iter__(self):
        return iter(self._entities)


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
    driver.api.available_entities = MockEntityCollection()
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
    async def test_on_r2_connect_cmd(self):
        """Test Remote Two connect command."""
        # Use real loop for this test since we need background tasks
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            loop=loop,
            device_class=DeviceForTests,
            entity_classes=[media_player.MediaPlayer],
        )
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
        assert device.connected is True

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
        driver = ConcreteDriver(
            loop=loop,
            device_class=DeviceForTests,
            entity_classes=[media_player.MediaPlayer],
        )
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

        assert device.connected is False

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

        assert dev1.connected is False
        assert dev2.connected is False

    @pytest.mark.asyncio
    async def test_on_r2_exit_standby(self):
        """Test exiting standby mode."""
        # Use real loop for this test since we need background tasks
        loop = asyncio.get_event_loop()
        driver = ConcreteDriver(
            loop=loop,
            device_class=DeviceForTests,
            entity_classes=[media_player.MediaPlayer],
        )
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
        assert device.connected is True

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

        # Mock configured entity
        mock_entity = Mock()
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

        # Give any background event handler tasks time to complete
        await asyncio.sleep(0.01)

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

    def test_device_from_entity_id_default_implementation(self, mock_loop):
        """Test the default device_from_entity_id implementation."""

        class MinimalDriver(BaseIntegrationDriver):
            """Minimal driver using default device_from_entity_id."""

            def get_entity_ids_for_device(self, device_id):
                return [f"media_player.{device_id}"]

        driver = MinimalDriver(
            loop=mock_loop, device_class=DeviceForTests, entity_classes=[]
        )

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
        assert driver.device_from_entity_id("invalid") is None
        assert driver.device_from_entity_id("only.one") == "one"

    def test_device_from_entity_id_requires_override_when_create_entities_overridden(
        self, mock_loop
    ):
        """Test that overriding create_entities requires overriding device_from_entity_id."""

        class DriverWithCustomEntities(BaseIntegrationDriver):
            """Driver that overrides create_entities but not device_from_entity_id."""

            def create_entities(self, device_config, device):
                # Custom entity creation with non-standard ID format
                return []

            def get_entity_ids_for_device(self, device_id):
                return [device_id]  # Custom format

        driver = DriverWithCustomEntities(
            loop=mock_loop, device_class=DeviceForTests, entity_classes=[]
        )

        # Should raise NotImplementedError with helpful message
        with pytest.raises(
            NotImplementedError,
            match="create_entities\\(\\) is overridden but device_from_entity_id\\(\\) is not",
        ):
            driver.device_from_entity_id("custom_entity_id")

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

        driver = DriverWithCustomFormat(
            loop=mock_loop, device_class=DeviceForTests, entity_classes=[]
        )

        # Should work fine with both overridden
        assert driver.device_from_entity_id("my_device_id") == "my_device_id"
        assert driver.device_from_entity_id("account_123") == "account_123"

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

        driver = MinimalDriver(
            loop=mock_loop, device_class=DeviceForTests, entity_classes=[]
        )

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


class TestEntityIdHelpers:
    """Tests for entity ID helper functions."""

    def test_create_entity_id_with_enum(self):
        """Test creating entity ID with EntityTypes enum."""
        entity_id = create_entity_id("device_123", EntityTypes.MEDIA_PLAYER)
        assert entity_id == "media_player.device_123"

        entity_id = create_entity_id("my_device", EntityTypes.REMOTE)
        assert entity_id == "remote.my_device"

        entity_id = create_entity_id("light_1", EntityTypes.LIGHT)
        assert entity_id == "light.light_1"

    def test_create_entity_id_with_string(self):
        """Test creating entity ID with string entity type."""
        entity_id = create_entity_id("device_123", "media_player")
        assert entity_id == "media_player.device_123"

        entity_id = create_entity_id("my_device", "remote")
        assert entity_id == "remote.my_device"

        entity_id = create_entity_id("custom_id", "custom_type")
        assert entity_id == "custom_type.custom_id"

    def test_create_entity_id_various_device_ids(self):
        """Test create_entity_id with various device ID formats."""
        # Simple ID
        assert create_entity_id("dev1", EntityTypes.MEDIA_PLAYER) == "media_player.dev1"

        # ID with underscores
        assert (
            create_entity_id("my_device_123", EntityTypes.MEDIA_PLAYER)
            == "media_player.my_device_123"
        )

        # ID with dashes
        assert (
            create_entity_id("device-abc-123", EntityTypes.REMOTE)
            == "remote.device-abc-123"
        )

        # Numeric ID
        assert create_entity_id("12345", EntityTypes.SWITCH) == "switch.12345"

    def test_create_entity_id_with_sub_entity(self):
        """Test creating entity ID with optional sub-entity parameter."""
        # Hub with multiple lights
        entity_id = create_entity_id("hub_1", EntityTypes.LIGHT, "bedroom_light")
        assert entity_id == "light.hub_1.bedroom_light"

        # Multi-zone receiver
        entity_id = create_entity_id("receiver_abc", EntityTypes.MEDIA_PLAYER, "zone_2")
        assert entity_id == "media_player.receiver_abc.zone_2"

        # String entity type with sub-entity
        entity_id = create_entity_id("device_123", "light", "light_1")
        assert entity_id == "light.device_123.light_1"

    def test_create_entity_id_sub_entity_with_various_formats(self):
        """Test sub-entity parameter with various ID formats."""
        # Numeric sub-entity
        assert (
            create_entity_id("hub_main", EntityTypes.LIGHT, "1") == "light.hub_main.1"
        )

        # Sub-entity with underscores
        assert (
            create_entity_id("hub_1", EntityTypes.SWITCH, "switch_bedroom_1")
            == "switch.hub_1.switch_bedroom_1"
        )

        # Sub-entity with dashes
        assert (
            create_entity_id("hub-abc", EntityTypes.COVER, "cover-1")
            == "cover.hub-abc.cover-1"
        )

        # Complex nested structure
        assert (
            create_entity_id("bridge_123", EntityTypes.SENSOR, "temp_sensor_kitchen")
            == "sensor.bridge_123.temp_sensor_kitchen"
        )
