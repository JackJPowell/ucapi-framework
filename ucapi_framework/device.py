"""
Base device interface classes for Unfolded Circle Remote integrations.

Provides base classes for different device connection patterns:
- Stateless HTTP devices
- Polling devices
- WebSocket devices
- Persistent connection devices

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import AbstractEventLoop
from enum import IntEnum
from typing import TYPE_CHECKING, Any

import aiohttp
from pyee.asyncio import AsyncIOEventEmitter

if TYPE_CHECKING:
    from .config import BaseDeviceManager

_LOG = logging.getLogger(__name__)

BACKOFF_MAX = 30
BACKOFF_SEC = 2


class DeviceEvents(IntEnum):
    """Common device events."""

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
    PAIRED = 3
    ERROR = 4
    UPDATE = 5


class BaseDeviceInterface(ABC):
    """
    Base class for all device interfaces.

    Provides common functionality:
    - Event emitter for device state changes
    - Connection lifecycle management
    - Property accessors for device information
    - Logging helpers
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        config_manager: BaseDeviceManager | None = None,
    ):
        """
        Create device interface instance.

        :param device_config: Device configuration
        :param loop: Event loop
        :param config_manager: Optional config manager for persisting configuration updates
        """
        self._loop: AbstractEventLoop = loop or asyncio.get_running_loop()
        self.events = AsyncIOEventEmitter(self._loop)
        self._device_config = device_config
        self._config_manager: BaseDeviceManager | None = config_manager
        self._state: Any = None

    @property
    def device_config(self) -> Any:
        """Return the device configuration."""
        return self._device_config

    def update_config(self, **kwargs) -> bool:
        """
        Update device configuration attributes and persist changes.

        This method allows devices to update their configuration when runtime
        changes occur, such as:
        - New authentication tokens received
        - IP address changes detected
        - Device firmware updates changing capabilities
        - Dynamic configuration from device responses

        The configuration is updated both in memory and persisted to storage
        if a config_manager is available.

        Example usage:
            # Update token after authentication
            self.update_config(token="new_token_value")

            # Update multiple fields
            self.update_config(
                address="192.168.1.100",
                token="new_token",
                firmware_version="2.0.1"
            )

        :param kwargs: Configuration attributes to update
        :return: True if config was persisted successfully, False if no config_manager or update failed
        :raises AttributeError: If trying to update non-existent configuration attribute
        """
        # Update the in-memory configuration
        for key, value in kwargs.items():
            if not hasattr(self._device_config, key):
                raise AttributeError(
                    f"Configuration attribute '{key}' does not exist on {type(self._device_config).__name__}"
                )
            setattr(self._device_config, key, value)

        # Persist changes if config manager is available
        if self._config_manager is not None:
            return self._config_manager.update(self._device_config)

        _LOG.debug(
            "[%s] Config updated in memory only (no config_manager available)",
            self.log_id,
        )
        return False

    @property
    @abstractmethod
    def identifier(self) -> str:
        """Return the device identifier."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the device name."""

    @property
    @abstractmethod
    def address(self) -> str | None:
        """Return the device address."""

    @property
    @abstractmethod
    def log_id(self) -> str:
        """Return a log identifier for the device."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if device is currently connected, False otherwise."""

    @property
    def state(self) -> Any:
        """Return the current device state."""
        return self._state

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the device."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""


