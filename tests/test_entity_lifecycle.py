"""Exercise framework lifecycle operations through real ucapi event queues."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from ucapi import switch, webview
from ucapi.api import _WsContext

from ucapi_framework import BaseIntegrationDriver, WebViewEntity
from tests.test_driver import DeviceConfigForTests, DeviceForTests


@pytest.fixture
async def driver():
    driver = BaseIntegrationDriver(DeviceForTests, [], loop=asyncio.get_running_loop())
    driver.api.get_supported_entity_types = AsyncMock(return_value=[])
    yield driver
    await drain(driver)


def client(driver, supported):
    socket = MagicMock()
    socket.remote_address = ("localhost", 9000)
    context = _WsContext(
        incoming=asyncio.Queue(),
        outgoing=asyncio.Queue(),
        pending={},
        supported_entity_types=supported,
    )
    driver.api._clients.add(socket)
    driver.api._ws_contexts[socket] = context
    return context.outgoing


def messages(queue):
    result = []
    while not queue.empty():
        result.append(json.loads(queue.get_nowait()))
    return result


async def drain(driver):
    await driver.api.available_entities._events.wait_for_complete()
    if driver._subscription_refresh_tasks:
        await asyncio.gather(*list(driver._subscription_refresh_tasks.values()))
    await driver.api.configured_entities._events.wait_for_complete()


def dashboard(name="Dashboard", token="original-secret"):
    return WebViewEntity(
        "webview.dev1",
        name,
        options={
            "url": "https://dashboard.example.com",
            "auth": {
                "type": "header",
                "header_name": "X-API-Key",
                "header_value": token,
            },
            "cookies": [{"name": "session", "value": "cookie-secret"}],
        },
    )


async def test_runtime_notifications_are_filtered_per_client(driver):
    current = client(driver, {"webview", "switch"})
    webview_only = client(driver, {"webview"})
    older = client(driver, {"switch"})
    unknown = client(driver, None)
    entity = dashboard()
    light_switch = switch.Switch("switch.dev2", "Switch", [], {})
    driver.add_entities([entity, light_switch])
    driver.add_entities([dashboard()])  # Default skip_existing sends no duplicate.
    await drain(driver)
    assert [m["msg_data"]["entity_id"] for m in messages(current)] == [
        entity.id,
        light_switch.id,
    ]
    assert messages(older) == []
    assert messages(unknown) == []
    assert [m["msg_data"]["entity_id"] for m in messages(webview_only)] == [entity.id]

    driver.remove_entity(entity.id)
    driver.remove_entity(light_switch.id)
    await drain(driver)
    removed = messages(current)
    assert [m["msg"] for m in removed] == ["entity_removed", "entity_removed"]
    assert [m["msg_data"]["entity_id"] for m in removed] == [entity.id, light_switch.id]
    assert messages(older) == []
    assert messages(unknown) == []
    assert [m["msg_data"]["entity_id"] for m in messages(webview_only)] == [entity.id]


@pytest.mark.parametrize("notify", [False, True])
async def test_definition_updates_preserve_live_state(driver, notify):
    queue = client(driver, {"webview"})
    original = dashboard()
    driver.add_entity(original, notify=False)
    driver.api.configured_entities.add(original)
    original.set_state(webview.States.UNAVAILABLE, update=True)
    replacement = dashboard("Renamed", "rotated-secret")
    replacement.attributes["state"] = webview.States.ON
    driver.add_entities([replacement], skip_existing=False, notify=notify)

    # Sync immediately, including the silent path, before ucapi handles events.
    assert driver.api.configured_entities.get(original.id) is replacement
    assert replacement.state == webview.States.UNAVAILABLE
    assert replacement._api is driver.api
    assert replacement.options["auth"]["header_value"] == "rotated-secret"
    await drain(driver)
    events = messages(queue)
    assert len(events) == int(notify)
    if notify:
        assert events[0]["msg"] == "entity_available"
        assert events[0]["msg_data"]["name"] == {"en": "Renamed"}
        assert "attributes" not in events[0]["msg_data"]
    assert driver.api.configured_entities.get(original.id) is replacement
    assert replacement.state == webview.States.UNAVAILABLE


@pytest.mark.parametrize("notify", [False, True])
@pytest.mark.parametrize("same_instance", [False, True])
async def test_explicit_update_rotates_credentials(driver, notify, same_instance):
    queue = client(driver, {"webview"})
    original = dashboard()
    driver.add_entity(original, notify=False)
    driver.api.configured_entities.add(original)
    original.set_state(webview.States.UNAVAILABLE)
    updated = original if same_instance else dashboard("Updated")
    updated.options["auth"]["header_value"] = "rotated-header"
    updated.options["cookies"] = [{"name": "session", "value": "rotated-cookie"}]

    assert driver.update_entity(updated, notify=notify) is True
    assert updated._api is driver.api
    assert driver.api.available_entities.get(original.id) is updated
    assert driver.api.configured_entities.get(original.id) is updated
    assert updated.state == webview.States.UNAVAILABLE
    await drain(driver)
    events = messages(queue)
    assert len(events) == int(notify)
    if notify:
        assert events[0]["msg"] == "entity_available"
        options = events[0]["msg_data"]["options"]
        assert options["auth"]["header_value"] == "rotated-header"
        assert options["cookies"][0]["value"] == "rotated-cookie"
    assert updated.state == webview.States.UNAVAILABLE


@pytest.mark.parametrize("configured_only", [False, True])
async def test_explicit_update_does_not_add_missing_entity(driver, configured_only):
    queue = client(driver, {"webview"})
    original = dashboard()
    if configured_only:
        driver.api.configured_entities.add(original)
    driver._entity_subscriptions[original.id] = {object()}
    updated = dashboard("Updated", "rotated-secret")
    assert driver.update_entity(updated) is False
    await drain(driver)
    assert not driver.api.available_entities.contains(original.id)
    assert driver.api.configured_entities.get(original.id) is (
        original if configured_only else None
    )
    assert original.options["auth"]["header_value"] == "original-secret"
    assert original.id in driver._entity_subscriptions
    assert not driver._subscription_refresh_tasks
    assert messages(queue) == []


async def test_startup_silent_then_registration_notifies_connected_clients(driver):
    config = DeviceConfigForTests("dev1", "Dashboard", "localhost")
    driver._entity_classes = [lambda cfg, dev: dashboard(cfg.name)]
    listener = MagicMock()
    driver.api.available_entities.add_listener("entity_available", listener)
    driver.add_configured_device(config, connect=False)
    await drain(driver)
    listener.assert_not_called()

    queue = client(driver, {"webview"})
    config.name = "Updated dashboard"
    driver.register_available_entities(config, driver._device_instances["dev1"])
    await drain(driver)
    (event,) = messages(queue)
    assert event["msg"] == "entity_available"
    assert event["msg_data"]["name"] == {"en": "Updated dashboard"}


async def test_replacement_refreshes_pending_subscription(driver):
    queue = client(driver, {"webview"})
    first = dashboard()
    refreshed = []

    async def refresh(entity_id):
        refreshed.append(driver.api.configured_entities.get(entity_id))

    driver.refresh_entity_state = AsyncMock(side_effect=refresh)
    driver._entity_subscriptions[first.id] = {object()}
    driver.add_entity(first)
    old_refresh = driver._subscription_refresh_tasks[first.id]
    replacement = dashboard("Latest")
    assert driver.update_entity(replacement) is True
    await drain(driver)
    assert old_refresh.cancelled()
    driver.refresh_entity_state.assert_awaited_once_with(first.id)
    assert refreshed == [replacement]
    assert driver.api.configured_entities.get(first.id) is replacement
    assert not driver._subscription_refresh_tasks
    assert [m["msg"] for m in messages(queue)] == [
        "entity_available",
        "entity_available",
    ]


async def test_remove_cancels_pending_subscription_and_is_idempotent(driver):
    queue = client(driver, {"webview"})
    entity = dashboard()
    driver.refresh_entity_state = AsyncMock()
    driver._entity_subscriptions[entity.id] = {object()}
    driver.add_entity(entity, notify=False)
    pending = driver._subscription_refresh_tasks[entity.id]
    driver.remove_entity(entity.id)
    driver.remove_entity(entity.id)
    await drain(driver)
    await asyncio.gather(pending, return_exceptions=True)
    assert pending.cancelled()
    driver.refresh_entity_state.assert_not_awaited()
    assert not driver.api.configured_entities.contains(entity.id)
    assert not driver.api.available_entities.contains(entity.id)
    assert entity.id not in driver._entity_subscriptions
    assert [m["msg"] for m in messages(queue)] == ["entity_removed"]


async def test_silent_removal(driver):
    queue = client(driver, {"webview"})
    entity = dashboard()
    driver.add_entity(entity, notify=False)
    driver.remove_entity(entity.id, notify=False)
    await drain(driver)
    assert messages(queue) == []
    assert not driver.api.available_entities.contains(entity.id)


@pytest.mark.parametrize("operation", ["remove_device", "clear_devices"])
async def test_device_removal_notifies_each_entity(driver, operation):
    queue = client(driver, {"webview", "switch"})
    config = DeviceConfigForTests("dev1", "Device", "localhost")
    driver._add_device_instance(config)
    device = driver._device_instances["dev1"]
    device.disconnect = AsyncMock()
    first = dashboard()
    second = switch.Switch("switch.dev1", "Switch", [], {})
    other = switch.Switch("switch.dev2", "Other", [], {})
    driver.add_entities([first, second, other], notify=False)
    for entity in (first, second):
        driver.api.configured_entities.add(entity)
        driver._entity_subscriptions[entity.id] = {object()}
    if operation == "remove_device":
        driver.remove_device("dev1")
    else:
        driver.clear_devices()
    await drain(driver)
    await asyncio.sleep(0)
    events = messages(queue)
    expected = {first.id, second.id}
    if operation == "clear_devices":
        expected.add(other.id)
    assert {m["msg_data"]["entity_id"] for m in events} == expected
    assert len(events) == len(expected)
    assert all(m["msg"] == "entity_removed" for m in events)
    assert not driver._entity_subscriptions
    assert driver.api.available_entities.contains(other.id) == (
        operation == "remove_device"
    )
    device.disconnect.assert_awaited_once()


async def test_definition_secrets_reach_remote_without_entering_logs(driver, caplog):
    queue = client(driver, {"webview"})
    with caplog.at_level(logging.DEBUG):
        driver.add_entity(dashboard(token="private-api-key"))
        await drain(driver)
    (event,) = messages(queue)
    assert event["msg_data"]["options"]["auth"]["header_value"] == "private-api-key"
    assert event["msg_data"]["options"]["cookies"][0]["value"] == "cookie-secret"
    assert "private-api-key" not in caplog.text
    assert "cookie-secret" not in caplog.text
