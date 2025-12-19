"""
Base discovery classes for Unfolded Circle Remote integrations.

Provides base classes and protocols for device discovery.

Optional Dependencies
---------------------
This module uses lazy imports to avoid requiring discovery dependencies
for integrations that don't use them. Install only what you need:

**SSDP Discovery** (UPnP, media renderers, smart TVs):
    - Package: ssdpy
    - Install: pip install ssdpy
    - Used by: SSDPDiscovery class
    - Import fails with helpful message if not installed

**SDDP Discovery** (Samsung TVs and similar devices):
    - Package: sddp-discovery-protocol
    - Install: pip install sddp-discovery-protocol
    - Used by: SDDPDiscovery class
    - Import fails with helpful message if not installed

**mDNS/Bonjour Discovery** (Apple devices, Chromecast, IoT):
    - Package: zeroconf
    - Install: pip install zeroconf
    - Used by: MDNSDiscovery class
    - Import fails with helpful message if not installed

**No Discovery** (Manual entry only):
    - Pass discovery=None to setup flow
    - No additional dependencies required

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

_LOG = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """
    Common structure for discovered devices.

    All discovery implementations should return this format.
    """

    identifier: str
    """Unique identifier for the device (e.g., MAC address, serial number)"""

    name: str
    """Human-readable device name"""

    address: str
    """Device address (IP address, Bluetooth address, etc.)"""

    extra_data: dict[str, Any] | None = None
    """Optional additional data specific to the discovery method"""

    def __repr__(self):
        return f"DiscoveredDevice(id={self.identifier}, name={self.name}, address={self.address})"


class BaseDiscovery(ABC):
    """
    Base class for device discovery.

    Provides a common interface for different discovery methods:
    - SSDP
    - mDNS/Bonjour
    - Bluetooth LE
    - Cloud API
    - Network scanning
    """

    def __init__(self, timeout: int = 5):
        """
        Initialize discovery.

        :param timeout: Discovery timeout in seconds
        """
        self.timeout = timeout
        self._discovered_devices: list[DiscoveredDevice] = []

    @property
    def devices(self) -> list[DiscoveredDevice]:
        """
        Get the list of discovered devices from the last discovery run.

        This property provides access to devices found by the most recent
        call to discover(). Useful when implementing create_device_from_discovery()
        in setup flows.

        :return: List of discovered devices
        """
        return self._discovered_devices

    @abstractmethod
    async def discover(self) -> list[DiscoveredDevice]:
        """
        Perform device discovery.

        :return: List of discovered devices
        """

    def clear(self) -> None:
        """Clear the list of discovered devices."""
        self._discovered_devices.clear()


class SSDPDiscovery(BaseDiscovery):
    """
    SSDP-based device discovery.

    Uses Simple Service Discovery Protocol to find devices on the local network.
    Good for: UPnP devices, media renderers, smart TVs
    """

    def __init__(
        self,
        search_target: str = "ssdp:all",
        timeout: int = 5,
        device_filter: Callable | None = None,
    ):
        """
        Initialize SSDP discovery.

        :param search_target: SSDP search target (e.g., "ssdp:all", "urn:schemas-upnp-org:device:MediaRenderer:1")
        :param timeout: Discovery timeout in seconds
        :param device_filter: Optional filter function to filter discovered devices
        """
        super().__init__(timeout)
        self.search_target = search_target
        self.device_filter = device_filter

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Perform SSDP discovery.

        :return: List of discovered devices
        """
        _LOG.info(
            "Starting SSDP discovery (target: %s, timeout: %ds)",
            self.search_target,
            self.timeout,
        )

        try:
            try:
                from ssdpy import SSDPClient  # type: ignore[import-not-found]
            except ImportError as err:
                raise ImportError(
                    "ssdpy package is required for SSDP discovery. "
                    "Install it with: pip install ssdpy"
                ) from err

            client = SSDPClient(timeout=self.timeout)
            raw_devices = client.m_search(self.search_target)

            _LOG.debug("Found %d SSDP devices", len(raw_devices))

            self._discovered_devices.clear()

            for raw_device in raw_devices:
                # Apply filter if provided
                if self.device_filter and not self.device_filter(raw_device):
                    continue

                # Parse device info
                device = self.parse_ssdp_device(raw_device)
                if device:
                    self._discovered_devices.append(device)

            _LOG.info(
                "SSDP discovery complete: found %d device(s)",
                len(self._discovered_devices),
            )

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("SSDP discovery error: %s", err)

        return self._discovered_devices

    @abstractmethod
    def parse_ssdp_device(self, raw_device: dict) -> DiscoveredDevice | None:
        """
        Parse raw SSDP device data into DiscoveredDevice.

        Override this method to extract device information from SSDP response.

        :param raw_device: Raw SSDP device data
        :return: DiscoveredDevice or None if parsing fails
        """


