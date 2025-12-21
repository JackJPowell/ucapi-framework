"""Tests for migration utilities."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ucapi_framework.migration import (
    MigrationData,
    _activity_uses_driver,
    _replace_entities_in_activity,
    _update_activity_on_remote,
    migrate_entities_on_remote,
    verify_migration,
)


@pytest.fixture
def sample_migration_data() -> MigrationData:
    """Return sample migration data."""
    return {
        "previous_driver_id": "olddriver",
        "new_driver_id": "newdriver",
        "entity_mappings": [
            {"previous_entity_id": "media_player.tv", "new_entity_id": "player.tv"},
            {"previous_entity_id": "light.bedroom", "new_entity_id": "light.bed"},
        ],
    }


@pytest.fixture
def sample_activity() -> dict[str, Any]:
    """Return a sample activity with various entity references."""
    return {
        "entity_id": "activity.movie_night",
        "name": "Movie Night",
        "icon": "movie",
        "options": {
            "included_entities": [
                {"entity_id": "olddriver.main.media_player.tv"},
                {"entity_id": "olddriver.main.light.bedroom"},
                {"entity_id": "otherdriver.main.sensor.temp"},
            ],
            "button_mapping": [
                {
                    "button": "POWER",
                    "short_press": {"entity_id": "olddriver.main.media_player.tv"},
                    "long_press": {"entity_id": "olddriver.main.light.bedroom"},
                },
                {
                    "button": "VOLUME_UP",
                    "short_press": {
                        "entity_id": "otherdriver.main.media_player.receiver"
                    },
                },
            ],
            "user_interface": {
                "pages": [
                    {
                        "page_id": "page1",
                        "name": "Main",
                        "items": [
                            {
                                "command": "olddriver.main.media_player.tv",
                            },
                            {
                                "command": {
                                    "entity_id": "olddriver.main.light.bedroom",
                                    "cmd_id": "toggle",
                                },
                            },
                            {
                                "media_player_id": "olddriver.main.media_player.tv",
                            },
                        ],
                    }
                ]
            },
            "sequences": {
                "on": [
                    {
                        "command": {
                            "entity_id": "olddriver.main.light.bedroom",
                            "cmd_id": "on",
                        }
                    }
                ],
                "off": [
                    {
                        "command": {
                            "entity_id": "olddriver.main.media_player.tv",
                            "cmd_id": "off",
                        }
                    }
                ],
            },
        },
    }


@pytest.fixture
def empty_activity() -> dict[str, Any]:
    """Return an activity with no options."""
    return {
        "entity_id": "activity.empty",
        "name": "Empty Activity",
    }


class TestActivityUsesDriver:
    """Test _activity_uses_driver function."""

    def test_activity_with_driver_entities(self, sample_activity):
        """Test activity that uses entities from the driver."""
        assert _activity_uses_driver(sample_activity, "olddriver.main") is True

    def test_activity_without_driver_entities(self, sample_activity):
        """Test activity that doesn't use entities from the driver."""
        assert _activity_uses_driver(sample_activity, "unknowndriver.main") is False

    def test_activity_with_no_options(self, empty_activity):
        """Test activity with no options."""
        assert _activity_uses_driver(empty_activity, "olddriver.main") is False

    def test_activity_with_no_included_entities(self):
        """Test activity with options but no included_entities."""
        activity = {
            "entity_id": "activity.test",
            "options": {"sequences": {}},
        }
        assert _activity_uses_driver(activity, "olddriver.main") is False

    def test_activity_with_empty_included_entities(self):
        """Test activity with empty included_entities list."""
        activity = {
            "entity_id": "activity.test",
            "options": {"included_entities": []},
        }
        assert _activity_uses_driver(activity, "olddriver.main") is False

    def test_partial_driver_match(self):
        """Test that partial integration ID matches count (substring match)."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "included_entities": [
                    {
                        "entity_id": "olddriver.main2.light.room"
                    },  # Contains olddriver.main
                ]
            },
        }
        # Note: This matches because we use startswith which includes substrings
        assert _activity_uses_driver(activity, "olddriver.main") is True

    def test_different_driver_no_match(self):
        """Test that completely different integration IDs don't match."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "included_entities": [
                    {"entity_id": "newdriver.main.light.room"},  # Different integration
                ]
            },
        }
        assert _activity_uses_driver(activity, "olddriver.main") is False


