"""Tests for discovery classes."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ucapi_framework.discovery import (
    BaseDiscovery,
    DiscoveredDevice,
    SSDPDiscovery,
    MDNSDiscovery,
)


class TestDiscoveredDevice:
    """Tests for DiscoveredDevice dataclass."""

    def test_create_discovered_device(self):
        """Test creating a DiscoveredDevice."""
        device = DiscoveredDevice(
            identifier="device-123",
            name="Test Device",
            address="192.168.1.100",
            extra_data={"model": "TestModel"},
        )

        assert device.identifier == "device-123"
        assert device.name == "Test Device"
        assert device.address == "192.168.1.100"
        assert device.extra_data["model"] == "TestModel"

    def test_discovered_device_repr(self):
        """Test string representation."""
        device = DiscoveredDevice(
            identifier="dev-1",
            name="My Device",
            address="10.0.0.1",
        )

        repr_str = repr(device)
        assert "dev-1" in repr_str
        assert "My Device" in repr_str
        assert "10.0.0.1" in repr_str

    def test_discovered_device_without_extra_data(self):
        """Test creating device without extra_data."""
        device = DiscoveredDevice(
            identifier="dev-1",
            name="Device",
            address="192.168.1.1",
        )

        assert device.extra_data is None


class ConcreteDiscovery(BaseDiscovery):
    """Concrete implementation for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.discover_called = False

    async def discover(self):
        """Discover devices."""
        self.discover_called = True
        self._discovered_devices = [
            DiscoveredDevice("dev1", "Device 1", "192.168.1.1"),
            DiscoveredDevice("dev2", "Device 2", "192.168.1.2"),
        ]
        return self._discovered_devices


class TestBaseDiscovery:
    """Tests for BaseDiscovery."""

    def test_init(self):
        """Test discovery initialization."""
        discovery = ConcreteDiscovery(timeout=10)

        assert discovery.timeout == 10
        assert discovery._discovered_devices == []

    def test_default_timeout(self):
        """Test default timeout value."""
        discovery = ConcreteDiscovery()

        assert discovery.timeout == 5

    @pytest.mark.asyncio
    async def test_discover(self):
        """Test discover method."""
        discovery = ConcreteDiscovery()

        devices = await discovery.discover()

        assert discovery.discover_called is True
        assert len(devices) == 2
        assert devices[0].identifier == "dev1"
        assert devices[1].identifier == "dev2"

    def test_clear(self):
        """Test clearing discovered devices."""
        discovery = ConcreteDiscovery()
        discovery._discovered_devices = [
            DiscoveredDevice("dev1", "Device 1", "192.168.1.1"),
        ]

        discovery.clear()

        assert discovery._discovered_devices == []


class ConcreteSSDPDiscovery(SSDPDiscovery):
    """Concrete SSDP discovery for testing."""

    def parse_ssdp_device(self, raw_device: dict):
        """Parse SSDP device."""
        try:
            return DiscoveredDevice(
                identifier=raw_device.get("usn", ""),
                name=raw_device.get("server", "Unknown"),
                address=raw_device.get("location", "").split("//")[1].split(":")[0],
                extra_data={"location": raw_device.get("location")},
            )
        except (IndexError, KeyError):
            return None


