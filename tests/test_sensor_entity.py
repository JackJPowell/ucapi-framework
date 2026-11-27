"""Tests for SensorEntity with built-in state management."""

import pytest
from unittest.mock import MagicMock
from ucapi import sensor
from ucapi_framework import SensorEntity


class TestSensorEntity:
    """Test SensorEntity state management."""

    @pytest.fixture
    def mock_api(self):
        """Create a mock API for testing."""
        api = MagicMock()
        api.configured_entities.get.return_value = MagicMock(
            attributes={sensor.Attributes.STATE: sensor.States.ON}
        )
        return api

    @pytest.fixture
    def entity(self, mock_api):
        """Create a SensorEntity for testing.

        Note: sensor.Sensor does NOT accept a ``cmd_handler`` parameter.
        """
        entity = SensorEntity(
            "sensor.test",
            "Test Sensor",
            features=[],
            attributes={
                sensor.Attributes.STATE: sensor.States.ON,
                sensor.Attributes.VALUE: 21.5,
                sensor.Attributes.UNIT: "°C",
            },
        )
        entity._api = mock_api  # noqa: SLF001
        return entity

    def test_initial_state(self, entity):
        """Test initial state from constructor attributes."""
        assert entity.state == sensor.States.ON
        assert entity.value == 21.5
        assert entity.unit == "°C"

    def test_initial_state_minimal(self, mock_api):
        """Test initial state when only required args are passed."""
        entity = SensorEntity(
            "sensor.minimal", "Minimal Sensor", features=[], attributes={}
        )
        entity._api = mock_api  # noqa: SLF001
        assert entity.state is None
        assert entity.value is None
        assert entity.unit is None

    def test_set_state_with_update(self, entity, mock_api):
        """Test set_state() calls entity.update() by default."""
        entity.set_state(sensor.States.UNAVAILABLE, update=True)

        assert entity.state == sensor.States.UNAVAILABLE

        assert mock_api.configured_entities.update_attributes.called
        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "sensor.test"
        assert sensor.Attributes.STATE in attributes
        assert attributes[sensor.Attributes.STATE] == sensor.States.UNAVAILABLE

    def test_set_state_without_update(self, entity, mock_api):
        """Test set_state(update=False) does not call entity.update()."""
        entity.set_state(sensor.States.UNAVAILABLE, update=False)

        assert entity.state == sensor.States.UNAVAILABLE
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_value_int(self, entity, mock_api):
        """Test set_value() with an integer value."""
        entity.set_value(42, update=True)

        assert entity.value == 42
        assert mock_api.configured_entities.update_attributes.called

    def test_set_value_float(self, entity, mock_api):
        """Test set_value() with a float value."""
        entity.set_value(23.7, update=True)

        assert entity.value == 23.7
        assert mock_api.configured_entities.update_attributes.called

    def test_set_value_string(self, entity, mock_api):
        """Test set_value() with a string value (sensor value is typed Any)."""
        entity.set_value("high", update=True)

        assert entity.value == "high"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_value_without_update(self, entity, mock_api):
        """Test set_value(update=False) does not call update."""
        entity.set_value(99.9, update=False)

        assert entity.value == 99.9
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_unit(self, entity, mock_api):
        """Test set_unit() updates state and calls update."""
        entity.set_unit("°F", update=True)

        assert entity.unit == "°F"
        assert mock_api.configured_entities.update_attributes.called

    def test_set_unit_without_update(self, entity, mock_api):
        """Test set_unit(update=False) does not call update."""
        entity.set_unit("K", update=False)

        assert entity.unit == "K"
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_bulk_update(self, entity, mock_api):
        """Test set_attributes() updates multiple attributes with single update call."""
        entity.set_attributes(
            state=sensor.States.ON,
            value=30.0,
            unit="°F",
            update=True,
        )

        assert entity.state == sensor.States.ON
        assert entity.value == 30.0
        assert entity.unit == "°F"

        # Verify update was called only once
        assert mock_api.configured_entities.update_attributes.call_count == 1

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        assert entity_id == "sensor.test"
        # STATE is unchanged (mock returns ON, we set ON), so filter removes it
        # Only VALUE and UNIT are new/changed
        assert sensor.Attributes.VALUE in attributes
        assert attributes[sensor.Attributes.VALUE] == 30.0
        assert sensor.Attributes.UNIT in attributes
        assert attributes[sensor.Attributes.UNIT] == "°F"

    def test_set_attributes_without_update(self, entity, mock_api):
        """Test set_attributes(update=False) does not call entity.update()."""
        entity.set_attributes(value=50, unit="W", update=False)

        assert entity.value == 50
        assert entity.unit == "W"
        assert not mock_api.configured_entities.update_attributes.called

    def test_set_attributes_ignores_none_values(self, entity, mock_api):
        """Test set_attributes() ignores None values."""
        entity.set_attributes(state=sensor.States.ON, value=None, update=True)

        assert entity.state == sensor.States.ON
        assert entity.value == 21.5  # unchanged from fixture

        call_args = mock_api.configured_entities.update_attributes.call_args
        entity_id, attributes = call_args[0]
        # value=None was ignored (not written to entity attributes)
        # The entity.value stays at 21.5 (unchanged from fixture)
        # STATE is filtered (unchanged), VALUE and UNIT may appear in update
        # The key assertion: we didn't accidentally write None for value
        if sensor.Attributes.VALUE in attributes:
            assert attributes[sensor.Attributes.VALUE] is not None  # None was ignored

    def test_property_getters_are_read_only(self, entity):
        """Test that property getters cannot be set directly."""
        with pytest.raises(AttributeError):
            entity.state = sensor.States.ON  # type: ignore[misc]

        with pytest.raises(AttributeError):
            entity.value = 0  # type: ignore[misc]

        with pytest.raises(AttributeError):
            entity.unit = "°C"  # type: ignore[misc]


class TestSensorEntityInheritance:
    """Test that SensorEntity can be subclassed and overridden."""

    def test_custom_set_value(self):
        """Test that set_value can be overridden."""

        class CustomSensor(SensorEntity):
            def __init__(self):
                super().__init__(
                    "sensor.custom",
                    "Custom Sensor",
                    features=[],
                    attributes={},
                )
                self.custom_called = False

            def set_value(self, value, *, update=True):
                self.custom_called = True
                super().set_value(value, update=update)

        entity = CustomSensor()
        entity._api = MagicMock()  # noqa: SLF001
        entity._api.configured_entities.get.return_value = entity  # noqa: SLF001

        entity.set_value(42, update=False)
        assert entity.custom_called is True
        assert entity.value == 42