class TestReplaceEntitiesInActivity:
    """Test _replace_entities_in_activity function."""

    def test_replace_in_included_entities(self, sample_activity, sample_migration_data):
        """Test replacing entities in included_entities."""
        count = _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        assert count == 9  # Total replacements across all locations
        included = sample_activity["options"]["included_entities"]
        assert included[0]["entity_id"] == "newdriver.main.player.tv"
        assert included[1]["entity_id"] == "newdriver.main.light.bed"
        assert included[2]["entity_id"] == "otherdriver.main.sensor.temp"  # Unchanged

    def test_replace_in_button_mapping(self, sample_activity, sample_migration_data):
        """Test replacing entities in button_mapping."""
        _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        buttons = sample_activity["options"]["button_mapping"]
        assert buttons[0]["short_press"]["entity_id"] == "newdriver.main.player.tv"
        assert buttons[0]["long_press"]["entity_id"] == "newdriver.main.light.bed"
        # Other driver unchanged
        assert (
            buttons[1]["short_press"]["entity_id"]
            == "otherdriver.main.media_player.receiver"
        )

    def test_replace_in_ui_pages_string_command(
        self, sample_activity, sample_migration_data
    ):
        """Test replacing string commands in UI pages."""
        _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        items = sample_activity["options"]["user_interface"]["pages"][0]["items"]
        assert items[0]["command"] == "newdriver.main.player.tv"

    def test_replace_in_ui_pages_object_command(
        self, sample_activity, sample_migration_data
    ):
        """Test replacing object commands in UI pages."""
        _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        items = sample_activity["options"]["user_interface"]["pages"][0]["items"]
        assert items[1]["command"]["entity_id"] == "newdriver.main.light.bed"
        assert items[1]["command"]["cmd_id"] == "toggle"  # Other fields preserved

    def test_replace_in_media_player_id(self, sample_activity, sample_migration_data):
        """Test replacing media_player_id in UI pages."""
        _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        items = sample_activity["options"]["user_interface"]["pages"][0]["items"]
        assert items[2]["media_player_id"] == "newdriver.main.player.tv"

    def test_replace_in_sequences(self, sample_activity, sample_migration_data):
        """Test replacing entities in sequences."""
        _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        sequences = sample_activity["options"]["sequences"]
        assert sequences["on"][0]["command"]["entity_id"] == "newdriver.main.light.bed"
        assert sequences["off"][0]["command"]["entity_id"] == "newdriver.main.player.tv"

    def test_no_replacements_for_empty_activity(
        self, empty_activity, sample_migration_data
    ):
        """Test no replacements are made for empty activity."""
        count = _replace_entities_in_activity(
            empty_activity,
            sample_migration_data["entity_mappings"],
            "olddriver.main",
            "newdriver.main",
        )

        assert count == 0

    def test_no_replacements_for_different_driver(
        self, sample_activity, sample_migration_data
    ):
        """Test no replacements when integration doesn't match."""
        count = _replace_entities_in_activity(
            sample_activity,
            sample_migration_data["entity_mappings"],
            "differentdriver.main",
            "newdriver.main",
        )

        assert count == 0
        # Verify nothing changed
        assert (
            sample_activity["options"]["included_entities"][0]["entity_id"]
            == "olddriver.main.media_player.tv"
        )

    def test_handles_button_without_presses(self):
        """Test handling buttons with no press actions."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "button_mapping": [
                    {"button": "EMPTY"},  # No short/long/double press
                ]
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "test", "new_entity_id": "new"}],
            "old.main",
            "new.main",
        )

        assert count == 0

    def test_handles_double_press(self):
        """Test handling double_press in buttons."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "button_mapping": [
                    {
                        "button": "TEST",
                        "double_press": {"entity_id": "old.main.test"},
                    }
                ]
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "test", "new_entity_id": "new"}],
            "old.main",
            "new.main",
        )

        assert count == 1
        assert (
            activity["options"]["button_mapping"][0]["double_press"]["entity_id"]
            == "new.main.new"
        )

    def test_handles_non_list_sequences(self):
        """Test handling sequences that aren't lists."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "sequences": {
                    "invalid": "not a list",  # Should be skipped
                }
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "test", "new_entity_id": "new"}],
            "old.main",
            "new.main",
        )

        assert count == 0

    def test_multiple_buttons_all_press_types(self):
        """Test activity with multiple buttons using all press types."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "button_mapping": [
                    {
                        "button": "POWER",
                        "short_press": {"entity_id": "old.main.entity1"},
                        "long_press": {"entity_id": "old.main.entity2"},
                        "double_press": {"entity_id": "old.main.entity3"},
                    },
                    {
                        "button": "MUTE",
                        "short_press": {"entity_id": "old.main.entity1"},
                    },
                ]
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [
                {"previous_entity_id": "entity1", "new_entity_id": "new1"},
                {"previous_entity_id": "entity2", "new_entity_id": "new2"},
                {"previous_entity_id": "entity3", "new_entity_id": "new3"},
            ],
            "old.main",
            "new.main",
        )

        assert count == 4
        buttons = activity["options"]["button_mapping"]
        assert buttons[0]["short_press"]["entity_id"] == "new.main.new1"
        assert buttons[0]["long_press"]["entity_id"] == "new.main.new2"
        assert buttons[0]["double_press"]["entity_id"] == "new.main.new3"
        assert buttons[1]["short_press"]["entity_id"] == "new.main.new1"

    def test_multiple_pages_with_mixed_commands(self):
        """Test multiple UI pages with both string and object commands."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "user_interface": {
                    "pages": [
                        {
                            "page_id": "page1",
                            "name": "Page 1",
                            "items": [
                                {"command": "old.main.entity1"},
                                {
                                    "command": {
                                        "entity_id": "old.main.entity2",
                                        "cmd_id": "on",
                                    }
                                },
                            ],
                        },
                        {
                            "page_id": "page2",
                            "name": "Page 2",
                            "items": [
                                {"media_player_id": "old.main.entity1"},
                            ],
                        },
                    ]
                }
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [
                {"previous_entity_id": "entity1", "new_entity_id": "new1"},
                {"previous_entity_id": "entity2", "new_entity_id": "new2"},
            ],
            "old.main",
            "new.main",
        )

        assert count == 3
        pages = activity["options"]["user_interface"]["pages"]
        assert pages[0]["items"][0]["command"] == "new.main.new1"
        assert pages[0]["items"][1]["command"]["entity_id"] == "new.main.new2"
        assert pages[1]["items"][0]["media_player_id"] == "new.main.new1"

    def test_both_on_and_off_sequences(self):
        """Test activity with both on and off sequences."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "sequences": {
                    "on": [
                        {"command": {"entity_id": "old.main.entity1", "cmd_id": "on"}},
                        {"command": {"entity_id": "old.main.entity2", "cmd_id": "on"}},
                    ],
                    "off": [
                        {"command": {"entity_id": "old.main.entity1", "cmd_id": "off"}},
                    ],
                }
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [
                {"previous_entity_id": "entity1", "new_entity_id": "new1"},
                {"previous_entity_id": "entity2", "new_entity_id": "new2"},
            ],
            "old.main",
            "new.main",
        )

        assert count == 3
        sequences = activity["options"]["sequences"]
        assert sequences["on"][0]["command"]["entity_id"] == "new.main.new1"
        assert sequences["on"][1]["command"]["entity_id"] == "new.main.new2"
        assert sequences["off"][0]["command"]["entity_id"] == "new.main.new1"

    def test_page_command_without_entity_id(self):
        """Test page items with commands that don't have entity_id."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "user_interface": {
                    "pages": [
                        {
                            "page_id": "page1",
                            "name": "Page 1",
                            "items": [
                                {
                                    "command": {"cmd_id": "play"}  # No entity_id field
                                },
                            ],
                        }
                    ]
                }
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "entity1", "new_entity_id": "new1"}],
            "old.main",
            "new.main",
        )

        assert count == 0

    def test_button_press_without_entity_id(self):
        """Test button presses that don't have entity_id field."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "button_mapping": [
                    {
                        "button": "POWER",
                        "short_press": {"cmd_id": "toggle"},  # No entity_id
                    }
                ]
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "test", "new_entity_id": "new"}],
            "old.main",
            "new.main",
        )

        assert count == 0

    def test_sequence_command_without_entity_id(self):
        """Test sequences with commands that don't have entity_id."""
        activity = {
            "entity_id": "activity.test",
            "options": {
                "sequences": {
                    "on": [
                        {"command": {"cmd_id": "on"}},  # No entity_id
                        {"delay": 1000},  # Not a command at all
                    ]
                }
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [{"previous_entity_id": "test", "new_entity_id": "new"}],
            "old.main",
            "new.main",
        )

        assert count == 0

    def test_all_locations_in_one_activity(self):
        """Test comprehensive activity with entities in all possible locations."""
        activity = {
            "entity_id": "activity.comprehensive",
            "options": {
                "included_entities": [
                    {"entity_id": "old.main.entity1"},
                    {"entity_id": "old.main.entity2"},
                ],
                "button_mapping": [
                    {
                        "button": "POWER",
                        "short_press": {"entity_id": "old.main.entity1"},
                        "long_press": {"entity_id": "old.main.entity2"},
                        "double_press": {"entity_id": "old.main.entity3"},
                    }
                ],
                "user_interface": {
                    "pages": [
                        {
                            "page_id": "page1",
                            "items": [
                                {"command": "old.main.entity1"},
                                {
                                    "command": {
                                        "entity_id": "old.main.entity2",
                                        "params": {},
                                    }
                                },
                                {"media_player_id": "old.main.entity3"},
                            ],
                        }
                    ]
                },
                "sequences": {
                    "on": [{"command": {"entity_id": "old.main.entity1"}}],
                    "off": [{"command": {"entity_id": "old.main.entity2"}}],
                },
            },
        }

        count = _replace_entities_in_activity(
            activity,
            [
                {"previous_entity_id": "entity1", "new_entity_id": "new1"},
                {"previous_entity_id": "entity2", "new_entity_id": "new2"},
                {"previous_entity_id": "entity3", "new_entity_id": "new3"},
            ],
            "old.main",
            "new.main",
        )

        # 2 included + 3 button presses + 3 UI items + 2 sequences = 10 replacements
        assert count == 10


@pytest.mark.asyncio
class TestUpdateActivityOnRemote:
    """Test _update_activity_on_remote function."""

    async def test_successful_update_complete_activity(self, sample_activity):
        """Test successfully updating a complete activity."""
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="OK")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.patch = MagicMock(return_value=mock_response)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            sample_activity,
            {"Content-Type": "application/json"},
            None,
        )

        assert result is True
        # Verify main activity was updated
        assert mock_session.patch.call_count >= 1

    async def test_activity_without_entity_id(self):
        """Test handling activity without entity_id."""
        mock_session = MagicMock()
        activity = {"name": "Test"}  # Missing entity_id

        result = await _update_activity_on_remote(
            mock_session, "http://192.168.1.100", activity, {}, None
        )

        assert result is False

    async def test_failed_activity_update(self, sample_activity):
        """Test handling failed activity update."""
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.patch = MagicMock(return_value=mock_response)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            sample_activity,
            {"Content-Type": "application/json"},
            None,
        )

        assert result is False

    async def test_update_with_icon(self):
        """Test updating activity with icon."""
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session.patch = MagicMock(return_value=mock_response)

        activity = {
            "entity_id": "activity.test",
            "name": "Test",
            "icon": "custom-icon",
            "options": {},
        }

        result = await _update_activity_on_remote(
            mock_session, "http://192.168.1.100", activity, {}, None
        )

        assert result is True

    async def test_button_update_failure_doesnt_fail_migration(self, sample_activity):
        """Test that button update failures don't fail the entire migration."""
        mock_session = MagicMock()

        # Main activity succeeds
        main_response = AsyncMock()
        main_response.status = 200
        main_response.text = AsyncMock(return_value="")
        main_response.__aenter__ = AsyncMock(return_value=main_response)
        main_response.__aexit__ = AsyncMock(return_value=None)

        # Button update fails
        button_response = AsyncMock()
        button_response.status = 500
        button_response.text = AsyncMock(return_value="")
        button_response.__aenter__ = AsyncMock(return_value=button_response)
        button_response.__aexit__ = AsyncMock(return_value=None)

        # Page update succeeds
        page_response = AsyncMock()
        page_response.status = 200
        page_response.text = AsyncMock(return_value="")
        page_response.__aenter__ = AsyncMock(return_value=page_response)
        page_response.__aexit__ = AsyncMock(return_value=None)

        responses = [main_response, button_response, button_response, page_response]
        mock_session.patch = MagicMock(side_effect=responses)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            sample_activity,
            {"Content-Type": "application/json"},
            None,
        )

        assert result is True  # Still succeeds despite button failures

    async def test_page_update_failure_doesnt_fail_migration(self, sample_activity):
        """Test that page update failures don't fail the entire migration."""
        mock_session = MagicMock()

        # Main activity and buttons succeed, page fails
        success_response = AsyncMock()
        success_response.status = 200
        success_response.__aenter__ = AsyncMock(return_value=success_response)
        success_response.__aexit__ = AsyncMock(return_value=None)

        fail_response = AsyncMock()
        fail_response.status = 404
        fail_response.__aenter__ = AsyncMock(return_value=fail_response)
        fail_response.__aexit__ = AsyncMock(return_value=fail_response)

        responses = [
            success_response,
            success_response,
            success_response,
            fail_response,
        ]
        mock_session.patch = MagicMock(side_effect=responses)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            sample_activity,
            {"Content-Type": "application/json"},
            None,
        )

        assert result is True

    async def test_exception_handling(self, sample_activity):
        """Test handling of exceptions during update."""
        mock_session = MagicMock()
        mock_session.patch = MagicMock(side_effect=Exception("Network error"))

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            sample_activity,
            {"Content-Type": "application/json"},
            None,
        )

        assert result is False

    async def test_button_without_name(self):
        """Test handling of button without button name."""
        activity = {
            "entity_id": "activity.test",
            "name": "Test",
            "options": {
                "button_mapping": [
                    {
                        # Missing "button" field
                        "short_press": {"entity_id": "olddriver.main.media_player.tv"},
                    }
                ],
            },
        }

        mock_session = MagicMock()

        # Mock successful activity update
        activity_response = AsyncMock()
        activity_response.status = 200
        activity_response.__aenter__ = AsyncMock(return_value=activity_response)
        activity_response.__aexit__ = AsyncMock()

        mock_session.patch = MagicMock(return_value=activity_response)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            activity,
            {"Content-Type": "application/json"},
            None,
        )

        # Should succeed (button is skipped, only activity is updated)
        assert result is True
        # Patch should only be called once for activity (not for button without name)
        assert mock_session.patch.call_count == 1

    async def test_page_without_id(self):
        """Test handling of page without page_id."""
        activity = {
            "entity_id": "activity.test",
            "name": "Test",
            "options": {
                "user_interface": {
                    "pages": [
                        {
                            # Missing "page_id" field
                            "name": "Main",
                            "items": [{"command": "test"}],
                        }
                    ]
                },
            },
        }

        mock_session = MagicMock()

        # Mock successful activity update
        activity_response = AsyncMock()
        activity_response.status = 200
        activity_response.__aenter__ = AsyncMock(return_value=activity_response)
        activity_response.__aexit__ = AsyncMock()

        mock_session.patch = MagicMock(return_value=activity_response)

        result = await _update_activity_on_remote(
            mock_session,
            "http://192.168.1.100",
            activity,
            {"Content-Type": "application/json"},
            None,
        )

        # Should succeed (page is skipped, only activity is updated)
        assert result is True
        # Patch should only be called once for activity (not for page without id)
        assert mock_session.patch.call_count == 1


