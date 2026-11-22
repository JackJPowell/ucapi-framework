"""Web view support against the real ucapi entity store and capability routing."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from ucapi import Entities, EntityTypes, IntegrationAPI, webview
from ucapi.api_definitions import Events
from ucapi.api import _WsContext

from ucapi_framework import WebViewAttributes, WebViewEntity
from ucapi_framework.entities import WebViewEntity as ExportedWebViewEntity
from tests.test_driver import DeviceConfigForTests, DeviceForTests
from ucapi_framework import BaseIntegrationDriver


@pytest.fixture
async def entity():
    entity = WebViewEntity(
        "webview.dev1",
        {"en": "Dashboard"},
        options={
            "url": "https://dashboard.example.com/energy",
            "auth": {"type": "bearer", "token": "test-token"},
            "tls": {"certificate_sha256": "AB" * 32},
            "cookies": [{"name": "layout", "value": "compact"}],
            "user_agent": "desktop",
            "zoom": 70,
            "background_color": "#112233",
            "show_navigation": True,
            "reload_interval": 60,
            "buttons": {
                webview.Button.CHANNEL_UP: {
                    "action": webview.ButtonActionType.FUNCTION,
                    "function": webview.ButtonFunction.RELOAD,
                },
                webview.Button.DPAD_MIDDLE: {
                    "action": webview.ButtonActionType.KEY,
                    "key": webview.ButtonKey.ENTER,
                },
            },
            webview.Options.DEVICE_API: True,
        },
        icon="uc:globe",
        description={"en": "Energy usage"},
        area="Office",
    )
    entity._api = MagicMock()
    entity._api.configured_entities = Entities("configured", asyncio.get_running_loop())
    entity._api.configured_entities.add(entity)
    return entity


async def test_definition_and_exports(entity):
    assert ExportedWebViewEntity is WebViewEntity
    definition = json.loads(json.dumps(entity._api.configured_entities.get_all()))[0]
    assert definition["entity_type"] == "webview"
    assert definition["features"] == []
    assert definition["options"] == entity.options
    assert definition["name"] == {"en": "Dashboard"}
    assert definition["description"] == {"en": "Energy usage"}
    assert definition["area"] == "Office"
    assert definition["icon"] == "uc:globe"
    assert "device_class" not in definition
    assert entity.attributes == {}
    assert entity.state is None


async def test_optional_state_and_change_filtering(entity):
    listener = MagicMock()
    entity._api.configured_entities.add_listener(
        Events.ENTITY_ATTRIBUTES_UPDATED, listener
    )
    entity.update(WebViewAttributes())
    listener.assert_not_called()
    entity.set_state(webview.States.UNAVAILABLE, update=True)
    listener.assert_called_once_with(
        entity.id,
        EntityTypes.WEBVIEW,
        {webview.Attributes.STATE: webview.States.UNAVAILABLE},
    )
    entity.set_state(webview.States.UNAVAILABLE, update=True)
    assert listener.call_count == 1
    entity.update(WebViewAttributes(STATE=webview.States.ON))
    assert entity.state == webview.States.ON
    assert listener.call_count == 2
    entity.set_state(None, update=True)
    assert entity.attributes == {}
    assert listener.call_count == 2
    entity.set_state(webview.States.UNKNOWN)
    assert entity.state == webview.States.UNKNOWN
    assert listener.call_count == 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("on", "ON"),
        ("unavailable", "UNAVAILABLE"),
        ("unknown", "UNKNOWN"),
        ("off", "UNKNOWN"),
        ("playing", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
async def test_state_mapping(entity, value, expected):
    assert entity.map_entity_states(value) == expected


@pytest.fixture
async def webview_driver(entity):
    driver = BaseIntegrationDriver(
        DeviceForTests,
        [lambda cfg, dev: entity],
        loop=asyncio.get_running_loop(),
    )
    driver.api = entity._api
    driver.api.available_entities = Entities("available", asyncio.get_running_loop())
    driver.api.set_device_state = AsyncMock()
    driver.add_configured_device(
        DeviceConfigForTests("dev1", "Dashboard", "localhost"), connect=False
    )
    return driver


@pytest.mark.parametrize("raw_entity", [False, True])
async def test_driver_state_routing(webview_driver, entity, raw_entity):
    driver = webview_driver
    if raw_entity:
        driver.api.configured_entities.remove(entity.id)
        entity = webview.Webview(entity.id, "Dashboard", options=entity.options)
        driver.api.configured_entities.add(entity)
    await driver.on_device_update(entity.id, {"state": "on", "url": "ignored"})
    assert entity.attributes == {"state": "ON"}
    await driver.on_device_update(entity.id, {"state": "off"})
    assert entity.attributes == {"state": "UNKNOWN"}
    await driver.on_device_update(entity.id, {"state": None})
    assert entity.attributes == {"state": "UNKNOWN"}
    await driver.on_device_update(entity.id, {"state": "unavailable"})
    assert entity.attributes == {"state": "UNAVAILABLE"}


@pytest.mark.parametrize("connected", [False, True])
async def test_connection_does_not_infer_state(webview_driver, entity, connected):
    driver = webview_driver
    device = driver._device_instances["dev1"]
    device._connected = connected
    device._state = "off"
    await driver.refresh_entity_state(entity.id)
    await driver.on_device_disconnected("dev1")
    await driver.on_device_connection_error("dev1", "Failed")
    assert entity.attributes == {}
    device.get_device_attributes = lambda entity_id: WebViewAttributes(
        STATE=webview.States.ON
    )
    await driver.refresh_entity_state(entity.id)
    await driver.on_device_disconnected("dev1")
    assert entity.state == webview.States.ON


@pytest.mark.parametrize(
    "supported",
    [
        {"webview"},
        {"sensor"},
        pytest.param(
            set(),
            marks=pytest.mark.xfail(
                strict=True,
                reason="Upstream PR #77 returns webviews when capability discovery is empty",
            ),
        ),
        pytest.param(
            None,
            marks=pytest.mark.xfail(
                strict=True,
                reason="Upstream PR #77 returns webviews when capability discovery fails",
            ),
        ),
    ],
)
async def test_ucapi_filters_unsupported_firmware(entity, supported):
    api = IntegrationAPI(asyncio.get_running_loop())
    api.available_entities.add(entity)
    socket = MagicMock()
    api._clients.add(socket)
    api._ws_contexts[socket] = _WsContext(
        incoming=asyncio.Queue(),
        outgoing=asyncio.Queue(),
        pending={},
        supported_entity_types=supported,
    )
    api.get_supported_entity_types = AsyncMock(return_value=[])
    api._send_ws_response = AsyncMock()
    await api._get_available_entities(socket, 1)
    definitions = api._send_ws_response.call_args.args[3]["available_entities"]
    assert bool(definitions) == (supported == {"webview"})


def test_upstream_constructor_contract():
    options: webview.WebviewEntityOptions = {
        "url": "https://example.com",
        "device_api": True,
    }
    entity = WebViewEntity("webview.test", "Test", options)
    assert isinstance(entity, webview.Webview)
    assert entity.options == options


@pytest.mark.parametrize("options", [{}, {"url": ""}, {"url": "   "}, {"url": 1}])
def test_upstream_url_validation(options):
    with pytest.raises(ValueError, match="non-empty 'url'"):
        WebViewEntity("webview.test", "Test", options=options)


def test_upstream_options_type_validation():
    with pytest.raises(TypeError, match="options must be dict"):
        WebViewEntity("webview.test", "Test", options=None)
