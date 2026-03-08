"""Tests for CoverEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import cover
from ucapi_framework import CoverEntity


class TestCoverEntity:
    """Test CoverEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={cover.Attributes.STATE: cover.States.CLOSED}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a CoverEntity for testing."""
        entity = CoverEntity(
            "cover.test",
            "Test Cover",
            features=[cover.Features.OPEN, cover.Features.CLOSE],
            attributes={cover.Attributes.STATE: cover.States.CLOSED},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        # State was set to CLOSED in constructor
        assert entity.state == cover.States.CLOSED
        # These were not set, so should be None
        assert entity.position is None
        assert entity.tilt_position is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(cover.States.OPEN, update=True)

        # Verify internal state was updated
        assert entity.state == cover.States.OPEN

        # Verify update was called
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "cover.test"
        assert cover.Attributes.STATE in attributes
        assert attributes[cover.Attributes.STATE] == cover.States.OPEN

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(cover.States.OPEN, update=False)

        # Verify internal state was updated
        assert entity.state == cover.States.OPEN

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_state_transitions(self, entity, mock_api):
        """Test all valid state transitions."""
        for state in [
            cover.States.OPENING,
            cover.States.OPEN,
            cover.States.CLOSING,
            cover.States.CLOSED,
            cover.States.UNKNOWN,
            cover.States.UNAVAILABLE,
        ]:
            entity.set_state(state, update=False)
            assert entity.state == state

    def test_set_position(self, entity, mock_api):
        """Test set_position() updates state and calls update."""
        entity.set_position(75, update=True)

        assert entity.position == 75
        assert mock_api.configured_entities.update_attributes.called

    def test_set_position_without_update(self, entity, mock_api):
        """Test set_position(update=False) does not call entity.update()."""
        entity.set_position(75, update=False)

        assert entity.position == 75
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_tilt_position(self, entity, mock_api):
        """Test set_tilt_position() updates state and calls update."""
        entity.set_tilt_position(45, update=True)

        assert entity.tilt_position == 45
        assert mock_api.configured_entities.update_attributes.called

    def test_set_tilt_position_without_update(self, entity, mock_api):
        """Test set_tilt_position(update=False) does not call entity.update()."""
        entity.set_tilt_position(45, update=False)

        assert entity.tilt_position == 45
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=cover.States.OPEN,
            position=100,
            tilt_position=50,
            update=True,
        )

        # Verify all internal state was updated
        assert entity.state == cover.States.OPEN
        assert entity.position == 100
        assert entity.tilt_position == 50

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        # Verify all attributes were included in the update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "cover.test"
        assert len(attributes) == 3
        assert attributes[cover.Attributes.STATE] == cover.States.OPEN
        assert attributes[cover.Attributes.POSITION] == 100
        assert attributes[cover.Attributes.TILT_POSITION] == 50

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(state=cover.States.OPEN, position=100, update=False)

        # Verify internal state was updated
        assert entity.state == cover.States.OPEN
        assert entity.position == 100

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(state=cover.States.OPEN, position=None, update=True)

        # Only state should be in internal storage
        assert entity.state == cover.States.OPEN
        assert entity.position is None

        # Verify only state was included in update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert len(attributes) == 1
        assert cover.Attributes.STATE in attributes

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = cover.States.OPEN  # type: ignore[misc]

    def test_all_cover_attributes(self, entity, mock_api):
        """Test setting all cover attributes."""
        entity.set_attributes(
            state=cover.States.OPEN,
            position=100,
            tilt_position=0,
            update=True,
        )

        assert entity.state == cover.States.OPEN
        assert entity.position == 100
        assert entity.tilt_position == 0

        # Verify single update call
        assert mock_api.configured_entities.update_attributes.call_count == 1


class TestCoverEntityInheritance:
    """Test that CoverEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomCover(CoverEntity):
            def __init__(self):
                super().__init__(
                    "cover.custom",
                    "Custom Cover",
                    features=[],
                    attributes={},
                )
                self.custom_set_state_called = False

            def set_state(self, value, *, update=True):
                """Override set_state to add custom logic."""
                self.custom_set_state_called = True
                super().set_state(value, update=update)

        entity = CustomCover()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(cover.States.OPEN, update=False)
        assert entity.custom_set_state_called is True
        assert entity.state == cover.States.OPEN

    def test_custom_property_getter(self):
        """Test that property getters can be overridden."""

        class CustomCover(CoverEntity):
            def __init__(self):
                super().__init__(
                    "cover.custom",
                    "Custom Cover",
                    features=[],
                    attributes={},
                )

            @property
            def state(self):
                """Override state getter to always return OPEN."""
                return cover.States.OPEN

        entity = CustomCover()
        # Even if internal state is None, getter returns OPEN
        assert entity.state == cover.States.OPEN
