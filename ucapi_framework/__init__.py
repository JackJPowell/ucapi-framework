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
from .config import BaseConfigManager, get_config_path
from .device import (
    BaseDeviceInterface,
    StatelessHTTPDevice,
    PollingDevice,
    WebSocketDevice,
    WebSocketPollingDevice,
    ExternalClientDevice,
    PersistentConnectionDevice,
    DeviceEvents,
)
from .discovery import (
    BaseDiscovery,
    DiscoveredDevice,
    MDNSDiscovery,
    NetworkScanDiscovery,
    SDDPDiscovery,
    SSDPDiscovery,
)

__all__ = [
    "BaseIntegrationDriver",
    "BaseSetupFlow",
    "SetupSteps",
    "BaseConfigManager",
    "get_config_path",
    "BaseDeviceInterface",
    "StatelessHTTPDevice",
    "PollingDevice",
    "WebSocketDevice",
    "WebSocketPollingDevice",
    "ExternalClientDevice",
    "PersistentConnectionDevice",
    "DeviceEvents",
    "BaseDiscovery",
    "DiscoveredDevice",
    "MDNSDiscovery",
    "NetworkScanDiscovery",
    "SDDPDiscovery",
    "SSDPDiscovery",
    "create_entity_id",
]

__version__ = "1.0.1"
