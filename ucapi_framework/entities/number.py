"""Number entity with built-in state management.

:copyright: (c) 2026 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from typing import Any

from ucapi import number

from ucapi_framework.entity import Entity


_UNSET = object()


class NumberEntity(number.Number, Entity):
    """A numeric control using the standard ucapi Number constructor.

    Range, step, unit, precision, display mode and readability are static
    constructor ``options``. Integrations implement set_value, increment and
    decrement commands through their command handler.

    Setters stage changes locally by default. Pass ``update=True`` to publish
    changes immediately. An explicit ``value=None`` reports an unknown value.
    """

    @property
    def state(self) -> number.States | None:
        """Return the current state, or None if omitted."""
        return self.attributes.get(number.Attributes.STATE)

    @property
    def value(self) -> float | int | None:
        """Return the current numeric value, or None if unknown."""
        return self.attributes.get(number.Attributes.VALUE)

    def set_state(self, value: number.States | None, *, update: bool = False) -> None:
        """Set the state and optionally publish it."""
        self._set_attributes({number.Attributes.STATE: value}, update=update)

    def set_value(self, value: float | int | None, *, update: bool = False) -> None:
        """Set the value, including None for an unknown value."""
        self._set_attributes({number.Attributes.VALUE: value}, update=update)

    def set_attributes(
        self,
        *,
        state: number.States | None = None,
        value: float | int | None | object = _UNSET,
        update: bool = False,
    ) -> None:
        """Set supplied attributes with a single optional update.

        Omitted values leave existing attributes unchanged. Explicit value=None
        clears the current value; state=None is ignored.
        """
        attributes: dict[str, Any] = {}
        if state is not None:
            attributes[number.Attributes.STATE] = state
        if value is not _UNSET:
            attributes[number.Attributes.VALUE] = value
        self._set_attributes(attributes, update=update)

    def _set_attributes(self, attributes: dict[str, Any], *, update: bool) -> None:
        # Publish before mutation: configured_entities may hold this same object.
        pending = {**self.attributes, **attributes}
        if update:
            self.update(pending)
        self.attributes.update(attributes)
