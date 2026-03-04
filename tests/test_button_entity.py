"""Tests for ButtonEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import button
from ucapi_framework import ButtonEntity


class TestButtonEntity:
    """Test ButtonEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={button.Attributes.STATE: button.States.AVAILABLE}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a ButtonEntity for testing."""
        entity = ButtonEntity(
            "button.test",
            "Test Button",
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == button.States.AVAILABLE

    def test_initial_state_always_available(self, mock_api):
        """Test that button always initializes STATE to AVAILABLE (ucapi hardcodes this)."""
        entity = ButtonEntity(
            "button.unset",
            "Unset Button",
        )
        entity._api = mock_api  # noqa: SLF001
        # ucapi.button.Button hardcodes {Attributes.STATE: States.AVAILABLE} in __init__
        assert entity.state == button.States.AVAILABLE

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(button.States.UNAVAILABLE, update=True)

        # Verify internal state was updated
        assert entity.state == button.States.UNAVAILABLE

        # Verify update was called
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "button.test"
        assert button.Attributes.STATE in attributes
        assert attributes[button.Attributes.STATE] == button.States.UNAVAILABLE

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(button.States.UNAVAILABLE, update=False)

        # Verify internal state was updated
        assert entity.state == button.States.UNAVAILABLE

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_state_available(self, entity, mock_api):
        """Test transitioning back to AVAILABLE."""
        entity.set_state(button.States.UNAVAILABLE, update=False)
        assert entity.state == button.States.UNAVAILABLE

        entity.set_state(button.States.AVAILABLE, update=False)
        assert entity.state == button.States.AVAILABLE

    def test_set_state_none_does_not_update_remote(self, entity, mock_api):
        """Test set_state(None) stores None but update filter strips it."""
        # set_state(None) writes None into attributes dict
        entity.set_state(None, update=True)

        # Internal state stores None
        assert entity.state is None

        # The update should have been called but the None filter in
        # update_attributes strips the None value — so update_attributes
        # is called with an empty dict (or not called if filter removes all)
        # Either way, the Remote should not receive a None value
        if mock_api.configured_entities.update_attributes.called:
            call_args = mock_api.configured_entities.update_attributes.call_args
            _, attributes = call_args[0]
            assert button.Attributes.STATE not in attributes

    def test_property_getter_is_read_only(self, entity):
        """Test that the state property cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = button.States.AVAILABLE  # type: ignore[misc]

    def test_only_one_attribute(self, entity, mock_api):
        """Test that Button only has the STATE attribute."""
        entity.set_state(button.States.UNAVAILABLE, update=True)

        call_args = mock_api.configured_entities.update_attributes.call_args
        _, attributes = call_args[0]
        # Should only contain STATE
        assert list(attributes.keys()) == [button.Attributes.STATE]


class TestButtonEntityInheritance:
    """Test that ButtonEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomButton(ButtonEntity):
            def __init__(self):
                super().__init__(
                    "button.custom",
                    "Custom Button",
                )
                self.custom_set_state_called = False

            def set_state(self, value, *, update=True):
                """Override set_state to add custom logic."""
                self.custom_set_state_called = True
                super().set_state(value, update=update)

        entity = CustomButton()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(button.States.AVAILABLE, update=False)
        assert entity.custom_set_state_called is True
        assert entity.state == button.States.AVAILABLE

    def test_custom_property_getter(self):
        """Test that the state property getter can be overridden."""

        class CustomButton(ButtonEntity):
            def __init__(self):
                super().__init__(
                    "button.custom",
                    "Custom Button",
                )

            @property
            def state(self):
                """Override state getter to always return AVAILABLE."""
                return button.States.AVAILABLE

        entity = CustomButton()
        # Property override always returns AVAILABLE
        assert entity.state == button.States.AVAILABLE
