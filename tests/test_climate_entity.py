"""Tests for ClimateEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import climate
from ucapi_framework import ClimateEntity


class TestClimateEntity:
    """Test ClimateEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={climate.Attributes.STATE: climate.States.OFF}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a ClimateEntity for testing."""
        entity = ClimateEntity(
            "climate.test",
            "Test Thermostat",
            features=[climate.Features.ON_OFF, climate.Features.HEAT],
            attributes={climate.Attributes.STATE: climate.States.OFF},
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == climate.States.OFF
        assert entity.current_temperature is None
        assert entity.target_temperature is None
        assert entity.target_temperature_high is None
        assert entity.target_temperature_low is None
        assert entity.fan_mode is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(climate.States.HEAT, update=True)

        assert entity.state == climate.States.HEAT

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "climate.test"
        assert climate.Attributes.STATE in attributes
        assert attributes[climate.Attributes.STATE] == climate.States.HEAT

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(climate.States.COOL, update=False)

        assert entity.state == climate.States.COOL
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_current_temperature(self, entity, mock_api):
        """Test set_current_temperature() updates state and calls update."""
        entity.set_current_temperature(22.5, update=True)

        assert entity.current_temperature == 22.5
        assert mock_api.configured_entities.update_attributes.called

    def test_set_current_temperature_without_update(self, entity, mock_api):
        """Test set_current_temperature(update=False) does not call update."""
        entity.set_current_temperature(22.5, update=False)

        assert entity.current_temperature == 22.5
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_target_temperature(self, entity, mock_api):
        """Test set_target_temperature() updates state and calls update."""
        entity.set_target_temperature(21.0, update=True)

        assert entity.target_temperature == 21.0
        assert mock_api.configured_entities.update_attributes.called

    def test_set_target_temperature_without_update(self, entity, mock_api):
        """Test set_target_temperature(update=False) does not call update."""
        entity.set_target_temperature(21.0, update=False)

        assert entity.target_temperature == 21.0
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_target_temperature_high(self, entity, mock_api):
        """Test set_target_temperature_high() updates state and calls update."""
        entity.set_target_temperature_high(25.0, update=True)

        assert entity.target_temperature_high == 25.0
        assert mock_api.configured_entities.update_attributes.called

    def test_set_target_temperature_low(self, entity, mock_api):
        """Test set_target_temperature_low() updates state and calls update."""
        entity.set_target_temperature_low(18.0, update=True)

        assert entity.target_temperature_low == 18.0
        assert mock_api.configured_entities.update_attributes.called

    def test_set_fan_mode(self, entity, mock_api):
        """Test set_fan_mode() updates state and calls update."""
        entity.set_fan_mode("AUTO", update=True)

        assert entity.fan_mode == "AUTO"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_fan_mode_without_update(self, entity, mock_api):
        """Test set_fan_mode(update=False) does not call update."""
        entity.set_fan_mode("HIGH", update=False)

        assert entity.fan_mode == "HIGH"
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=climate.States.HEAT,
            current_temperature=20.5,
            target_temperature=22.0,
            fan_mode="AUTO",
            update=True,
        )

        assert entity.state == climate.States.HEAT
        assert entity.current_temperature == 20.5
        assert entity.target_temperature == 22.0
        assert entity.fan_mode == "AUTO"

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "climate.test"
        assert len(attributes) == 4
        assert attributes[climate.Attributes.STATE] == climate.States.HEAT
        assert attributes[climate.Attributes.CURRENT_TEMPERATURE] == 20.5
        assert attributes[climate.Attributes.TARGET_TEMPERATURE] == 22.0
        assert attributes[climate.Attributes.FAN_MODE] == "AUTO"

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(
            state=climate.States.COOL,
            target_temperature=19.0,
            update=False,
        )

        assert entity.state == climate.States.COOL
        assert entity.target_temperature == 19.0
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(
            state=climate.States.HEAT, current_temperature=None, update=True
        )

        assert entity.state == climate.States.HEAT
        assert entity.current_temperature is None

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert len(attributes) == 1
        assert climate.Attributes.STATE in attributes

    def test_set_attributes_all_six(self, entity, mock_api):
        """Test setting all six climate attributes at once."""
        entity.set_attributes(
            state=climate.States.HEAT_COOL,
            current_temperature=21.0,
            target_temperature=22.0,
            target_temperature_high=25.0,
            target_temperature_low=18.0,
            fan_mode="AUTO",
            update=True,
        )

        assert entity.state == climate.States.HEAT_COOL
        assert entity.current_temperature == 21.0
        assert entity.target_temperature == 22.0
        assert entity.target_temperature_high == 25.0
        assert entity.target_temperature_low == 18.0
        assert entity.fan_mode == "AUTO"

        assert mock_api.configured_entities.update_attributes.call_count == 1

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = climate.States.HEAT  # type: ignore[misc]

        with pytest.raises(AttributeError):
            entity.current_temperature = 20.0  # type: ignore[misc]

        with pytest.raises(AttributeError):
            entity.target_temperature = 21.0  # type: ignore[misc]


class TestClimateEntityInheritance:
    """Test that ClimateEntity can be subclassed and overridden."""

    def test_custom_set_state(self):
        """Test that set_state can be overridden."""

        class CustomClimate(ClimateEntity):
            def __init__(self):
                super().__init__(
                    "climate.custom",
                    "Custom Thermostat",
                    features=[],
                    attributes={},
                )
                self.custom_called = False

            def set_state(self, value, *, update=True):
                self.custom_called = True
                super().set_state(value, update=update)

        entity = CustomClimate()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_state(climate.States.COOL, update=False)
        assert entity.custom_called is True
        assert entity.state == climate.States.COOL
