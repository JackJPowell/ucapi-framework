"""Tests for RemoteEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import remote
from ucapi_framework import RemoteEntity


class TestRemoteEntity:
    """Test RemoteEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={remote.Attributes.STATE: remote.States.OFF}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a RemoteEntity for testing."""
        entity = RemoteEntity(
            "remote.test",
            "Test Remote",
            features=[remote.Features.SEND_CMD],
            attributes={remote.Attributes.STATE: remote.States.OFF},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == remote.States.OFF

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(remote.States.ON, update=True)

        assert entity.state == remote.States.ON

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "remote.test"
        assert remote.Attributes.STATE in attributes
        assert attributes[remote.Attributes.STATE] == remote.States.ON

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(remote.States.ON, update=False)

        assert entity.state == remote.States.ON
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_state_unavailable(self, entity, mock_api):
        """Test transitioning to UNAVAILABLE."""
        entity.set_state(remote.States.UNAVAILABLE, update=False)
        assert entity.state == remote.States.UNAVAILABLE

    def test_set_state_back_to_off(self, entity, mock_api):
        """Test transitioning back to OFF."""
        entity.set_state(remote.States.ON, update=False)
        assert entity.state == remote.States.ON

        entity.set_state(remote.States.OFF, update=False)
        assert entity.state == remote.States.OFF

    def test_set_state_none_does_not_send_none(self, entity, mock_api):
        """Test set_state(None) stores None but update filter strips it."""
        entity.set_state(None, update=True)

        assert entity.state is None

        if mock_api.configured_entities.update_attributes.called:
            call_args = mock_api.configured_entities.update_attributes.call_args
            _, attributes = call_args[0]
            assert remote.Attributes.STATE not in attributes

    def test_property_getter_is_read_only(self, entity):
        """Test that the state property cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = remote.States.ON  # type: ignore[misc]

    def test_only_one_attribute(self, entity, mock_api):
        """Test that RemoteEntity only manages the STATE attribute."""
        entity.set_state(remote.States.ON, update=True)

        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]
        assert list(attributes.keys()) == [remote.Attributes.STATE]

    def test_no_set_attributes_method(self, entity):
        """Test that RemoteEntity does not have a set_attributes bulk helper."""
        assert not hasattr(entity, "set_attributes")


class TestRemoteEntityInheritance:
    """Test that RemoteEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomRemote(RemoteEntity):
            def __init__(self):
                super().__init__(
                    "remote.custom",
                    "Custom Remote",
                    features=[],
                    attributes={},
                )
                self.custom_called = False

            def set_state(self, value, *, update=True):
                self.custom_called = True
                super().set_state(value, update=update)

        entity = CustomRemote()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(remote.States.ON, update=False)
        assert entity.custom_called is True
        assert entity.state == remote.States.ON