class SDDPDiscovery(BaseDiscovery):
    """
    SDDP-based device discovery.

    Uses Simple Device Discovery Protocol (similar to SSDP but with different format).
    Good for: Samsung TVs and other devices using SDDP protocol
    """

    def __init__(
        self,
        search_pattern: str = "*",
        timeout: int = 5,
        multicast_address: str | None = None,
        multicast_port: int | None = None,
        bind_addresses: list[str] | None = None,
        include_loopback: bool = False,
    ):
        """
        Initialize SDDP discovery.

        :param search_pattern: SDDP search pattern (default: "*" for all devices)
        :param timeout: Discovery timeout in seconds
        :param multicast_address: SDDP multicast address (uses default if None)
        :param multicast_port: SDDP multicast port (uses default if None)
        :param bind_addresses: Optional list of specific addresses to bind to
        :param include_loopback: Whether to include loopback interface
        """
        super().__init__(timeout)
        self.search_pattern = search_pattern
        self.multicast_address = multicast_address
        self.multicast_port = multicast_port
        self.bind_addresses = bind_addresses
        self.include_loopback = include_loopback

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Perform SDDP discovery.

        :return: List of discovered devices
        """
        _LOG.info(
            "Starting SDDP discovery (pattern: %s, timeout: %ds)",
            self.search_pattern,
            self.timeout,
        )

        try:
            try:
                import sddp_discovery_protocol as sddp  # type: ignore[import-not-found]
                from sddp_discovery_protocol.constants import (  # type: ignore[import-not-found]
                    SDDP_MULTICAST_ADDRESS,
                    SDDP_PORT,
                )
            except ImportError as err:
                raise ImportError(
                    "sddp-discovery-protocol package is required for SDDP discovery. "
                    "Install it with: pip install sddp-discovery-protocol"
                ) from err

            # Use defaults if not specified
            multicast_address = self.multicast_address or SDDP_MULTICAST_ADDRESS
            multicast_port = self.multicast_port or SDDP_PORT

            self._discovered_devices.clear()

            async with sddp.SddpClient(
                search_pattern=self.search_pattern,
                response_wait_time=self.timeout,
                multicast_address=multicast_address,
                multicast_port=multicast_port,
                bind_addresses=self.bind_addresses,
                include_loopback=self.include_loopback,
            ) as client:
                async with client.search(
                    search_pattern=self.search_pattern,
                    response_wait_time=self.timeout,
                ) as search_request:
                    async for response_info in search_request.iter_responses():
                        device = self.parse_sddp_response(
                            response_info.datagram, response_info
                        )
                        if device:
                            self._discovered_devices.append(device)

            _LOG.info(
                "SDDP discovery complete: found %d device(s)",
                len(self._discovered_devices),
            )

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("SDDP discovery error: %s", err)

        return self._discovered_devices

    @abstractmethod
    def parse_sddp_response(
        self, datagram: Any, response_info: Any
    ) -> DiscoveredDevice | None:
        """
        Parse SDDP response into DiscoveredDevice.

        Override this method to extract device information from SDDP response.
        The datagram contains device information in its headers (hdr_from, hdr_type, etc.).

        Example implementation:
            def parse_sddp_response(self, datagram, response_info):
                return DiscoveredDevice(
                    identifier=datagram.hdr_type,  # or other unique field
                    name=datagram.hdr_type,
                    address=datagram.hdr_from[0],  # IP address
                    extra_data={
                        "type": datagram.hdr_type,
                        "datagram": datagram,
                    }
                )

        :param datagram: SDDP datagram with headers (hdr_from, hdr_type, etc.)
        :param response_info: Full response info object from SDDP client
        :return: DiscoveredDevice or None if parsing fails
        """


class MDNSDiscovery(BaseDiscovery):
    """
    mDNS/Bonjour-based device discovery.

    Uses multicast DNS to discover devices advertising services.
    Good for: Apple devices, HomeKit, Chromecast, many IoT devices
    """

    def __init__(
        self,
        service_type: str,
        timeout: int = 5,
    ):
        """
        Initialize mDNS discovery.

        :param service_type: mDNS service type (e.g., "_airplay._tcp.local.", "_googlecast._tcp.local.")
        :param timeout: Discovery timeout in seconds
        """
        super().__init__(timeout)
        self.service_type = service_type

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Perform mDNS discovery.

        :return: List of discovered devices
        """
        _LOG.info(
            "Starting mDNS discovery (service: %s, timeout: %ds)",
            self.service_type,
            self.timeout,
        )

        try:
            try:
                from zeroconf import ServiceBrowser, ServiceListener, Zeroconf  # type: ignore[import-not-found]
            except ImportError as err:
                raise ImportError(
                    "zeroconf package is required for mDNS discovery. "
                    "Install it with: pip install zeroconf"
                ) from err

            import asyncio

            zeroconf = Zeroconf()
            discovered = []

            class Listener(ServiceListener):
                def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    info = zc.get_service_info(type_, name)
                    if info:
                        discovered.append(info)

                def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

                def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
                    pass

            browser = ServiceBrowser(zeroconf, self.service_type, Listener())

            # Wait for discovery timeout
            await asyncio.sleep(self.timeout)

            browser.cancel()
            zeroconf.close()

            self._discovered_devices.clear()

            for service_info in discovered:
                device = self.parse_mdns_service(service_info)
                if device:
                    self._discovered_devices.append(device)

            _LOG.info(
                "mDNS discovery complete: found %d device(s)",
                len(self._discovered_devices),
            )

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOG.error("mDNS discovery error: %s", err)

        return self._discovered_devices

    @abstractmethod
    def parse_mdns_service(self, service_info: Any) -> DiscoveredDevice | None:
        """
        Parse mDNS service info into DiscoveredDevice.

        Override this method to extract device information from mDNS service.

        :param service_info: mDNS service info object
        :return: DiscoveredDevice or None if parsing fails
        """


