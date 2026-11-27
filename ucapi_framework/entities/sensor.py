"""
Sensor entity with built-in state management.

Provides a Sensor entity subclass that manages its own state internally
using property getters and setter methods.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any
from ucapi import sensor
from ucapi_framework.entity import Entity


class SensorEntity(sensor.Sensor, Entity):
    """
    Sensor entity with built-in state management.

    This class extends the base Sensor entity to provide built-in state tracking
    and management. State is stored directly in the existing ``self.attributes``
    dict that all ucapi entities have.

    **State Management Pattern**:
    - Each attribute has a property getter (e.g., ``entity.value``)
    - Each attribute has a setter method (e.g., ``entity.set_value(23.5)``)
    - Setter methods accept an optional ``update`` parameter to control whether
      ``entity.update()`` is called automatically (default: True)
    - Properties are still overridable by subclasses for custom behavior

    **Example Usage**:

        ```python
        from ucapi import sensor
        from ucapi_framework.entities import SensorEntity

        class MyTemperatureSensor(SensorEntity):
            def __init__(self, device_config, device):
                entity_id = f"sensor.{device_config.id}.temperature"
                super().__init__(
                    entity_id,
                    device_config.name,
                    features=[],
                    attributes={
                        sensor.Attributes.STATE: sensor.States.ON,
                        sensor.Attributes.VALUE: 0.0,
                        sensor.Attributes.UNIT: "°C",
                    },
                    device_class=sensor.DeviceClasses.TEMPERATURE,
                )
                self._device = device

            async def sync_state(self):
                self.attributes[sensor.Attributes.STATE] = sensor.States.ON
                self.attributes[sensor.Attributes.VALUE] = self._device.temperature
                self.update(self.attributes)
        ```
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize Sensor entity with state tracking.

        Accepts the same parameters as ucapi.sensor.Sensor.
        State is stored in the existing self.attributes dict that all ucapi entities have.
        """
        super().__init__(*args, **kwargs)

    # ========================================================================
    # Property Getters (read-only access, overridable)
    # ========================================================================

    @property
    def state(self) -> sensor.States | None:
        """Get current sensor state (ON, UNAVAILABLE, UNKNOWN)."""
        return self.attributes.get(sensor.Attributes.STATE)

    @property
    def value(self) -> Any:
        """Get the current sensor measurement value."""
        return self.attributes.get(sensor.Attributes.VALUE)

    @property
    def unit(self) -> str | None:
        """Get the unit of measurement."""
        return self.attributes.get(sensor.Attributes.UNIT)

    # ========================================================================
    # Setter Methods (with optional auto-update, overridable)
    # ========================================================================

    def set_state(self, value: sensor.States | None, *, update: bool = False) -> None:
        """
        Set sensor state.

        :param value: New state value (ON, UNAVAILABLE, UNKNOWN)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[sensor.Attributes.STATE] = value
        if update:
            self.update(self.attributes)

    def set_value(self, value: Any, *, update: bool = False) -> None:
        """
        Set the sensor measurement value.

        :param value: Measurement value (numeric or string)
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[sensor.Attributes.VALUE] = value
        if update:
            self.update(self.attributes)

    def set_unit(self, value: str | None, *, update: bool = False) -> None:
        """
        Set the unit of measurement.

        :param value: Unit string (e.g., "°C", "%", "W")
        :param update: If True, call entity.update() to push changes to Remote (default: True)
        """
        self.attributes[sensor.Attributes.UNIT] = value
        if update:
            self.update(self.attributes)

    # ========================================================================
    # Bulk Update Helper
    # ========================================================================

    def set_attributes(
        self,
        *,
        state: sensor.States | None = None,
        value: Any = None,
        unit: str | None = None,
        update: bool = False,
    ) -> None:
        """
        Update multiple attributes at once with a single Remote update call.

        Only non-``None`` arguments are written into ``self.attributes``.

        :param state: Sensor state
        :param value: Measurement value
        :param unit: Unit of measurement
        :param update: If True, call entity.update() once after all changes (default: True)
        """
        if state is not None:
            self.attributes[sensor.Attributes.STATE] = state
        if value is not None:
            self.attributes[sensor.Attributes.VALUE] = value
        if unit is not None:
            self.attributes[sensor.Attributes.UNIT] = unit

        if update:
            self.update(self.attributes)