class StatelessHTTPDevice(BaseDeviceInterface):
    """
    Base class for devices with stateless HTTP API.

    No persistent connection is maintained. Each command creates a new
    HTTP session for the request.

    Good for: REST APIs, simple HTTP devices without a persistent connection (e.g., websockets)
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        config_manager: BaseDeviceManager | None = None,
    ):
        """Initialize stateless HTTP device."""
        super().__init__(device_config, loop, config_manager)
        self._is_connected = False
        self._session_timeout = aiohttp.ClientTimeout(total=10)

    async def connect(self) -> None:
        """
        Establish connection (verify device is reachable).

        For stateless devices, this typically means verifying the device
        responds to a basic request.
        """
        _LOG.debug("[%s] Connecting to device at %s", self.log_id, self.address)
        self.events.emit(DeviceEvents.CONNECTING, self.identifier)

        try:
            await self.verify_connection()
            self._is_connected = True
            self.events.emit(DeviceEvents.CONNECTED, self.identifier)
            _LOG.info("[%s] Connected", self.log_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Connection error: %s", self.log_id, err)
            self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))
            self._is_connected = False

    async def disconnect(self) -> None:
        """Disconnect from device (mark as disconnected)."""
        _LOG.debug("[%s] Disconnecting from device", self.log_id)
        self._is_connected = False
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

    @property
    def is_connected(self) -> bool:
        """Return True if device is currently connected."""
        return self._is_connected

    @abstractmethod
    async def verify_connection(self) -> None:
        """
        Verify the device connection.

        Should make a simple request to verify device is reachable.
        Raises exception if connection fails.
        """

    async def _http_request(
        self, method: str, url: str, **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Make an HTTP request to the device.

        :param method: HTTP method (GET, POST, PUT, etc.)
        :param url: Full URL or path
        :param kwargs: Additional arguments for aiohttp request
        :return: HTTP response
        """
        async with aiohttp.ClientSession(timeout=self._session_timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return response


class PollingDevice(BaseDeviceInterface):
    """
    Base class for devices requiring periodic status polling.

    Maintains a polling task that periodically queries the device for status updates.

    Good for: Devices without push notifications, devices with changing state
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        poll_interval: int = 30,
        config_manager: BaseDeviceManager | None = None,
    ):
        """
        Initialize polling device.

        :param device_config: Device configuration
        :param loop: Event loop
        :param poll_interval: Polling interval in seconds
        :param config_manager: Optional config manager for persisting configuration updates
        """
        super().__init__(device_config, loop, config_manager)
        self._poll_interval = poll_interval
        self._poll_task: asyncio.Task | None = None
        self._stop_polling = asyncio.Event()

    async def connect(self) -> None:
        """Establish connection and start polling."""
        # Prevent multiple concurrent connections
        if self._poll_task and not self._poll_task.done():
            _LOG.debug(
                "[%s] Already connected and polling, skipping connect", self.log_id
            )
            return

        _LOG.debug("[%s] Connecting and starting poll", self.log_id)
        self.events.emit(DeviceEvents.CONNECTING, self.identifier)

        try:
            await self.establish_connection()
            self._stop_polling.clear()
            self._poll_task = asyncio.create_task(self._poll_loop())
            self.events.emit(DeviceEvents.CONNECTED, self.identifier)
            _LOG.info("[%s] Connected and polling started", self.log_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] Connection error: %s", self.log_id, err)
            self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))

    async def disconnect(self) -> None:
        """Stop polling and disconnect."""
        _LOG.debug("[%s] Disconnecting and stopping poll", self.log_id)
        self._stop_polling.set()

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        self._poll_task = None
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

    @property
    def is_connected(self) -> bool:
        """Return True if device is currently connected and polling."""
        return self._poll_task is not None and not self._poll_task.done()

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        _LOG.debug("[%s] Poll loop started", self.log_id)

        while not self._stop_polling.is_set():
            try:
                await self.poll_device()
            except asyncio.CancelledError:
                break
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOG.error("[%s] Poll error: %s", self.log_id, err)

            try:
                await asyncio.wait_for(
                    self._stop_polling.wait(), timeout=self._poll_interval
                )
            except asyncio.TimeoutError:
                pass  # Normal timeout, continue polling

        _LOG.debug("[%s] Poll loop stopped", self.log_id)

    @abstractmethod
    async def establish_connection(self) -> None:
        """
        Establish initial connection to device.

        Called once when connect() is invoked.
        """

    @abstractmethod
    async def poll_device(self) -> None:
        """
        Poll the device for status updates.

        Called periodically based on poll_interval.
        Should emit UPDATE events with changed state.
        """


class WebSocketDevice(BaseDeviceInterface):
    """
    Base class for devices with WebSocket connections.

    Maintains a persistent WebSocket connection with automatic reconnection,
    exponential backoff, and optional ping/keepalive support.

    Features:
    - Automatic reconnection on connection loss
    - Configurable exponential backoff (default: 2s initial, 30s max)
    - Optional ping/pong keepalive (default: 30s interval)
    - Graceful error handling and recovery

    Good for: Devices with WebSocket APIs, real-time updates
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        reconnect: bool = True,
        reconnect_interval: int = BACKOFF_SEC,
        reconnect_max: int = BACKOFF_MAX,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        config_manager: BaseDeviceManager | None = None,
    ):
        """
        Initialize WebSocket device.

        :param device_config: Device configuration
        :param loop: Event loop
        :param reconnect: Enable automatic reconnection (default: True)
        :param reconnect_interval: Initial reconnection interval in seconds (default: 2)
        :param reconnect_max: Maximum reconnection interval in seconds (default: 30)
        :param ping_interval: Ping/keepalive interval in seconds, 0 to disable (default: 30)
        :param ping_timeout: Ping timeout in seconds (default: 10)
        :param config_manager: Optional config manager for persisting configuration updates
        """
        super().__init__(device_config, loop, config_manager)
        self._ws: Any = None
        self._ws_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None
        self._stop_ws = asyncio.Event()
        self._reconnect_enabled = reconnect
        self._reconnect_interval = reconnect_interval
        self._reconnect_max = reconnect_max
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._backoff_current = reconnect_interval
        self._is_connected = False

    async def connect(self) -> None:
        """
        Establish WebSocket connection with automatic reconnection.

        If reconnection is enabled, this will continuously attempt to
        maintain a connection until disconnect() is called.
        """
        # Prevent multiple concurrent connection tasks
        if self._ws_task and not self._ws_task.done():
            _LOG.debug("[%s] WebSocket connection task already running", self.log_id)
            return

        _LOG.debug(
            "[%s] Starting WebSocket connection to %s", self.log_id, self.address
        )
        self._stop_ws.clear()
        self._backoff_current = self._reconnect_interval

        if self._reconnect_enabled:
            # Start connection loop with automatic reconnection
            self._ws_task = asyncio.create_task(self._connection_loop())
        else:
            # Single connection attempt
            self._ws_task = asyncio.create_task(self._single_connect())

    async def disconnect(self) -> None:
        """Close WebSocket connection and stop reconnection attempts."""
        _LOG.debug("[%s] Disconnecting WebSocket", self.log_id)
        self._stop_ws.set()

        # Stop ping task
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        self._ping_task = None

        # Stop connection task
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self._ws:
            try:
                await self.close_websocket()
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOG.debug("[%s] Error closing WebSocket: %s", self.log_id, err)
            self._ws = None

        self._ws_task = None
        self._is_connected = False
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

    async def _single_connect(self) -> None:
        """Single connection attempt without reconnection."""
        self.events.emit(DeviceEvents.CONNECTING, self.identifier)

        try:
            self._ws = await self.create_websocket()
            self._is_connected = True
            self.events.emit(DeviceEvents.CONNECTED, self.identifier)
            _LOG.info("[%s] WebSocket connected", self.log_id)

            # Start ping task if enabled
            if self._ping_interval > 0:
                self._ping_task = asyncio.create_task(self._ping_loop())

            # Run message loop
            await self._message_loop()

        except asyncio.CancelledError:
            pass
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] WebSocket connection error: %s", self.log_id, err)
            self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))
        finally:
            self._is_connected = False
            if self._ws:
                try:
                    await self.close_websocket()
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                self._ws = None

    async def _connection_loop(self) -> None:
        """
        Connection loop with automatic reconnection and exponential backoff.

        Continuously attempts to establish and maintain WebSocket connection.
        Implements exponential backoff on connection failures.
        """
        first_connection = True

        while not self._stop_ws.is_set():
            try:
                _LOG.debug("[%s] Establishing WebSocket connection", self.log_id)
                if first_connection:
                    self.events.emit(DeviceEvents.CONNECTING, self.identifier)

                self._ws = await self.create_websocket()
                self._is_connected = True
                self._backoff_current = (
                    self._reconnect_interval
                )  # Reset backoff on success
                self.events.emit(DeviceEvents.CONNECTED, self.identifier)
                _LOG.info("[%s] WebSocket connected", self.log_id)
                first_connection = False

                # Start ping task if enabled
                if self._ping_interval > 0:
                    self._ping_task = asyncio.create_task(self._ping_loop())

                # Run message loop
                await self._message_loop()

            except asyncio.CancelledError:
                break
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOG.warning("[%s] WebSocket connection error: %s", self.log_id, err)
                self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))
                self._is_connected = False

                # Clean up
                if self._ping_task and not self._ping_task.done():
                    self._ping_task.cancel()
                    try:
                        await self._ping_task
                    except asyncio.CancelledError:
                        pass
                    self._ping_task = None

                if self._ws:
                    try:
                        await self.close_websocket()
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                    self._ws = None

                # Exponential backoff for reconnection
                if not self._stop_ws.is_set():
                    _LOG.debug(
                        "[%s] Reconnecting in %d seconds",
                        self.log_id,
                        self._backoff_current,
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop_ws.wait(), timeout=self._backoff_current
                        )
                    except asyncio.TimeoutError:
                        pass
                    self._backoff_current = min(
                        self._backoff_current * 2, self._reconnect_max
                    )

    async def _message_loop(self) -> None:
        """Main message loop for receiving WebSocket messages."""
        _LOG.debug("[%s] WebSocket message loop started", self.log_id)

        try:
            while not self._stop_ws.is_set() and self._is_connected:
                message = await self.receive_message()
                if message is None:
                    _LOG.debug("[%s] WebSocket connection closed", self.log_id)
                    break
                await self.handle_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("[%s] WebSocket message error: %s", self.log_id, err)
            self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))

        self._is_connected = False
        _LOG.debug("[%s] WebSocket message loop stopped", self.log_id)

    async def _ping_loop(self) -> None:
        """
        Ping/keepalive loop to maintain WebSocket connection.

        Sends periodic pings to detect connection issues early.
        """
        _LOG.debug(
            "[%s] WebSocket ping loop started (interval: %ds)",
            self.log_id,
            self._ping_interval,
        )

        try:
            while not self._stop_ws.is_set() and self._is_connected:
                await asyncio.sleep(self._ping_interval)

                if self._is_connected and self._ws:
                    try:
                        await asyncio.wait_for(
                            self.send_ping(), timeout=self._ping_timeout
                        )
                    except asyncio.TimeoutError:
                        _LOG.warning(
                            "[%s] Ping timeout, connection may be dead", self.log_id
                        )
                        self._is_connected = False
                        break
                    except Exception as err:  # pylint: disable=broad-exception-caught
                        _LOG.debug("[%s] Ping failed: %s", self.log_id, err)
                        # Connection will be detected as closed in message loop

        except asyncio.CancelledError:
            pass

        _LOG.debug("[%s] WebSocket ping loop stopped", self.log_id)

    async def send_ping(self) -> None:
        """
        Send ping to WebSocket connection.

        Default implementation does nothing. Override this if your WebSocket
        implementation requires explicit ping messages.

        For websockets library, pings are handled automatically.
        For custom implementations, send your protocol-specific keepalive.

        Example for custom protocol:
            async def send_ping(self):
                await self._ws.send(json.dumps({"type": "ping"}))
        """
        # Default: no-op (websockets library handles pings automatically)
        pass

    @property
    def is_connected(self) -> bool:
        """
        Check if WebSocket is currently connected.

        :return: True if WebSocket is connected, False otherwise
        """
        return self._is_connected

    @abstractmethod
    async def create_websocket(self) -> Any:
        """
        Create and return WebSocket connection.

        Called automatically by the connection loop. Raise an exception
        if connection cannot be established.

        Example using websockets library:
            async def create_websocket(self):
                import websockets
                return await websockets.connect(
                    f"ws://{self.address}/socket",
                    ping_interval=None,  # We handle pings ourselves
                )

        :return: WebSocket connection object
        """

    @abstractmethod
    async def close_websocket(self) -> None:
        """
        Close the WebSocket connection.

        Example:
            async def close_websocket(self):
                if self._ws:
                    await self._ws.close()
        """

    @abstractmethod
    async def receive_message(self) -> Any:
        """
        Receive a message from WebSocket.

        Should block until a message is available or connection is closed.

        Example:
            async def receive_message(self):
                try:
                    message = await self._ws.recv()
                    return json.loads(message)
                except websockets.ConnectionClosed:
                    return None

        :return: Message data or None if connection closed
        """

    @abstractmethod
    async def handle_message(self, message: Any) -> None:
        """
        Handle incoming WebSocket message.

        Called for each message received from the WebSocket connection.

        :param message: Message data
        """