class NetworkScanDiscovery(BaseDiscovery):
    """
    Network scanning-based device discovery.

    Scans IP range for devices responding on specific ports.
    Good for: Devices without standard discovery protocols
    """

    def __init__(
        self,
        ip_range: str,
        ports: list[int],
        timeout: int = 5,
    ):
        """
        Initialize network scan discovery.

        :param ip_range: IP range to scan (e.g., "192.168.1.0/24")
        :param ports: List of ports to check
        :param timeout: Discovery timeout in seconds
        """
        super().__init__(timeout)
        self.ip_range = ip_range
        self.ports = ports

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Perform network scan discovery.

        :return: List of discovered devices
        """
        _LOG.info(
            "Starting network scan (range: %s, ports: %s, timeout: %ds)",
            self.ip_range,
            self.ports,
            self.timeout,
        )

        # Implementation would scan network and check ports
        # This is a placeholder - actual implementation depends on specific needs

        _LOG.warning("Network scan discovery not yet implemented")
        return []

    @abstractmethod
    async def probe_device(self, ip: str, port: int) -> DiscoveredDevice | None:
        """
        Probe a specific IP:port for device information.

        Override this method to implement device probing logic.

        :param ip: IP address to probe
        :param port: Port to probe
        :return: DiscoveredDevice or None if not a valid device
        """
