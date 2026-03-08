"""Tests for SelectEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import select
from ucapi_framework import SelectEntity


class TestSelectEntity:
    """Test SelectEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={select.Attributes.STATE: select.States.ON}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a SelectEntity for testing.

        Note: select.Select does NOT accept a ``features`` parameter.
        """
        entity = SelectEntity(
            "select.test",
            "Test Select",
            attributes={
                select.Attributes.STATE: select.States.ON,
                select.Attributes.CURRENT_OPTION: "HDMI 1",
                select.Attributes.OPTIONS: ["HDMI 1", "HDMI 2", "HDMI 3"],
            },
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == select.States.ON
        assert entity.current_option == "HDMI 1"
        assert entity.options == ["HDMI 1", "HDMI 2", "HDMI 3"]

    def test_initial_state_minimal(self, mock_api):
        """Test initial state when only required args are passed."""
        entity = SelectEntity("select.minimal", "Minimal Select", attributes={})
        entity._api = mock_api  # noqa: SLF001
        assert entity.state is None
        assert entity.current_option is None
        assert entity.options is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(select.States.UNAVAILABLE, update=True)

        assert entity.state == select.States.UNAVAILABLE

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "select.test"
        assert select.Attributes.STATE in attributes
        assert attributes[select.Attributes.STATE] == select.States.UNAVAILABLE

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(select.States.UNAVAILABLE, update=False)

        assert entity.state == select.States.UNAVAILABLE
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_current_option(self, entity, mock_api):
        """Test set_current_option() updates state and calls update."""
        entity.set_current_option("HDMI 2", update=True)

        assert entity.current_option == "HDMI 2"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_current_option_without_update(self, entity, mock_api):
        """Test set_current_option(update=False) does not call update."""
        entity.set_current_option("HDMI 2", update=False)

        assert entity.current_option == "HDMI 2"
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_options(self, entity, mock_api):
        """Test set_options() updates the options list and calls update."""
        new_options = ["Input 1", "Input 2"]
        entity.set_options(new_options, update=True)

        assert entity.options == new_options
        assert mock_api.configured_entities.update_attributes.called

    def test_set_options_without_update(self, entity, mock_api):
        """Test set_options(update=False) does not call update."""
        new_options = ["Input 1", "Input 2"]
        entity.set_options(new_options, update=False)

        assert entity.options == new_options
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=select.States.ON,
            current_option="HDMI 2",
            options=["HDMI 1", "HDMI 2"],
            update=True,
        )

        assert entity.state == select.States.ON
        assert entity.current_option == "HDMI 2"
        assert entity.options == ["HDMI 1", "HDMI 2"]

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "select.test"
        # STATE is unchanged (mock returns ON, we set ON — filtered out by filter_changed_attributes)
        # Only CURRENT_OPTION and OPTIONS appear in the update
        assert select.Attributes.CURRENT_OPTION in attributes
        assert attributes[select.Attributes.CURRENT_OPTION] == "HDMI 2"
        assert select.Attributes.OPTIONS in attributes
        assert attributes[select.Attributes.OPTIONS] == ["HDMI 1", "HDMI 2"]

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(
            state=select.States.ON,
            current_option="HDMI 3",
            update=False,
        )

        assert entity.state == select.States.ON
        assert entity.current_option == "HDMI 3"
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(state=select.States.ON, current_option=None, update=True)

        assert entity.state == select.States.ON
        assert entity.current_option == "HDMI 1"  # unchanged

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        # current_option=None was ignored, so entity.current_option stays "HDMI 1"
        # The filter may include CURRENT_OPTION (it's in entity.attributes but not in mock),
        # but it must NOT be None
        if select.Attributes.CURRENT_OPTION in attributes:
            assert (
                attributes[select.Attributes.CURRENT_OPTION] is not None
            )  # None was ignored

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = select.States.ON  # type: ignore[misc]

        with pytest.raises(AttributeError):
            entity.current_option = "HDMI 2"  # type: ignore[misc]

        # Note: entity.options has a setter (required to avoid clash with ucapi Entity.options)
        # so direct assignment is allowed but has no effect on the select options list


class TestSelectEntityInheritance:
    """Test that SelectEntity can be subclassed and overridden."""

    def test_custom_set_current_option(self):
        """Test that set_current_option can be overridden."""

        class CustomSelect(SelectEntity):
            def __init__(self):
                super().__init__(
                    "select.custom",
                    "Custom Select",
                    attributes={},
                )
                self.custom_called = False

            def set_current_option(self, value, *, update=True):
                self.custom_called = True
                super().set_current_option(value, update=update)

        entity = CustomSelect()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_current_option("Option A", update=False)
        assert entity.custom_called is True
        assert entity.current_option == "Option A"
