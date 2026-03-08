"""Tests for LightEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import light
from ucapi_framework import LightEntity


class TestLightEntity:
    """Test LightEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={light.Attributes.STATE: light.States.OFF}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a LightEntity for testing."""
        entity = LightEntity(
            "light.test",
            "Test Light",
            features=[light.Features.ON_OFF, light.Features.DIM],
            attributes={light.Attributes.STATE: light.States.OFF},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        # State was set to OFF in constructor
        assert entity.state == light.States.OFF
        # These were not set, so should be None
        assert entity.brightness is None
        assert entity.hue is None
        assert entity.saturation is None
        assert entity.color_temperature is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(light.States.ON, update=True)

        # Verify internal state was updated
        assert entity.state == light.States.ON

        # Verify update was called
        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "light.test"
        assert light.Attributes.STATE in attributes
        assert attributes[light.Attributes.STATE] == light.States.ON

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(light.States.ON, update=False)

        # Verify internal state was updated
        assert entity.state == light.States.ON

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_brightness(self, entity, mock_api):
        """Test set_brightness() updates state and calls update."""
        entity.set_brightness(80, update=True)

        assert entity.brightness == 80
        assert mock_api.configured_entities.update_attributes.called

    def test_set_brightness_without_update(self, entity, mock_api):
        """Test set_brightness(update=False) does not call entity.update()."""
        entity.set_brightness(80, update=False)

        assert entity.brightness == 80
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_hue(self, entity, mock_api):
        """Test set_hue() updates state and calls update."""
        entity.set_hue(180, update=True)

        assert entity.hue == 180
        assert mock_api.configured_entities.update_attributes.called

    def test_set_saturation(self, entity, mock_api):
        """Test set_saturation() updates state and calls update."""
        entity.set_saturation(75, update=True)

        assert entity.saturation == 75
        assert mock_api.configured_entities.update_attributes.called

    def test_set_color_temperature(self, entity, mock_api):
        """Test set_color_temperature() updates state and calls update."""
        entity.set_color_temperature(4000, update=True)

        assert entity.color_temperature == 4000
        assert mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=light.States.ON,
            brightness=75,
            hue=120,
            saturation=80,
            color_temperature=3500,
            update=True,
        )

        # Verify all internal state was updated
        assert entity.state == light.States.ON
        assert entity.brightness == 75
        assert entity.hue == 120
        assert entity.saturation == 80
        assert entity.color_temperature == 3500

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        # Verify all attributes were included in the update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "light.test"
        assert len(attributes) == 5
        assert attributes[light.Attributes.STATE] == light.States.ON
        assert attributes[light.Attributes.BRIGHTNESS] == 75
        assert attributes[light.Attributes.HUE] == 120
        assert attributes[light.Attributes.SATURATION] == 80
        assert attributes[light.Attributes.COLOR_TEMPERATURE] == 3500

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(state=light.States.ON, brightness=50, update=False)

        # Verify internal state was updated
        assert entity.state == light.States.ON
        assert entity.brightness == 50

        # Verify update was NOT called
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(state=light.States.ON, brightness=None, update=True)

        # Only state should be in internal storage
        assert entity.state == light.States.ON
        assert entity.brightness is None

        # Verify only state was included in update
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert len(attributes) == 1
        assert light.Attributes.STATE in attributes

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = light.States.ON  # type: ignore[misc]

    def test_all_light_attributes(self, entity, mock_api):
        """Test setting all light attributes."""
        entity.set_attributes(
            state=light.States.ON,
            brightness=60,
            hue=240,
            saturation=90,
            color_temperature=2700,
            update=True,
        )

        assert entity.state == light.States.ON
        assert entity.brightness == 60
        assert entity.hue == 240
        assert entity.saturation == 90
        assert entity.color_temperature == 2700

        # Verify single update call
        assert mock_api.configured_entities.update_attributes.call_count == 1


class TestLightEntityInheritance:
    """Test that LightEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomLight(LightEntity):
            def __init__(self):
                super().__init__(
                    "light.custom",
                    "Custom Light",
                    features=[],
                    attributes={},
                )
                self.custom_set_state_called = False

            def set_state(self, value, *, update=True):
                """Override set_state to add custom logic."""
                self.custom_set_state_called = True
                super().set_state(value, update=update)

        entity = CustomLight()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(light.States.ON, update=False)
        assert entity.custom_set_state_called is True
        assert entity.state == light.States.ON

    def test_custom_property_getter(self):
        """Test that property getters can be overridden."""

        class CustomLight(LightEntity):
            def __init__(self):
                super().__init__(
                    "light.custom",
                    "Custom Light",
                    features=[],
                    attributes={},
                )

            @property
            def state(self):
                """Override state getter to always return ON."""
                return light.States.ON

        entity = CustomLight()
        # Even if internal state is None, getter returns ON
        assert entity.state == light.States.ON
