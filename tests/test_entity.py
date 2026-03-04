"""Tests for Entity ABC."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from ucapi import media_player, sensor

from ucapi_framework.entity import Entity


class TestMediaPlayer(media_player.MediaPlayer, Entity):
    """Test media player with Entity ABC."""

    def __init__(self, entity_id, name):
        super().__init__(
            entity_id,
            name,
            features=[media_player.Features.ON_OFF],
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )


class CustomStateMediaPlayer(media_player.MediaPlayer, Entity):
    """Media player with custom state mapping."""

    def __init__(self, entity_id, name):
        super().__init__(
            entity_id,
            name,
            features=[media_player.Features.ON_OFF],
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
        )

    def map_entity_states(self, device_state):
        """Custom state mapping."""
        if device_state == "STREAM":
            return media_player.States.PLAYING
        elif device_state == "POWERING_ON":
            return media_player.States.ON
        return super().map_entity_states(device_state)


class TestSensor(sensor.Sensor, Entity):
    """Test sensor with Entity ABC."""

    def __init__(self, entity_id, name):
        super().__init__(
            entity_id,
            name,
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.UNKNOWN,
                sensor.Attributes.VALUE: 0,
            },
        )


class TestEntityABC:
    """Test Entity ABC functionality."""

    @pytest.fixture
    def mock_api(self):
        """Provide a mock API for all tests."""
        return MagicMock()

    def test_entity_api_set_by_framework(self, mock_api):
        """Test that Entity _api is set by framework after construction."""
        # Create entity without api
        entity = TestMediaPlayer("media_player.test", "Test Player")

        # Framework sets _api after construction
        entity._api = mock_api  # noqa: SLF001

        # Verify it works
        assert entity._api is mock_api  # noqa: SLF001

    def test_map_entity_states_default(self, mock_api):
        """Test default state mapping behavior."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Test common state mappings
        assert (
            entity.map_entity_states("UNAVAILABLE") == media_player.States.UNAVAILABLE
        )
        assert entity.map_entity_states("UNKNOWN") == media_player.States.UNKNOWN
        assert entity.map_entity_states("ON") == media_player.States.ON
        assert entity.map_entity_states("MENU") == media_player.States.ON
        assert entity.map_entity_states("IDLE") == media_player.States.ON
        assert entity.map_entity_states("OFF") == media_player.States.OFF
        assert entity.map_entity_states("POWER_OFF") == media_player.States.OFF
        assert entity.map_entity_states("PLAYING") == media_player.States.PLAYING
        assert entity.map_entity_states("PLAY") == media_player.States.PLAYING
        assert entity.map_entity_states("PAUSED") == media_player.States.PAUSED
        assert entity.map_entity_states("STANDBY") == media_player.States.STANDBY
        assert entity.map_entity_states("BUFFERING") == media_player.States.BUFFERING

        # Test case insensitivity
        assert entity.map_entity_states("playing") == media_player.States.PLAYING
        assert entity.map_entity_states("off") == media_player.States.OFF

        # Test unknown state
        assert entity.map_entity_states("RANDOM_STATE") == media_player.States.UNKNOWN

        # Test None handling
        assert entity.map_entity_states(None) == media_player.States.UNKNOWN

    def test_map_entity_states_custom_override(self, mock_api):
        """Test custom state mapping override."""
        entity = CustomStateMediaPlayer("media_player.custom", "Custom Player")
        entity._api = mock_api  # noqa: SLF001

        # Test custom mappings
        assert entity.map_entity_states("STREAM") == media_player.States.PLAYING
        assert entity.map_entity_states("POWERING_ON") == media_player.States.ON

        # Test that default mappings still work
        assert entity.map_entity_states("OFF") == media_player.States.OFF
        assert entity.map_entity_states("PAUSED") == media_player.States.PAUSED

    def test_filter_changed_attributes(self, mock_api):
        """Test attribute filtering."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Mock the configured entity
        mock_configured_entity = MagicMock()
        mock_configured_entity.attributes = {
            media_player.Attributes.STATE: media_player.States.OFF,
            media_player.Attributes.VOLUME: 50,
        }
        mock_api.configured_entities.get.return_value = mock_configured_entity

        # Test filtering - only changed values should be returned
        update = {
            media_player.Attributes.STATE: media_player.States.PLAYING,  # Changed
            media_player.Attributes.VOLUME: 50,  # Unchanged
            media_player.Attributes.MUTED: False,  # New attribute
        }

        filtered = entity.filter_changed_attributes(update)
        assert filtered == {
            media_player.Attributes.STATE: media_player.States.PLAYING,
            media_player.Attributes.MUTED: False,
        }

    def test_filter_changed_attributes_entity_not_configured(self, mock_api):
        """Test that filter returns all attributes if entity not configured."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Mock the API to return None for configured entity
        mock_api.configured_entities.get.return_value = None

        update = {
            media_player.Attributes.STATE: media_player.States.PLAYING,
            media_player.Attributes.VOLUME: 75,
        }

        filtered = entity.filter_changed_attributes(update)
        # Should return all attributes if entity not found
        assert filtered == update

    def test_update_attributes_with_filtering(self, mock_api):
        """Test update_attributes with automatic filtering."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Mock the configured entity
        mock_configured_entity = MagicMock()
        mock_configured_entity.attributes = {
            media_player.Attributes.STATE: media_player.States.OFF,
        }
        mock_api.configured_entities.get.return_value = mock_configured_entity

        # Update with mixed changed/unchanged attributes
        update = {
            media_player.Attributes.STATE: media_player.States.PLAYING,  # Changed
            media_player.Attributes.VOLUME: 50,  # New
        }

        entity.update_attributes(update)

        # Should only update changed attributes
        mock_api.configured_entities.update_attributes.assert_called_once_with(
            "media_player.test", update
        )

    def test_update_attributes_force(self, mock_api):
        """Test update_attributes with force=True bypasses filtering."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Update with force=True should skip filtering
        update = {
            media_player.Attributes.STATE: media_player.States.PLAYING,
            media_player.Attributes.VOLUME: 50,
        }

        entity.update_attributes(update, force=True)

        # Should update all attributes without calling filter
        mock_api.configured_entities.update_attributes.assert_called_once_with(
            "media_player.test", update
        )

    def test_update_with_dataclass(self, mock_api):
        """Test that update() converts dataclass to dict with enum keys."""
        from ucapi_framework import MediaPlayerAttributes

        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Configure entity in mock
        mock_api.configured_entities.get.return_value = MagicMock(
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN}
        )

        # Create attributes dataclass
        attrs = MediaPlayerAttributes(
            STATE=media_player.States.PLAYING, VOLUME=50, MUTED=False
        )

        # Update entity with dataclass
        entity.update(attrs)

        # Verify update_attributes was called
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args

        # Get the attributes dict that was passed
        entity_id, attributes = call_args[0]
        assert entity_id == "media_player.test"

        # Verify keys are enum objects, not strings
        assert media_player.Attributes.STATE in attributes
        assert media_player.Attributes.VOLUME in attributes
        assert media_player.Attributes.MUTED in attributes

        # Verify string keys are NOT present
        assert "STATE" not in attributes
        assert "VOLUME" not in attributes
        assert "MUTED" not in attributes

        # Verify values
        assert attributes[media_player.Attributes.STATE] == media_player.States.PLAYING
        assert attributes[media_player.Attributes.VOLUME] == 50
        assert attributes[media_player.Attributes.MUTED] is False

    def test_update_filters_none_values(self, mock_api):
        """Test that update() filters out None values from dataclass."""
        from ucapi_framework import MediaPlayerAttributes

        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Configure entity in mock
        mock_api.configured_entities.get.return_value = MagicMock(
            attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN}
        )

        # Create attributes with only some fields set (rest are None)
        attrs = MediaPlayerAttributes(STATE=media_player.States.PLAYING, VOLUME=50)

        # Update entity
        entity.update(attrs)

        # Get the attributes dict that was passed
        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]

        # Should only have STATE and VOLUME, not other None fields
        assert len(attributes) == 2
        assert media_player.Attributes.STATE in attributes
        assert media_player.Attributes.VOLUME in attributes
        # These should not be present (they were None)
        assert media_player.Attributes.MUTED not in attributes
        assert media_player.Attributes.SOURCE not in attributes

    def test_multiple_entity_types(self, mock_api):
        """Test that Entity ABC works with different entity types."""
        # Test with sensor
        sensor_entity = TestSensor("sensor.test", "Test Sensor")
        sensor_entity._api = mock_api  # noqa: SLF001
        assert sensor_entity.map_entity_states("ON") == media_player.States.ON

        # Test with media player
        mp_entity = TestMediaPlayer("media_player.test", "Test Player")
        mp_entity._api = mock_api  # noqa: SLF001
        assert mp_entity.map_entity_states("PLAYING") == media_player.States.PLAYING

        # Both should have the same Entity ABC methods
        assert hasattr(sensor_entity, "filter_changed_attributes")
        assert hasattr(mp_entity, "filter_changed_attributes")
        assert hasattr(sensor_entity, "update_attributes")
        assert hasattr(mp_entity, "update_attributes")

    def test_framework_sets_api(self):
        """Test that framework can set api after entity construction."""
        mock_api = MagicMock()

        # Create entity without api (as framework does)
        entity = TestMediaPlayer("media_player.test", "Test Player")

        # Framework sets _api after construction
        entity._api = mock_api  # noqa: SLF001

        # The api should be accessible
        assert entity._api is mock_api  # noqa: SLF001

    def test_button_attributes(self):
        """Test ButtonAttributes dataclass."""
        from ucapi import button
        from ucapi_framework import ButtonAttributes

        # Test default values
        attrs = ButtonAttributes()
        assert attrs.STATE is None

        # Test with values
        attrs = ButtonAttributes(STATE=button.States.AVAILABLE)
        assert attrs.STATE == button.States.AVAILABLE

    def test_climate_attributes(self):
        """Test ClimateAttributes dataclass."""
        from ucapi import climate
        from ucapi_framework import ClimateAttributes

        # Test default values
        attrs = ClimateAttributes()
        assert attrs.STATE is None
        assert attrs.CURRENT_TEMPERATURE is None
        assert attrs.TARGET_TEMPERATURE is None
        assert attrs.FAN_MODE is None

        # Test with values
        attrs = ClimateAttributes(
            STATE=climate.States.HEAT,
            CURRENT_TEMPERATURE=20.5,
            TARGET_TEMPERATURE=22.0,
            FAN_MODE="auto",
        )
        assert attrs.STATE == climate.States.HEAT
        assert attrs.CURRENT_TEMPERATURE == 20.5
        assert attrs.TARGET_TEMPERATURE == 22.0
        assert attrs.FAN_MODE == "auto"

    def test_cover_attributes(self):
        """Test CoverAttributes dataclass."""
        from ucapi import cover
        from ucapi_framework import CoverAttributes

        # Test default values
        attrs = CoverAttributes()
        assert attrs.STATE is None
        assert attrs.POSITION is None
        assert attrs.TILT_POSITION is None

        # Test with values
        attrs = CoverAttributes(STATE=cover.States.OPEN, POSITION=100, TILT_POSITION=50)
        assert attrs.STATE == cover.States.OPEN
        assert attrs.POSITION == 100
        assert attrs.TILT_POSITION == 50

    def test_light_attributes(self):
        """Test LightAttributes dataclass."""
        from ucapi import light
        from ucapi_framework import LightAttributes

        # Test default values
        attrs = LightAttributes()
        assert attrs.STATE is None
        assert attrs.BRIGHTNESS is None
        assert attrs.HUE is None

        # Test with values
        attrs = LightAttributes(
            STATE=light.States.ON, BRIGHTNESS=200, HUE=180, SATURATION=100
        )
        assert attrs.STATE == light.States.ON
        assert attrs.BRIGHTNESS == 200
        assert attrs.HUE == 180
        assert attrs.SATURATION == 100

    def test_remote_attributes(self):
        """Test RemoteAttributes dataclass."""
        from ucapi import remote
        from ucapi_framework import RemoteAttributes

        # Test default values
        attrs = RemoteAttributes()
        assert attrs.STATE is None

        # Test with values
        attrs = RemoteAttributes(STATE=remote.States.ON)
        assert attrs.STATE == remote.States.ON

    def test_sensor_attributes(self):
        """Test SensorAttributes dataclass."""
        from ucapi import sensor as ucapi_sensor
        from ucapi_framework import SensorAttributes

        # Test default values
        attrs = SensorAttributes()
        assert attrs.STATE is None
        assert attrs.VALUE is None
        assert attrs.UNIT is None

        # Test with values (numeric)
        attrs = SensorAttributes(STATE=ucapi_sensor.States.ON, VALUE=23.5, UNIT="°C")
        assert attrs.STATE == ucapi_sensor.States.ON
        assert attrs.VALUE == 23.5
        assert attrs.UNIT == "°C"

        # Test with values (string)
        attrs = SensorAttributes(STATE=ucapi_sensor.States.ON, VALUE="active", UNIT="")
        assert attrs.VALUE == "active"

    def test_switch_attributes(self):
        """Test SwitchAttributes dataclass."""
        from ucapi import switch
        from ucapi_framework import SwitchAttributes

        # Test default values
        attrs = SwitchAttributes()
        assert attrs.STATE is None

        # Test with values
        attrs = SwitchAttributes(STATE=switch.States.ON)
        assert attrs.STATE == switch.States.ON

    def test_voice_assistant_attributes(self):
        """Test VoiceAssistantAttributes dataclass."""
        from ucapi import voice_assistant
        from ucapi_framework import VoiceAssistantAttributes

        # Test default values
        attrs = VoiceAssistantAttributes()
        assert attrs.STATE is None

        # Test with values
        attrs = VoiceAssistantAttributes(STATE=voice_assistant.States.ON)
        assert attrs.STATE == voice_assistant.States.ON

    def test_entity_attributes_inheritance(self):
        """Test that all attribute dataclasses inherit from EntityAttributes."""
        from ucapi_framework import (
            ButtonAttributes,
            ClimateAttributes,
            CoverAttributes,
            EntityAttributes,
            LightAttributes,
            MediaPlayerAttributes,
            RemoteAttributes,
            SensorAttributes,
            SwitchAttributes,
            VoiceAssistantAttributes,
        )

        # All should be instances of EntityAttributes
        assert isinstance(ButtonAttributes(), EntityAttributes)
        assert isinstance(ClimateAttributes(), EntityAttributes)
        assert isinstance(CoverAttributes(), EntityAttributes)
        assert isinstance(LightAttributes(), EntityAttributes)
        assert isinstance(MediaPlayerAttributes(), EntityAttributes)
        assert isinstance(RemoteAttributes(), EntityAttributes)
        assert isinstance(SensorAttributes(), EntityAttributes)
        assert isinstance(SwitchAttributes(), EntityAttributes)
        assert isinstance(VoiceAssistantAttributes(), EntityAttributes)

    def test_update_with_dict(self, mock_api):
        """Test entity.update() with a plain dictionary."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        mock_api.configured_entities.get.return_value = entity

        # Update with dict should work
        entity.update(
            {
                media_player.Attributes.STATE: media_player.States.PLAYING,
                media_player.Attributes.VOLUME: 50,
            }
        )

        # Should call update_attributes
        assert mock_api.configured_entities.update_attributes.called

    def test_update_with_invalid_type(self, mock_api):
        """Test entity.update() with invalid type raises TypeError."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Should raise TypeError for non-dataclass, non-dict
        with pytest.raises(TypeError, match="Expected a dataclass or dict"):
            entity.update("invalid")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="Expected a dataclass or dict"):
            entity.update(42)  # type: ignore[arg-type]

    def test_update_with_extra_dataclass_fields(self, mock_api):
        """Test update with dataclass containing fields not in ucapi Attributes enum."""
        from dataclasses import dataclass
        from ucapi_framework import MediaPlayerAttributes

        # Create a custom dataclass with extra fields
        @dataclass
        class ExtendedMediaPlayerAttributes(MediaPlayerAttributes):
            CUSTOM_FIELD: str | None = None

        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001
        mock_api.configured_entities.get.return_value = entity

        attrs = ExtendedMediaPlayerAttributes(
            STATE=media_player.States.PLAYING, VOLUME=50, CUSTOM_FIELD="custom_value"
        )

        # Should not raise error, just skip unknown fields
        entity.update(attrs)
        assert mock_api.configured_entities.update_attributes.called

    def test_filter_changed_attributes_entity_not_found(self, mock_api):
        """Test filter_changed_attributes when entity not found returns all attributes."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Entity not found in configured_entities
        mock_api.configured_entities.get.return_value = None

        update = {
            media_player.Attributes.STATE: media_player.States.PLAYING,
            media_player.Attributes.VOLUME: 50,
        }

        # Should return all attributes when entity not found
        result = entity.filter_changed_attributes(update)
        assert result == update


class TestSyncStateAndSubscription:
    """Tests for sync_state() and subscribe_to_device() coordinator pattern."""

    @pytest.fixture
    def mock_api(self):
        """Provide a mock API for all tests."""
        return MagicMock()

    def test_sync_state_default_is_noop(self, mock_api):
        """Test that default sync_state() is a no-op (base Entity does not override)."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001
        # Base class sync_state is a no-op — overriding it is what triggers the coordinator path
        assert type(entity).sync_state is Entity.sync_state

    @pytest.mark.asyncio
    async def test_sync_state_noop_does_not_push(self, mock_api):
        """Test that calling the default no-op sync_state() makes no API calls."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001
        await entity.sync_state()
        mock_api.configured_entities.update_attributes.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_to_device_wires_sync_state(self, mock_api):
        """Test subscribe_to_device wires UPDATE event to sync_state."""
        class SyncingMediaPlayer(media_player.MediaPlayer, Entity):
            def __init__(self):
                super().__init__(
                    "media_player.test",
                    "Test Player",
                    features=[media_player.Features.ON_OFF],
                    attributes={media_player.Attributes.STATE: media_player.States.UNKNOWN},
                )
                self.sync_state_called = 0

            async def sync_state(self):
                self.sync_state_called += 1

        from ucapi_framework.device import DeviceEvents

        entity = SyncingMediaPlayer()
        entity._api = mock_api  # noqa: SLF001

        mock_device = MagicMock()
        entity.subscribe_to_device(mock_device)

        # Verify events.on was called with UPDATE event
        mock_device.events.on.assert_called_once_with(
            DeviceEvents.UPDATE, entity._handle_device_update  # noqa: SLF001
        )

    @pytest.mark.asyncio
    async def test_handle_device_update_calls_sync_state(self, mock_api):
        """Test _handle_device_update dispatches to sync_state."""
        sync_state_mock = AsyncMock()

        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001
        entity.sync_state = sync_state_mock  # type: ignore[method-assign]

        await entity._handle_device_update("device_id", {"state": "ON"})  # noqa: SLF001

        sync_state_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_device_update_ignores_args(self, mock_api):
        """Test _handle_device_update accepts any args/kwargs without error."""
        entity = TestMediaPlayer("media_player.test", "Test Player")
        entity._api = mock_api  # noqa: SLF001

        # Should not raise regardless of args passed by the event emitter
        await entity._handle_device_update()  # noqa: SLF001
        await entity._handle_device_update("device_id", {"key": "value"}, extra="kwarg")  # noqa: SLF001

    def test_sync_state_overridden_detected(self):
        """Test that overriding sync_state is detectable for driver short-circuit."""
        class OverridingEntity(media_player.MediaPlayer, Entity):
            def __init__(self):
                super().__init__(
                    "media_player.test",
                    "Test",
                    features=[],
                    attributes={},
                )

            async def sync_state(self):
                pass

        base_entity = TestMediaPlayer("media_player.test", "Test Player")
        overriding_entity = OverridingEntity()

        # Base entity uses Entity.sync_state (no-op) — not overridden
        assert type(base_entity).sync_state is Entity.sync_state

        # Overriding entity has its own sync_state — driver should short-circuit
        assert type(overriding_entity).sync_state is not Entity.sync_state
