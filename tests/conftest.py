"""Pytest configuration and shared fixtures."""

import asyncio
import tempfile
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for configuration files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@dataclass
class TestDevice:
    """Test device configuration."""

    identifier: str
    name: str
    address: str
    extra_field: str = "test"


@dataclass
class MinimalDevice:
    """Minimal device configuration with only identifier."""

    id: str
    friendly_name: str


@pytest.fixture
def sample_device():
    """Return a sample device configuration."""
    return TestDevice(
        identifier="test-123",
        name="Test Device",
        address="192.168.1.100",
        extra_field="custom_value",
    )


@pytest.fixture
def sample_devices():
    """Return a list of sample device configurations."""
    return [
        TestDevice(
            identifier="device-1",
            name="Device One",
            address="192.168.1.101",
        ),
        TestDevice(
            identifier="device-2",
            name="Device Two",
            address="192.168.1.102",
        ),
        TestDevice(
            identifier="device-3",
            name="Device Three",
            address="192.168.1.103",
        ),
    ]


@pytest.fixture
def mock_api():
    """Create a mock IntegrationAPI."""
    api = MagicMock()
    api.configured_entities = MagicMock()
    api.available_entities = MagicMock()
    api.set_device_state = AsyncMock()
    api.config_dir_path = "/tmp/test_config"
    return api


@pytest.fixture
def mock_device_config():
    """Create a mock device configuration."""
    return TestDevice(
        identifier="mock-device-123",
        name="Mock Device",
        address="192.168.1.200",
    )