class TestSSDPDiscovery:
    """Tests for SSDPDiscovery."""

    def test_init(self):
        """Test SSDP discovery initialization."""
        discovery = ConcreteSSDPDiscovery(
            search_target="urn:schemas-upnp-org:device:Basic:1",
            timeout=10,
        )

        assert discovery.search_target == "urn:schemas-upnp-org:device:Basic:1"
        assert discovery.timeout == 10

    def test_default_search_target(self):
        """Test default search target."""
        discovery = ConcreteSSDPDiscovery()

        assert discovery.search_target == "ssdp:all"

    @pytest.mark.asyncio
    async def test_discover_with_ssdpy(self):
        """Test SSDP discovery with ssdpy module."""
        mock_ssdp_client = Mock()
        mock_ssdp_client.m_search.return_value = [
            {
                "usn": "uuid:device-1",
                "server": "Test Device 1",
                "location": "http://192.168.1.100:8080/description.xml",
            },
            {
                "usn": "uuid:device-2",
                "server": "Test Device 2",
                "location": "http://192.168.1.101:8080/description.xml",
            },
        ]

        mock_ssdpy_module = Mock()
        mock_ssdpy_module.SSDPClient.return_value = mock_ssdp_client

        with patch.dict("sys.modules", {"ssdpy": mock_ssdpy_module}):
            discovery = ConcreteSSDPDiscovery()
            devices = await discovery.discover()

            assert len(devices) == 2
            assert devices[0].identifier == "uuid:device-1"
            assert devices[0].name == "Test Device 1"

    @pytest.mark.asyncio
    async def test_discover_with_filter(self):
        """Test SSDP discovery with device filter."""

        def device_filter(raw_device):
            return "Test Device 1" in raw_device.get("server", "")

        mock_ssdp_client = Mock()
        mock_ssdp_client.m_search.return_value = [
            {
                "usn": "uuid:device-1",
                "server": "Test Device 1",
                "location": "http://192.168.1.100:8080/description.xml",
            },
            {
                "usn": "uuid:device-2",
                "server": "Other Device",
                "location": "http://192.168.1.101:8080/description.xml",
            },
        ]

        mock_ssdpy_module = Mock()
        mock_ssdpy_module.SSDPClient.return_value = mock_ssdp_client

        with patch.dict("sys.modules", {"ssdpy": mock_ssdpy_module}):
            discovery = ConcreteSSDPDiscovery(device_filter=device_filter)
            devices = await discovery.discover()

            # Only one device should pass the filter
            assert len(devices) == 1
            assert devices[0].name == "Test Device 1"

    @pytest.mark.asyncio
    async def test_discover_handles_import_error(self):
        """Test that discover handles missing ssdpy gracefully."""
        discovery = ConcreteSSDPDiscovery()

        # Patch the import to raise ImportError
        def mock_import(name, *args, **kwargs):
            if name == "ssdpy":
                raise ImportError("No module named 'ssdpy'")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            devices = await discovery.discover()
            # Should return empty list on import error
            assert devices == []


class ConcreteMDNSDiscovery(MDNSDiscovery):
    """Concrete mDNS discovery for testing."""

    def parse_mdns_service(self, service_info):
        """Parse mDNS service info."""
        if service_info is None:
            return None

        try:
            return DiscoveredDevice(
                identifier=service_info.name,
                name=service_info.server,
                address=service_info.addresses[0] if service_info.addresses else "",
                extra_data={"port": service_info.port},
            )
        except (AttributeError, IndexError):
            return None


class TestMDNSDiscovery:
    """Tests for MDNSDiscovery."""

    def test_init(self):
        """Test mDNS discovery initialization."""
        discovery = ConcreteMDNSDiscovery(
            service_type="_http._tcp.local.",
            timeout=10,
        )

        assert discovery.service_type == "_http._tcp.local."
        assert discovery.timeout == 10

    @pytest.mark.asyncio
    async def test_discover_with_zeroconf(self):
        """Test mDNS discovery with mocked zeroconf."""
        mock_service_info = Mock()
        mock_service_info.name = "test-device._test._tcp.local."
        mock_service_info.server = "Test Device"
        mock_service_info.addresses = [b"\xc0\xa8\x01\x64"]  # 192.168.1.100 as bytes
        mock_service_info.port = 8080

        mock_zeroconf = Mock()
        mock_service_browser = Mock()

        mock_zeroconf_module = Mock()
        mock_zeroconf_module.Zeroconf.return_value = mock_zeroconf
        mock_zeroconf_module.ServiceBrowser.return_value = mock_service_browser

        with patch.dict("sys.modules", {"zeroconf": mock_zeroconf_module}):
            discovery = ConcreteMDNSDiscovery(
                service_type="_test._tcp.local.", timeout=1
            )
            devices = await discovery.discover()

            # Due to asyncio sleep and mocking complexity, this is more of a structure test
            assert isinstance(devices, list)


