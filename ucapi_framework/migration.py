"""
Migration utilities for Unfolded Circle Remote integrations.

Provides helper methods for performing entity migrations on the Remote.

:copyright: (c) 2025 by Jack Powell.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any, TypedDict
import aiohttp

_LOG = logging.getLogger(__name__)


class EntityMigrationMapping(TypedDict):
    """Entity migration mapping for version upgrades.

    Used by get_migration_data() to specify how entity IDs should be renamed
    during integration upgrades.
    """

    previous_entity_id: str
    """The old entity ID (without driver_id prefix) that needs to be migrated."""

    new_entity_id: str
    """The new entity ID (without driver_id prefix) to replace the old one."""


class MigrationData(TypedDict):
    """Complete migration data including driver IDs and entity mappings.

    This is the full structure returned by get_migration_data() and used by
    migrate_entities_on_remote() to perform the migration.

    **Important:** Specify driver_id WITHOUT the ".main" suffix. The migration
    function will automatically append ".main" to create the integration_id used
    by the Remote API.
    """

    previous_driver_id: str
    """The old/previous driver ID (without .main suffix, e.g., 'mydriver_v1')."""

    new_driver_id: str
    """The new/current driver ID (without .main suffix, e.g., 'mydriver_v2')."""

    entity_mappings: list[EntityMigrationMapping]
    """List of entity ID mappings to apply during migration (without integration_id prefix)."""


async def migrate_entities_on_remote(
    remote_url: str,
    migration_data: MigrationData,
    pin: str | None = None,
    api_key: str | None = None,
) -> bool:
    """
    Perform entity migration on the Remote by updating activity configurations.

    This method performs a comprehensive migration by:
    1. Fetching all activities from the Remote
    2. Finding activities that use entities from the old integration
    3. Replacing old entity IDs with new ones in all locations:
       - included_entities
       - button_mapping (short_press, long_press, double_press)
       - user_interface pages (command, media_player_id)
       - sequences (on/off)
    4. Updating each activity via the Remote API

    **Important:** The Remote uses `integration_id.entity_id` format where
    `integration_id = driver_id + ".main"`. For example, if your driver_id is "mydriver",
    the full entity IDs will be "mydriver.main.media_player.tv". This function automatically
    appends ".main" to the driver_ids provided in migration_data.

    **Note:** If a driver_id already ends with ".main", the framework assumes you've passed
    the full integration_id and will NOT append ".main" again. A log message will indicate
    this behavior.

    Authentication can be done via PIN (Basic Auth) or API key (Bearer token).
    One of `pin` or `api_key` must be provided.

    :param remote_url: The Remote's base URL (e.g., "http://192.168.1.100")
    :param migration_data: Complete migration data with driver IDs (without .main suffix) and entity mappings
    :param pin: Remote's web-configurator PIN for Basic Auth (username: "web-configurator")
    :param api_key: Remote's API key for Bearer token authentication
    :return: True if migration was successful, False otherwise
    :raises ValueError: If neither pin nor api_key is provided

    Example - Using PIN:
        # Developer specifies driver_id (without .main suffix)
        # The function automatically converts to integration_id (driver_id.main)
        migration_data = {
            "previous_driver_id": "mydriver_v1",  # Becomes "mydriver_v1.main" internally
            "new_driver_id": "mydriver_v2",        # Becomes "mydriver_v2.main" internally
            "entity_mappings": [
                # Entity IDs WITHOUT driver_id/integration_id prefix
                {"previous_entity_id": "media_player.tv", "new_entity_id": "player.tv"},
                {"previous_entity_id": "light.bedroom", "new_entity_id": "light.bed"},
            ]
        }
        # Actual entity IDs in Remote will be:
        # "mydriver_v1.main.media_player.tv" -> "mydriver_v2.main.player.tv"
        # "mydriver_v1.main.light.bedroom" -> "mydriver_v2.main.light.bed"

        success = await migrate_entities_on_remote(
            remote_url="http://192.168.1.100",
            migration_data=migration_data,
            pin="1234"
        )

    Example - Using API key:
        success = await migrate_entities_on_remote(
            remote_url="http://192.168.1.100",
            migration_data=migration_data,
            api_key="your-api-key-here"
        )
    """
    if not pin and not api_key:
        raise ValueError("Either pin or api_key must be provided for authentication")

    mappings = migration_data["entity_mappings"]
    previous_driver_id = migration_data["previous_driver_id"]
    new_driver_id = migration_data["new_driver_id"]

    # Convert driver_id to integration_id by appending ".main"
    # Entity IDs in Remote are: integration_id.entity_id (e.g., "mydriver.main.media_player.tv")
    # Naive check: if driver_id already ends with .main, assume it's the full integration_id
    if previous_driver_id.endswith(".main"):
        previous_integration_id = previous_driver_id
        _LOG.info(
            "Previous driver_id '%s' already ends with '.main' - using as-is (framework did not append .main)",
            previous_driver_id,
        )
    else:
        previous_integration_id = f"{previous_driver_id}.main"

    if new_driver_id.endswith(".main"):
        new_integration_id = new_driver_id
        _LOG.info(
            "New driver_id '%s' already ends with '.main' - using as-is (framework did not append .main)",
            new_driver_id,
        )
    else:
        new_integration_id = f"{new_driver_id}.main"

    if not mappings:
        _LOG.info("No entity mappings to migrate")
        return True

    _LOG.info(
        "Migrating %d entity mappings on Remote at %s (integration: %s -> %s)",
        len(mappings),
        remote_url,
        previous_integration_id,
        new_integration_id,
    )

    # Build authentication
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    auth = None
    if pin:
        auth = aiohttp.BasicAuth(login="web-configurator", password=pin)

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Get all activities
            activities_url = f"{remote_url}/api/activities"
            async with session.get(
                activities_url,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    _LOG.error("Failed to fetch activities: HTTP %d", response.status)
                    return False

                activities_list = await response.json()
                _LOG.info("Found %d activities to check", len(activities_list))

            # Step 2: Fetch full activity details and filter by driver
            activities_to_migrate: list[dict[str, Any]] = []
            for activity_summary in activities_list:
                entity_id = activity_summary.get("entity_id")
                if not entity_id:
                    continue

                # Get full activity details
                activity_url = f"{remote_url}/api/activities/{entity_id}"
                async with session.get(
                    activity_url,
                    headers=headers,
                    auth=auth,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        _LOG.warning(
                            "Failed to fetch activity %s: HTTP %d",
                            entity_id,
                            response.status,
                        )
                        continue

                    activity = await response.json()

                    # Check if this activity uses entities from the old integration
                    if _activity_uses_driver(activity, previous_integration_id):
                        activities_to_migrate.append(activity)
                        _LOG.debug(
                            "Activity %s uses integration %s, will migrate",
                            entity_id,
                            previous_integration_id,
                        )

            _LOG.info("Found %d activities to migrate", len(activities_to_migrate))

            # Step 3: Replace entity IDs in each activity
            total_replacements = 0
            for activity in activities_to_migrate:
                replacements = _replace_entities_in_activity(
                    activity, mappings, previous_integration_id, new_integration_id
                )
                total_replacements += replacements
                _LOG.info(
                    "Replaced %d entity references in activity %s",
                    replacements,
                    activity.get("entity_id"),
                )

            # Step 4: Update each activity on the Remote
            success_count = 0
            for activity in activities_to_migrate:
                if await _update_activity_on_remote(
                    session, remote_url, activity, headers, auth
                ):
                    success_count += 1

            _LOG.info(
                "Migration complete: %d/%d activities updated, %d total entity replacements",
                success_count,
                len(activities_to_migrate),
                total_replacements,
            )

            return success_count == len(activities_to_migrate)

    except aiohttp.ClientError as err:
        _LOG.error("Network error during migration: %s", err)
        return False
    except Exception as err:  # pylint: disable=broad-except
        _LOG.error("Unexpected error during migration: %s", err)
        return False


def _activity_uses_driver(activity: dict[str, Any], integration_id: str) -> bool:
    """Check if an activity uses entities from the specified integration.

    Args:
        activity: The activity configuration dict
        integration_id: The integration ID (driver_id.main) to check for
    """
    options = activity.get("options")
    if not options:
        return False

    # Check included_entities
    included_entities = options.get("included_entities", [])
    for entity in included_entities:
        entity_id = entity.get("entity_id", "")
        if entity_id.startswith(integration_id):
            return True

    return False


def _replace_entities_in_activity(
    activity: dict[str, Any],
    mappings: list[EntityMigrationMapping],
    old_integration_id: str,
    new_integration_id: str,
) -> int:
    """
    Replace entity IDs in an activity configuration.

    Args:
        activity: The activity configuration dict
        mappings: List of entity ID mappings (without integration_id prefix)
        old_integration_id: Previous integration ID (driver_id.main)
        new_integration_id: New integration ID (driver_id.main)

    Returns the number of replacements made.
    """
    replaced_count = 0
    options = activity.get("options")
    if not options:
        return replaced_count

    # Replace in included_entities
    included_entities = options.get("included_entities", [])
    for entity in included_entities:
        for mapping in mappings:
            full_old_id = f"{old_integration_id}.{mapping['previous_entity_id']}"
            if entity.get("entity_id") == full_old_id:
                full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                _LOG.debug(
                    "  Replacing included entity: %s -> %s", full_old_id, full_new_id
                )
                entity["entity_id"] = full_new_id
                replaced_count += 1
                break

    # Replace in button_mapping
    button_mapping = options.get("button_mapping", [])
    for button in button_mapping:
        button_name = button.get("button", "unknown")

        # Check short_press
        short_press = button.get("short_press")
        if short_press and "entity_id" in short_press:
            for mapping in mappings:
                full_old_id = f"{old_integration_id}.{mapping['previous_entity_id']}"
                if short_press["entity_id"] == full_old_id:
                    full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                    _LOG.debug(
                        "  Replacing button %s short_press: %s -> %s",
                        button_name,
                        full_old_id,
                        full_new_id,
                    )
                    short_press["entity_id"] = full_new_id
                    replaced_count += 1
                    break

        # Check long_press
        long_press = button.get("long_press")
        if long_press and "entity_id" in long_press:
            for mapping in mappings:
                full_old_id = f"{old_integration_id}.{mapping['previous_entity_id']}"
                if long_press["entity_id"] == full_old_id:
                    full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                    _LOG.debug(
                        "  Replacing button %s long_press: %s -> %s",
                        button_name,
                        full_old_id,
                        full_new_id,
                    )
                    long_press["entity_id"] = full_new_id
                    replaced_count += 1
                    break

        # Check double_press
        double_press = button.get("double_press")
        if double_press and "entity_id" in double_press:
            for mapping in mappings:
                full_old_id = f"{old_integration_id}.{mapping['previous_entity_id']}"
                if double_press["entity_id"] == full_old_id:
                    full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                    _LOG.debug(
                        "  Replacing button %s double_press: %s -> %s",
                        button_name,
                        full_old_id,
                        full_new_id,
                    )
                    double_press["entity_id"] = full_new_id
                    replaced_count += 1
                    break

    # Replace in user_interface pages
    user_interface = options.get("user_interface", {})
    pages = user_interface.get("pages", [])
    for page in pages:
        page_name = page.get("name", "unknown")
        items = page.get("items", [])

        for item in items:
            # Handle command (can be string or object with entity_id)
            command = item.get("command")
            if command:
                if isinstance(command, str):
                    # Command is a direct entity_id string
                    for mapping in mappings:
                        full_old_id = (
                            f"{old_integration_id}.{mapping['previous_entity_id']}"
                        )
                        if command == full_old_id:
                            full_new_id = (
                                f"{new_integration_id}.{mapping['new_entity_id']}"
                            )
                            _LOG.debug(
                                '  Replacing page "%s" command: %s -> %s',
                                page_name,
                                full_old_id,
                                full_new_id,
                            )
                            item["command"] = full_new_id
                            replaced_count += 1
                            break
                elif isinstance(command, dict) and "entity_id" in command:
                    # Command is an object with entity_id
                    for mapping in mappings:
                        full_old_id = (
                            f"{old_integration_id}.{mapping['previous_entity_id']}"
                        )
                        if command["entity_id"] == full_old_id:
                            full_new_id = (
                                f"{new_integration_id}.{mapping['new_entity_id']}"
                            )
                            _LOG.debug(
                                '  Replacing page "%s" command.entity_id: %s -> %s',
                                page_name,
                                full_old_id,
                                full_new_id,
                            )
                            command["entity_id"] = full_new_id
                            replaced_count += 1
                            break

            # Handle media_player_id
            media_player_id = item.get("media_player_id")
            if media_player_id:
                for mapping in mappings:
                    full_old_id = (
                        f"{old_integration_id}.{mapping['previous_entity_id']}"
                    )
                    if media_player_id == full_old_id:
                        full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                        _LOG.debug(
                            '  Replacing page "%s" media_player_id: %s -> %s',
                            page_name,
                            full_old_id,
                            full_new_id,
                        )
                        item["media_player_id"] = full_new_id
                        replaced_count += 1
                        break

    # Replace in sequences (on/off)
    sequences = options.get("sequences", {})
    for seq_type, sequence_list in sequences.items():
        if not isinstance(sequence_list, list):
            continue

        for sequence in sequence_list:
            command = sequence.get("command")
            if command and isinstance(command, dict) and "entity_id" in command:
                for mapping in mappings:
                    full_old_id = (
                        f"{old_integration_id}.{mapping['previous_entity_id']}"
                    )
                    if command["entity_id"] == full_old_id:
                        full_new_id = f"{new_integration_id}.{mapping['new_entity_id']}"
                        _LOG.debug(
                            "  Replacing %s sequence: %s -> %s",
                            seq_type,
                            full_old_id,
                            full_new_id,
                        )
                        command["entity_id"] = full_new_id
                        replaced_count += 1
                        break

    return replaced_count


async def _update_activity_on_remote(
    session: Any,
    remote_url: str,
    activity: dict[str, Any],
    headers: dict[str, str],
    auth: Any,
) -> bool:
    """
    Update an activity on the Remote via API.

    Makes multiple API calls:
    1. PATCH activity (name, icon, entity_ids, sequences)
    2. PATCH each button mapping
    3. PATCH each UI page

    Returns True if all updates succeeded, False otherwise.
    """
    try:
        entity_id = activity.get("entity_id")
        if not entity_id:
            _LOG.error("Activity missing entity_id, cannot update")
            return False

        options = activity.get("options", {})

        # Build main activity update payload
        payload: dict[str, Any] = {
            "name": activity.get("name", ""),
            "options": {},
        }

        if activity.get("icon"):
            payload["icon"] = activity["icon"]

        # Add entity_ids from included_entities
        included_entities = options.get("included_entities", [])
        if included_entities:
            payload["options"]["entity_ids"] = [
                e["entity_id"] for e in included_entities
            ]

        # Add sequences
        if options.get("sequences"):
            payload["options"]["sequences"] = options["sequences"]

        # Update main activity
        activity_url = f"{remote_url}/api/activities/{entity_id}"
        async with session.patch(
            activity_url,
            json=payload,
            headers=headers,
            auth=auth,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            if response.status not in (200, 204):
                error_text = await response.text()
                _LOG.error(
                    "Failed to update activity %s: HTTP %d - %s",
                    entity_id,
                    response.status,
                    error_text,
                )
                return False

        _LOG.debug("Successfully updated activity %s", entity_id)

        # Update button mappings
        button_mapping = options.get("button_mapping", [])
        for button in button_mapping:
            # Only update if there are press actions defined
            if not any(
                button.get(press_type)
                for press_type in ("short_press", "long_press", "double_press")
            ):
                continue

            button_name = button.get("button")
            if not button_name:
                continue

            button_url = (
                f"{remote_url}/api/activities/{entity_id}/buttons/{button_name}"
            )
            async with session.patch(
                button_url,
                json=button,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status not in (200, 204):
                    _LOG.warning(
                        "Failed to update button %s: HTTP %d",
                        button_name,
                        response.status,
                    )
                    # Don't fail the whole migration for button update failures
                else:
                    _LOG.debug("Successfully updated button %s", button_name)

        # Update UI pages
        user_interface = options.get("user_interface", {})
        pages = user_interface.get("pages", [])
        for page in pages:
            page_id = page.get("page_id")
            if not page_id:
                continue

            page_url = f"{remote_url}/api/activities/{entity_id}/ui/pages/{page_id}"
            async with session.patch(
                page_url,
                json=page,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status not in (200, 204):
                    _LOG.warning(
                        "Failed to update page %s: HTTP %d",
                        page.get("name", page_id),
                        response.status,
                    )
                    # Don't fail the whole migration for page update failures
                else:
                    _LOG.debug(
                        "Successfully updated page %s", page.get("name", page_id)
                    )

        return True

    except Exception as err:  # pylint: disable=broad-except
        _LOG.error("Error updating activity on Remote: %s", err)
        return False


async def verify_migration(
    remote_url: str,
    expected_entity_ids: list[str],
    pin: str | None = None,
    api_key: str | None = None,
) -> bool:
    """
    Verify that migrated entities exist on the Remote.

    This optional helper checks if the new entity IDs are properly registered
    on the Remote after migration.

    :param remote_url: The Remote's base URL
    :param expected_entity_ids: List of new entity IDs to verify
    :param pin: Remote's web-configurator PIN
    :param api_key: Remote's API key
    :return: True if all entities are found, False otherwise

    Example:
        new_entity_ids = [m["new_entity_id"] for m in migration_data["entity_mappings"]]
        verified = await verify_migration(
            remote_url="http://192.168.1.100",
            expected_entity_ids=new_entity_ids,
            pin="1234"
        )
    """
    if not pin and not api_key:
        raise ValueError("Either pin or api_key must be provided for authentication")

    _LOG.info("Verifying %d migrated entities", len(expected_entity_ids))

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    auth = None
    if pin:
        auth = aiohttp.BasicAuth(login="web-configurator", password=pin)

    try:
        async with aiohttp.ClientSession() as session:
            # Get entities from Remote
            verification_endpoint = f"{remote_url}/api/intg/entities"

            async with session.get(
                verification_endpoint,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Parse entities from response
                    available_entities = data.get("entities", [])
                    available_ids = {
                        entity.get("entity_id") for entity in available_entities
                    }

                    missing = [
                        eid for eid in expected_entity_ids if eid not in available_ids
                    ]

                    if missing:
                        _LOG.warning("Missing entities after migration: %s", missing)
                        return False

                    _LOG.info("All migrated entities verified successfully")
                    return True
                else:
                    _LOG.error("Failed to verify entities: HTTP %d", response.status)
                    return False

    except aiohttp.ClientError as err:
        _LOG.error("Network error during verification: %s", err)
        return False
    except Exception as err:  # pylint: disable=broad-except
        _LOG.error("Unexpected error during verification: %s", err)
        return False


async def get_driver_version(
    remote_url: str,
    driver_id: str,
    pin: str | None = None,
    api_key: str | None = None,
) -> str | None:
    """
    Get the current version of a driver from the Remote.

    Fetches driver information from the Remote's API to retrieve the version string.
    This is useful for automatically determining the current version during migration
    without requiring the user to manually enter it.

    Authentication can be done via PIN (Basic Auth) or API key (Bearer token).
    One of `pin` or `api_key` must be provided.

    :param remote_url: The Remote's base URL (e.g., "http://192.168.1.100")
    :param driver_id: The driver/integration ID to query
    :param pin: Remote's web-configurator PIN for Basic Auth (username: "web-configurator")
    :param api_key: Remote's API key for Bearer token authentication
    :return: Version string if successful, None if failed
    :raises ValueError: If neither pin nor api_key is provided

    Example:
        version = await get_driver_version(
            remote_url="http://192.168.1.100",
            driver_id="mydriver",
            pin="1234"
        )
        print(f"Current version: {version}")  # e.g., "2.0.0"
    """
    if not pin and not api_key:
        raise ValueError("Either pin or api_key must be provided for authentication")

    _LOG.debug("Fetching driver version for %s from %s", driver_id, remote_url)

    try:
        # Setup authentication
        auth = None
        headers = {"Content-Type": "application/json"}

        if pin:
            auth = aiohttp.BasicAuth(login="web-configurator", password=pin)
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            # Fetch driver information
            driver_url = f"{remote_url}/api/intg/drivers/{driver_id}"
            async with session.get(
                driver_url,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    driver_data = await response.json()
                    version = driver_data.get("version")
                    if version:
                        _LOG.info("Retrieved driver version: %s", version)
                        return version
                    else:
                        _LOG.warning("Driver data does not contain version field")
                        return None
                else:
                    _LOG.error("Failed to fetch driver info: HTTP %d", response.status)
                    return None

    except aiohttp.ClientError as err:
        _LOG.error("Network error fetching driver version: %s", err)
        return None
    except Exception as err:  # pylint: disable=broad-except
        _LOG.error("Unexpected error fetching driver version: %s", err)
        return None
