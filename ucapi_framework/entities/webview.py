"""Web view entity with optional state management."""

from typing import Any

from ucapi import webview

from ucapi_framework.entity import Entity, map_state_to_webview


class WebViewEntity(webview.Webview, Entity):
    """Web page rendered by the Remote UI, with optional driver state updates.

    Accepts the same constructor arguments as ``ucapi.webview.Webview``,
    including required ``options`` with an HTTP(S) ``url``. Options are passed
    through to ucapi and validated by Core. There are no features, device
    classes or driver command handlers. Omit state to let Core manage availability.
    """

    @property
    def state(self) -> webview.States | None:
        """Get the optional state (ON, UNAVAILABLE or UNKNOWN)."""
        return self.attributes.get(webview.Attributes.STATE)

    def set_state(self, value: webview.States | None, *, update: bool = False) -> None:
        """Set state locally, optionally sending the change to the Remote.

        ``None`` removes local state and sends no update. Omit state from the
        entity definition to let Core determine availability.
        """
        if value is None:
            self.attributes.pop(webview.Attributes.STATE, None)
            return
        if update:
            # Send before mutating: configured_entities may hold this same object.
            self.update({webview.Attributes.STATE: value})
        self.attributes[webview.Attributes.STATE] = value

    def map_entity_states(self, device_state: Any) -> webview.States:
        """Map device state without introducing unsupported states like OFF."""
        return map_state_to_webview(device_state)