@pytest.mark.asyncio
class TestMigrateEntitiesOnRemote:
    """Test migrate_entities_on_remote function."""

    async def test_successful_migration(self, sample_migration_data):
        """Test successful migration with activities."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            # Setup mock session and responses
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock GET /api/activities (list)
            activities_response = AsyncMock()
            activities_response.status = 200
            activities_response.json = AsyncMock(
                return_value=[{"entity_id": "activity.test"}]
            )

            # Mock GET /api/activities/{id} (details)
            activity_response = AsyncMock()
            activity_response.status = 200
            activity_response.json = AsyncMock(
                return_value={
                    "entity_id": "activity.test",
                    "name": "Test",
                    "options": {
                        "included_entities": [
                            {"entity_id": "olddriver.main.media_player.tv"}
                        ]
                    },
                }
            )

            # Mock PATCH responses
            patch_response = AsyncMock()
            patch_response.status = 200

            # Setup context managers
            activities_response.__aenter__ = AsyncMock(return_value=activities_response)
            activities_response.__aexit__ = AsyncMock()
            activity_response.__aenter__ = AsyncMock(return_value=activity_response)
            activity_response.__aexit__ = AsyncMock()
            patch_response.__aenter__ = AsyncMock(return_value=patch_response)
            patch_response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(
                side_effect=[activities_response, activity_response]
            )
            mock_session.patch = MagicMock(return_value=patch_response)

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data, pin="1234"
            )

            assert result is True

    async def test_no_auth_raises_error(self, sample_migration_data):
        """Test that missing authentication raises ValueError."""
        with pytest.raises(ValueError, match="Either pin or api_key must be provided"):
            await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data
            )

    async def test_empty_mappings_returns_true(self):
        """Test that empty mappings returns True immediately."""
        migration_data: MigrationData = {
            "previous_driver_id": "old",
            "new_driver_id": "new",
            "entity_mappings": [],
        }

        result = await migrate_entities_on_remote(
            "http://192.168.1.100", migration_data, pin="1234"
        )

        assert result is True

    async def test_failed_activities_fetch(self, sample_migration_data):
        """Test handling failed activities fetch."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock failed response
            response = AsyncMock()
            response.status = 500
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data, pin="1234"
            )

            assert result is False

    async def test_activities_without_matching_driver(self, sample_migration_data):
        """Test activities that don't use the old driver are skipped."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock responses
            activities_response = AsyncMock()
            activities_response.status = 200
            activities_response.json = AsyncMock(
                return_value=[{"entity_id": "activity.test"}]
            )

            # Activity with different driver
            activity_response = AsyncMock()
            activity_response.status = 200
            activity_response.json = AsyncMock(
                return_value={
                    "entity_id": "activity.test",
                    "options": {
                        "included_entities": [
                            {"entity_id": "differentdriver.light.room"}
                        ]
                    },
                }
            )

            activities_response.__aenter__ = AsyncMock(return_value=activities_response)
            activities_response.__aexit__ = AsyncMock()
            activity_response.__aenter__ = AsyncMock(return_value=activity_response)
            activity_response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(
                side_effect=[activities_response, activity_response]
            )

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data, pin="1234"
            )

            # Should succeed even though no activities were migrated
            assert result is True

    async def test_network_error_handling(self, sample_migration_data):
        """Test handling of network errors."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientError = Exception
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Simulate network error
            mock_session.get = MagicMock(side_effect=Exception("Network error"))

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data, pin="1234"
            )

            assert result is False

    async def test_api_key_authentication(self, sample_migration_data):
        """Test using API key authentication instead of PIN."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock empty activities list
            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(return_value=[])
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", sample_migration_data, api_key="test-key"
            )

            assert result is True

    async def test_driver_id_with_main_suffix_not_modified(self):
        """Test that driver_id ending with .main is not modified."""
        migration_data: MigrationData = {
            "previous_driver_id": "olddriver.main",  # Already has .main
            "new_driver_id": "newdriver.main",  # Already has .main
            "entity_mappings": [
                {"previous_entity_id": "media_player.tv", "new_entity_id": "player.tv"}
            ],
        }

        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock GET /api/activities (list)
            activities_response = AsyncMock()
            activities_response.status = 200
            activities_response.json = AsyncMock(
                return_value=[{"entity_id": "activity.test"}]
            )

            # Mock GET /api/activities/{id} (details)
            activity_response = AsyncMock()
            activity_response.status = 200
            activity_response.json = AsyncMock(
                return_value={
                    "entity_id": "activity.test",
                    "name": "Test",
                    "options": {
                        "included_entities": [
                            # Entity should match olddriver.main (not olddriver.main.main)
                            {"entity_id": "olddriver.main.media_player.tv"}
                        ]
                    },
                }
            )

            # Mock PATCH responses
            patch_response = AsyncMock()
            patch_response.status = 200

            # Setup context managers
            activities_response.__aenter__ = AsyncMock(return_value=activities_response)
            activities_response.__aexit__ = AsyncMock()
            activity_response.__aenter__ = AsyncMock(return_value=activity_response)
            activity_response.__aexit__ = AsyncMock()
            patch_response.__aenter__ = AsyncMock(return_value=patch_response)
            patch_response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(
                side_effect=[activities_response, activity_response]
            )
            mock_session.patch = MagicMock(return_value=patch_response)

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", migration_data, pin="1234"
            )

            assert result is True

    async def test_activity_fetch_fails_individual_activity(self):
        """Test handling when fetching individual activity details fails."""
        migration_data = {
            "previous_driver_id": "olddriver",
            "new_driver_id": "newdriver",
            "entity_mappings": [
                {
                    "previous_entity_id": "media_player.tv",
                    "new_entity_id": "player.tv",
                },
            ],
        }

        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock activities list response
            activities_list = AsyncMock()
            activities_list.status = 200
            activities_list.json = AsyncMock(
                return_value=[
                    {"entity_id": "activity.test1"},
                    {"entity_id": "activity.test2"},
                ]
            )
            activities_list.__aenter__ = AsyncMock(return_value=activities_list)
            activities_list.__aexit__ = AsyncMock()

            # Mock individual activity fetch - first one fails, second succeeds
            failed_response = AsyncMock()
            failed_response.status = 404
            failed_response.__aenter__ = AsyncMock(return_value=failed_response)
            failed_response.__aexit__ = AsyncMock()

            success_response = AsyncMock()
            success_response.status = 200
            success_response.json = AsyncMock(
                return_value={
                    "entity_id": "activity.test2",
                    "name": "Test Activity",
                    "options": {"included_entities": []},
                }
            )
            success_response.__aenter__ = AsyncMock(return_value=success_response)
            success_response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(
                side_effect=[activities_list, failed_response, success_response]
            )

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", migration_data, pin="1234"
            )

            # Should succeed despite one activity fetch failing
            assert result is True

    async def test_unexpected_exception_during_migration(self):
        """Test handling of unexpected exceptions during migration."""
        migration_data = {
            "previous_driver_id": "olddriver",
            "new_driver_id": "newdriver",
            "entity_mappings": [
                {
                    "previous_entity_id": "media_player.tv",
                    "new_entity_id": "player.tv",
                },
            ],
        }

        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientError = Exception
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock unexpected exception (not ClientError)
            mock_session.get = MagicMock(side_effect=RuntimeError("Unexpected error"))

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", migration_data, pin="1234"
            )

            assert result is False

    async def test_activity_without_entity_id_in_list(self):
        """Test handling activities list with entries missing entity_id."""
        migration_data = {
            "previous_driver_id": "olddriver",
            "new_driver_id": "newdriver",
            "entity_mappings": [
                {
                    "previous_entity_id": "media_player.tv",
                    "new_entity_id": "player.tv",
                },
            ],
        }

        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock activities list with one missing entity_id and one valid
            activities_list = AsyncMock()
            activities_list.status = 200
            activities_list.json = AsyncMock(
                return_value=[
                    {"name": "Invalid"},  # Missing entity_id
                    {"entity_id": "activity.test"},
                ]
            )
            activities_list.__aenter__ = AsyncMock(return_value=activities_list)
            activities_list.__aexit__ = AsyncMock()

            # Mock valid activity details
            activity_response = AsyncMock()
            activity_response.status = 200
            activity_response.json = AsyncMock(
                return_value={
                    "entity_id": "activity.test",
                    "name": "Test Activity",
                    "options": {"included_entities": []},
                }
            )
            activity_response.__aenter__ = AsyncMock(return_value=activity_response)
            activity_response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(
                side_effect=[activities_list, activity_response]
            )

            result = await migrate_entities_on_remote(
                "http://192.168.1.100", migration_data, pin="1234"
            )

            # Should succeed (invalid entry is skipped)
            assert result is True


@pytest.mark.asyncio
class TestVerifyMigration:
    """Test verify_migration function."""

    async def test_successful_verification(self):
        """Test successful verification of migrated entities."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock response with entities
            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(
                return_value={
                    "entities": [
                        {"entity_id": "newdriver.player.tv"},
                        {"entity_id": "newdriver.light.bed"},
                    ]
                }
            )
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await verify_migration(
                "http://192.168.1.100",
                ["newdriver.player.tv", "newdriver.light.bed"],
                pin="1234",
            )

            assert result is True

    async def test_missing_entities(self):
        """Test verification fails when entities are missing."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock response missing some entities
            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(
                return_value={
                    "entities": [
                        {"entity_id": "newdriver.player.tv"},
                        # Missing newdriver.light.bed
                    ]
                }
            )
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await verify_migration(
                "http://192.168.1.100",
                ["newdriver.player.tv", "newdriver.light.bed"],
                pin="1234",
            )

            assert result is False

    async def test_no_auth_raises_error(self):
        """Test that missing authentication raises ValueError."""
        with pytest.raises(ValueError, match="Either pin or api_key must be provided"):
            await verify_migration("http://192.168.1.100", ["entity.test"])

    async def test_failed_request(self):
        """Test handling failed verification request."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock failed response
            response = AsyncMock()
            response.status = 500
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await verify_migration(
                "http://192.168.1.100", ["entity.test"], pin="1234"
            )

            assert result is False

    async def test_network_error(self):
        """Test handling network errors during verification."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientError = Exception
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            mock_session.get = MagicMock(side_effect=Exception("Network error"))

            result = await verify_migration(
                "http://192.168.1.100", ["entity.test"], pin="1234"
            )

            assert result is False

    async def test_api_key_authentication(self):
        """Test verification with API key instead of PIN."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientTimeout = MagicMock()

            response = AsyncMock()
            response.status = 200
            response.json = AsyncMock(
                return_value={"entities": [{"entity_id": "test.entity"}]}
            )
            response.__aenter__ = AsyncMock(return_value=response)
            response.__aexit__ = AsyncMock()

            mock_session.get = MagicMock(return_value=response)

            result = await verify_migration(
                "http://192.168.1.100", ["test.entity"], api_key="test-key"
            )

            assert result is True

    async def test_unexpected_exception_during_verification(self):
        """Test handling of unexpected exceptions during verification."""
        with patch("ucapi_framework.migration.aiohttp") as mock_aiohttp:
            mock_session = AsyncMock()
            mock_aiohttp.ClientSession.return_value.__aenter__.return_value = (
                mock_session
            )
            mock_aiohttp.ClientError = Exception
            mock_aiohttp.BasicAuth = MagicMock()
            mock_aiohttp.ClientTimeout = MagicMock()

            # Mock unexpected exception (not ClientError)
            mock_session.get = MagicMock(side_effect=RuntimeError("Unexpected error"))

            result = await verify_migration(
                "http://192.168.1.100", ["entity.test"], pin="1234"
            )

            assert result is False
