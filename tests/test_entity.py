"""Tests for Entity ABC."""

from unittest.mock import MagicMock

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
