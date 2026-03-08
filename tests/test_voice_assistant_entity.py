"""Tests for VoiceAssistantEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import voice_assistant
from ucapi_framework import VoiceAssistantEntity


class TestVoiceAssistantEntity:
    """Test VoiceAssistantEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={voice_assistant.Attributes.STATE: voice_assistant.States.OFF}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a VoiceAssistantEntity for testing."""
        entity = VoiceAssistantEntity(
            "voice_assistant.test",
            "Test Voice Assistant",
            features=[voice_assistant.Features.TRANSCRIPTION],
            attributes={voice_assistant.Attributes.STATE: voice_assistant.States.OFF},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == voice_assistant.States.OFF

    def test_set_state_on_with_update(self, entity, mock_api):
        """Test set_state(ON) calls entity.update() by default."""
        entity.set_state(voice_assistant.States.ON, update=True)

        assert entity.state == voice_assistant.States.ON

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "voice_assistant.test"
        assert voice_assistant.Attributes.STATE in attributes
        assert attributes[voice_assistant.Attributes.STATE] == voice_assistant.States.ON

    def test_set_state_off_with_update(self, entity, mock_api):
        """Test set_state(OFF) calls entity.update() when state actually changes."""
        # Make mock return ON so that transitioning to OFF appears as a change
        mock_api.configured_entities.get.return_value = MagicMock(
            attributes={voice_assistant.Attributes.STATE: voice_assistant.States.ON}
        )
        entity.set_state(voice_assistant.States.OFF, update=True)

        assert entity.state == voice_assistant.States.OFF
        assert mock_api.configured_entities.update_attributes.called

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(voice_assistant.States.ON, update=False)

        assert entity.state == voice_assistant.States.ON
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_state_unavailable(self, entity, mock_api):
        """Test transitioning to UNAVAILABLE."""
        entity.set_state(voice_assistant.States.UNAVAILABLE, update=False)
        assert entity.state == voice_assistant.States.UNAVAILABLE

    def test_set_state_none_does_not_send_none(self, entity, mock_api):
        """Test set_state(None) stores None but update filter strips it."""
        entity.set_state(None, update=True)

        assert entity.state is None

        if mock_api.configured_entities.update_attributes.called:
            call_args = mock_api.configured_entities.update_attributes.call_args
            _, attributes = call_args[0]
            assert voice_assistant.Attributes.STATE not in attributes

    def test_property_getter_is_read_only(self, entity):
        """Test that the state property cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = voice_assistant.States.ON  # type: ignore[misc]

    def test_only_one_attribute(self, entity, mock_api):
        """Test that VoiceAssistantEntity only manages the STATE attribute."""
        entity.set_state(voice_assistant.States.ON, update=True)

        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]
        assert list(attributes.keys()) == [voice_assistant.Attributes.STATE]

    def test_no_set_attributes_method(self, entity):
        """Test that VoiceAssistantEntity does not have a set_attributes bulk helper."""
        assert not hasattr(entity, "set_attributes")


class TestVoiceAssistantEntityInheritance:
    """Test that VoiceAssistantEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomVoiceAssistant(VoiceAssistantEntity):
            def __init__(self):
                super().__init__(
                    "voice_assistant.custom",
                    "Custom Voice Assistant",
                    features=[],
                    attributes={},
                )
                self.custom_called = False

            def set_state(self, value, *, update=True):
                self.custom_called = True
                super().set_state(value, update=update)

        entity = CustomVoiceAssistant()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(voice_assistant.States.ON, update=False)
        assert entity.custom_called is True
        assert entity.state == voice_assistant.States.ON