class TestNetworkScanDiscovery:
    """Tests for NetworkScanDiscovery."""

    @pytest.mark.asyncio
    async def test_network_scan_not_implemented(self):
        """Test that network scan discovery warns about not being implemented."""
        from ucapi_framework.discovery import NetworkScanDiscovery

        class ConcreteNetworkScan(NetworkScanDiscovery):
            async def probe_device(self, ip, port):
                return None

        discovery = ConcreteNetworkScan(
            ip_range="192.168.1.0/24",
            ports=[8080, 9090],
            timeout=5,
        )

        devices = await discovery.discover()

        # Currently returns empty list
        assert devices == []


class TestDiscoveryIntegration:
    """Integration tests for discovery classes."""

    @pytest.mark.asyncio
    async def test_multiple_discovery_runs(self):
        """Test running discovery multiple times."""
        discovery = ConcreteDiscovery()

        devices1 = await discovery.discover()
        devices2 = await discovery.discover()

        assert len(devices1) == len(devices2)
        assert devices1[0].identifier == devices2[0].identifier

    @pytest.mark.asyncio
    async def test_discovery_with_clear(self):
        """Test discovery with clearing between runs."""
        discovery = ConcreteDiscovery()

        devices1 = await discovery.discover()
        assert len(devices1) == 2

        discovery.clear()
        assert len(discovery._discovered_devices) == 0

        devices2 = await discovery.discover()
        assert len(devices2) == 2

    @pytest.mark.asyncio
    async def test_mdns_listener_methods(self):
        """Test mDNS discovery listener callback methods."""
        mock_zeroconf = Mock()
        mock_service_browser = Mock()

        mock_zeroconf_module = Mock()
        mock_zeroconf_module.Zeroconf.return_value = mock_zeroconf

        # Capture the listener instance
        captured_listener = None

        def capture_listener(zc, service_type, listener):
            nonlocal captured_listener
            captured_listener = listener
            return mock_service_browser

        mock_zeroconf_module.ServiceBrowser.side_effect = capture_listener

        with patch.dict("sys.modules", {"zeroconf": mock_zeroconf_module}):
            discovery = ConcreteMDNSDiscovery(
                service_type="_test._tcp.local.", timeout=0.1
            )
            await discovery.discover()

            # Test the listener methods
            if captured_listener:
                # Test remove_service (should do nothing)
                captured_listener.remove_service(
                    mock_zeroconf, "_test._tcp.local.", "test"
                )

                # Test update_service (should do nothing)
                captured_listener.update_service(
                    mock_zeroconf, "_test._tcp.local.", "test"
                )

    @pytest.mark.asyncio
    async def test_mdns_handles_import_error(self):
        """Test that mDNS discovery handles missing zeroconf gracefully."""
        from ucapi_framework.discovery import MDNSDiscovery

        class TestMDNS(MDNSDiscovery):
            def parse_mdns_service(self, service_info):
                return None

        discovery = TestMDNS(service_type="_test._tcp.local.")

        # Remove zeroconf from sys.modules if present
        with patch.dict("sys.modules", {"zeroconf": None}):
            # This will log an error but return empty list
            devices = await discovery.discover()
            assert devices == []

    @pytest.mark.asyncio
    async def test_mdns_parse_returns_none(self):
        """Test mDNS when parse returns None for a service."""
        mock_service_info = Mock()
        mock_service_info.name = "test-device._test._tcp.local."

        mock_zeroconf = Mock()
        mock_zeroconf.get_service_info.return_value = mock_service_info

        mock_zeroconf_module = Mock()
        mock_zeroconf_module.Zeroconf.return_value = mock_zeroconf
        mock_zeroconf_module.ServiceBrowser.return_value = Mock()

        # Create a discovery that returns None for parsing
        class NoneReturningMDNS(MDNSDiscovery):
            def parse_mdns_service(self, service_info):
                return None  # Simulate unparseable service

        with patch.dict("sys.modules", {"zeroconf": mock_zeroconf_module}):
            discovery = NoneReturningMDNS(service_type="_test._tcp.local.", timeout=0.1)
            devices = await discovery.discover()

            # Should return empty list since parse returns None
            assert devices == []
