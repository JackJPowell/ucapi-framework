"""Number state management against the real ucapi entity store."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from ucapi import Entities, EntityTypes, StatusCodes, number
from ucapi_framework import NumberAttributes, NumberEntity


@pytest.fixture
async def entity():
    entity = NumberEntity(
        "number.amp.bass",
        "Bass",
        [number.Features.TRANSITION],
        {number.Attributes.STATE: number.States.ON, number.Attributes.VALUE: 2.5},
        device_class=number.DeviceClasses.AUDIO_LEVEL,
        options={
            number.Options.MIN: None,
            number.Options.MAX: 10,
            number.Options.STEP: 0.5,
            number.Options.UNIT: "dB",
            number.Options.READABLE: False,
        },
    )
    api = MagicMock()
    api.configured_entities = Entities("configured", asyncio.get_running_loop())
    api.configured_entities.add(entity)
    entity._api = api
    return entity


async def test_metadata_and_options(entity):
    definition = json.loads(json.dumps(entity._api.configured_entities.get_all()))[0]
    assert definition["entity_type"] == "number"
    assert definition["device_class"] == "audio_level"
    assert definition["options"]["min"] is None
    assert definition["options"]["readable"] is False
    assert entity.entity_type == EntityTypes.NUMBER
    assert entity.state == number.States.ON
    assert entity.value == 2.5


async def test_setters_emit_changes_when_store_holds_same_object(entity):
    store = entity._api.configured_entities
    store.update_attributes = MagicMock(wraps=store.update_attributes)
    entity.set_value(0, update=True)
    store.update_attributes.assert_called_once_with(
        entity.id, {number.Attributes.VALUE: 0}
    )
    assert entity.value == 0
    store.update_attributes.reset_mock()
    entity.set_value(0, update=True)
    store.update_attributes.assert_not_called()


async def test_unknown_value_and_omitted_bulk_value(entity):
    store = entity._api.configured_entities
    store.update_attributes = MagicMock(wraps=store.update_attributes)
    entity.set_attributes(state=number.States.UNKNOWN, update=True)
    assert entity.value == 2.5
    store.update_attributes.reset_mock()
    entity.set_attributes(value=None, update=True)
    store.update_attributes.assert_called_once_with(
        entity.id, {number.Attributes.VALUE: None}
    )
    assert entity.value is None
    assert (await store.get_states())[0]["attributes"]["value"] is None


async def test_staged_changes(entity):
    entity.update = MagicMock(wraps=entity.update)
    entity.set_value(4)
    entity.set_state(number.States.UNKNOWN)
    entity.update.assert_not_called()
    assert entity.value == 4
    assert entity.state == number.States.UNKNOWN
    entity.set_attributes(update=True)
    assert entity.update.call_args.args[0] == {"state": "UNKNOWN", "value": 4}


async def test_dataclass_mapping_and_explicit_null_dict(entity):
    entity.update(NumberAttributes(VALUE=-1))
    assert entity.value == -1
    entity.update(NumberAttributes(STATE=number.States.UNKNOWN))
    assert entity.value == -1
    entity.update({"value": None})
    assert entity.value is None
    entity.attributes.pop("value")
    entity.update({"value": None})
    assert "value" in entity.attributes


@pytest.mark.parametrize(
    "command,params",
    [
        (number.Commands.SET_VALUE, {"value": 1, "duration": 2000}),
        (number.Commands.INCREMENT, None),
        (number.Commands.DECREMENT, {"step": 0.5}),
    ],
)
async def test_command_handler(command, params):
    handler = AsyncMock(return_value=StatusCodes.OK)
    entity = NumberEntity("number.test", "Test", [], {}, cmd_handler=handler)
    assert await entity.command(command, params, websocket=None) == StatusCodes.OK
    handler.assert_awaited_once_with(entity, command, params, websocket=None)
