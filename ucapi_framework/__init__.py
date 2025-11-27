"""
Base classes and utilities for Unfolded Circle Remote integrations.

This module provides reusable base classes for integration drivers, setup flows,
device management, and device interfaces.

Optional Dependencies
---------------------
The discovery module supports optional dependencies for different discovery methods:
- ssdpy: For SSDP/UPnP discovery (pip install ssdpy)
- sddp-discovery-protocol: For SDDP discovery (pip install sddp-discovery-protocol)
- zeroconf: For mDNS/Bonjour discovery (pip install zeroconf)

These are only required if you use the corresponding discovery classes.
See ucapi_framework.discovery module documentation for details.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

from .driver import BaseIntegrationDriver, create_entity_id
from .setup import BaseSetupFlow, SetupSteps
from .config import BaseDeviceManager
from .device import (
    BaseDeviceInterface,
    StatelessHTTPDevice,
    PollingDevice,
    WebSocketDevice,
    WebSocketPollingDevice,
    ExternalClientDevice,
    DeviceEvents,
)
from .discovery import (
    BaseDiscovery,
    DiscoveredDevice,
    MDNSDiscovery,
    SDDPDiscovery,
    SSDPDiscovery,
)

__all__ = [
    "BaseIntegrationDriver",
    "BaseSetupFlow",
    "SetupSteps",
    "BaseDeviceManager",
    "BaseDeviceInterface",
    "StatelessHTTPDevice",
    "PollingDevice",
    "WebSocketDevice",
    "WebSocketPollingDevice",
    "BaseDiscovery",
    "DiscoveredDevice",
    "create_entity_id",
    "ExternalClientDevice",
    "DeviceEvents",
    "MDNSDiscovery",
    "SDDPDiscovery",
    "SSDPDiscovery",
]

__version__ = "0.1.0"