class WebSocketPollingDevice(WebSocketDevice, PollingDevice):
    """
    Base class for devices with WebSocket + Polling hybrid pattern.

    Combines WebSocket for real-time updates with periodic polling for health checks
    and state verification. This is a common pattern for smart TVs and IoT devices where:
    - WebSocket provides instant notifications when device is active
    - Polling provides fallback health checks and state verification
    - REST API provides additional control endpoints

    The polling and WebSocket run concurrently and independently. By default, polling
    continues even when WebSocket is disconnected (via disconnect()), providing resilience
    and allowing fallback to polling-only mode. Use disconnect_all() or set
    keep_polling_on_disconnect=False to stop both.

    Implementation uses multiple inheritance to compose WebSocketDevice and PollingDevice
    functionality without code duplication.

    WebSocket reconnection is automatically disabled for this class since polling
    provides the resilience. WebSocket will reconnect naturally through the hybrid
    connect() implementation.

    Good for: Smart TVs, media players, IoT devices with multiple communication methods
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        poll_interval: int = 30,
        ping_interval: int = 30,
        ping_timeout: int = 10,
        keep_polling_on_disconnect: bool = True,
        config_manager: BaseDeviceManager | None = None,
    ):
        """
        Initialize WebSocket + Polling device.

        :param device_config: Device configuration
        :param loop: Event loop
        :param poll_interval: Polling interval in seconds (default: 30)
        :param ping_interval: WebSocket ping interval in seconds, 0 to disable (default: 30)
        :param ping_timeout: WebSocket ping timeout in seconds (default: 10)
        :param keep_polling_on_disconnect: Continue polling when WebSocket disconnects (default: True)
        :param config_manager: Optional config manager for persisting configuration updates
        """
        # Initialize both parent classes
        # Disable auto-reconnect for WebSocket since polling provides resilience
        # Note: Python's MRO will handle calling BaseDeviceInterface.__init__ only once
        WebSocketDevice.__init__(
            self,
            device_config,
            loop,
            reconnect=False,  # Disabled - we handle reconnection in connect()
            ping_interval=ping_interval,
            ping_timeout=ping_timeout,
            config_manager=config_manager,
        )
        PollingDevice.__init__(self, device_config, loop, poll_interval, config_manager)
        self._keep_polling_on_disconnect = keep_polling_on_disconnect

    async def connect(self) -> None:
        """
        Establish WebSocket connection and start polling.

        Both WebSocket and polling tasks run concurrently. If WebSocket connection
        fails, polling continues to provide state updates.
        """
        # Prevent multiple concurrent connections
        if (self._ws_task and not self._ws_task.done()) or (
            self._poll_task and not self._poll_task.done()
        ):
            _LOG.debug(
                "[%s] Already connected (WS=%s, Poll=%s), skipping connect",
                self.log_id,
                self._ws_task is not None,
                self._poll_task is not None,
            )
            return

        _LOG.debug("[%s] Connecting WebSocket and starting polling", self.log_id)
        self.events.emit(DeviceEvents.CONNECTING, self.identifier)

        # Start polling task (from PollingDevice)
        self._stop_polling.clear()
        self._poll_task = asyncio.create_task(self._poll_loop())

        # Start WebSocket task (from WebSocketDevice)
        # Note: WebSocketDevice.connect() would emit CONNECTING again, so we manually start the task
        try:
            self._ws = await self.create_websocket()
            self._is_connected = True  # Mark as connected for message loop
            self._stop_ws.clear()

            # Start ping task if enabled
            if self._ping_interval > 0:
                self._ping_task = asyncio.create_task(self._ping_loop())

            self._ws_task = asyncio.create_task(self._message_loop())
            self.events.emit(DeviceEvents.CONNECTED, self.identifier)
            _LOG.info("[%s] WebSocket and polling started", self.log_id)
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.warning("[%s] WebSocket connection error: %s", self.log_id, err)
            self._is_connected = False
            # Polling continues even if WebSocket fails
            _LOG.info("[%s] Polling started (WebSocket unavailable)", self.log_id)

    async def disconnect(self, stop_polling: bool | None = None) -> None:
        """
        Stop WebSocket and optionally polling.

        If keep_polling_on_disconnect is True (default) and stop_polling is not
        explicitly set, only the WebSocket connection is stopped and polling continues.
        This allows the device to fall back to polling-only mode.

        If keep_polling_on_disconnect is False or stop_polling=True, both WebSocket
        and polling are stopped, fully disconnecting the device.

        :param stop_polling: Override to force stop polling (True) or keep it running (False).
                           If None, uses keep_polling_on_disconnect setting.
        """
        # Determine whether to stop polling
        should_stop_polling = (
            stop_polling
            if stop_polling is not None
            else not self._keep_polling_on_disconnect
        )

        if should_stop_polling:
            _LOG.debug("[%s] Disconnecting WebSocket and stopping polling", self.log_id)
        else:
            _LOG.debug(
                "[%s] Disconnecting WebSocket (keeping polling active)", self.log_id
            )

        # Stop WebSocket (from WebSocketDevice)
        self._stop_ws.set()
        self._is_connected = False

        # Stop ping task
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
        self._ping_task = None

        # Stop WebSocket task
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self.close_websocket()
            self._ws = None
        self._ws_task = None

        # Conditionally stop polling
        if should_stop_polling:
            self._stop_polling.set()
            if self._poll_task and not self._poll_task.done():
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass
            self._poll_task = None

        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

    async def disconnect_all(self) -> None:
        """
        Stop both WebSocket and polling, fully disconnecting the device.

        This method always stops both WebSocket and polling regardless of
        the keep_polling_on_disconnect setting.
        """
        await self.disconnect(stop_polling=True)

    @property
    def is_websocket_connected(self) -> bool:
        """
        Check if WebSocket is currently connected.

        :return: True if WebSocket is connected, False otherwise
        """
        return self.is_connected  # Use parent WebSocketDevice property

    # Abstract methods from both parent classes must be implemented by subclasses:
    # - create_websocket() from WebSocketDevice
    # - close_websocket() from WebSocketDevice
    # - receive_message() from WebSocketDevice
    # - handle_message() from WebSocketDevice
    # - establish_connection() from PollingDevice
    # - poll_device() from PollingDevice


class PersistentConnectionDevice(BaseDeviceInterface):
    """
    Base class for devices with persistent TCP/protocol connections.

    Maintains a persistent connection with reconnection logic and backoff.

    Good for: Proprietary protocols, TCP connections, devices requiring persistent sessions
    """

    def __init__(
        self,
        device_config: Any,
        loop: AbstractEventLoop | None = None,
        backoff_max: int = BACKOFF_MAX,
        config_manager: BaseDeviceManager | None = None,
    ):
        """
        Initialize persistent connection device.

        :param device_config: Device configuration
        :param loop: Event loop
        :param backoff_max: Maximum backoff time in seconds
        :param config_manager: Optional config manager for persisting configuration updates
        """
        super().__init__(device_config, loop, config_manager)
        self._connection: Any = None
        self._reconnect_task: asyncio.Task | None = None
        self._stop_reconnect = asyncio.Event()
        self._backoff_max = backoff_max
        self._backoff_current = BACKOFF_SEC

    async def connect(self) -> None:
        """Establish persistent connection with reconnection logic."""
        _LOG.debug("[%s] Starting persistent connection", self.log_id)
        self._stop_reconnect.clear()
        self._reconnect_task = asyncio.create_task(self._connection_loop())

    async def disconnect(self) -> None:
        """Close persistent connection."""
        _LOG.debug("[%s] Stopping persistent connection", self.log_id)
        self._stop_reconnect.set()

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._connection:
            await self.close_connection()
            self._connection = None

        self._reconnect_task = None
        self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)

    @property
    def is_connected(self) -> bool:
        """Return True if device has an active connection."""
        return self._connection is not None

    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection."""
        while not self._stop_reconnect.is_set():
            try:
                _LOG.debug("[%s] Establishing connection", self.log_id)
                self.events.emit(DeviceEvents.CONNECTING, self.identifier)

                self._connection = await self.establish_connection()
                self._backoff_current = BACKOFF_SEC  # Reset backoff on success
                self.events.emit(DeviceEvents.CONNECTED, self.identifier)
                _LOG.info("[%s] Connected", self.log_id)

                # Maintain connection
                await self.maintain_connection()

            except asyncio.CancelledError:
                break
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOG.error("[%s] Connection error: %s", self.log_id, err)
                self.events.emit(DeviceEvents.ERROR, self.identifier, str(err))

                if self._connection:
                    await self.close_connection()
                    self._connection = None

                # Exponential backoff
                if not self._stop_reconnect.is_set():
                    _LOG.debug(
                        "[%s] Reconnecting in %d seconds",
                        self.log_id,
                        self._backoff_current,
                    )
                    try:
                        await asyncio.wait_for(
                            self._stop_reconnect.wait(), timeout=self._backoff_current
                        )
                    except asyncio.TimeoutError:
                        pass

                    self._backoff_current = min(
                        self._backoff_current * 2, self._backoff_max
                    )

    @abstractmethod
    async def establish_connection(self) -> Any:
        """
        Establish connection to device.

        :return: Connection object
        """

    @abstractmethod
    async def close_connection(self) -> None:
        """Close the connection."""

    @abstractmethod
    async def maintain_connection(self) -> None:
        """
        Maintain the connection.

        This method should block while the connection is active.
        Return when connection is lost or should be closed.
        """
