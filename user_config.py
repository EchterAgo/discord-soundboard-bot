"""User configuration storage for soundboard."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

_log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / "user_configs"


def ensure_config_dir():
    """Ensure the user configs directory exists."""
    CONFIG_DIR.mkdir(exist_ok=True)


def get_user_config_path(user_id: str) -> Path:
    """Get the path to a user's config file."""
    return CONFIG_DIR / f"{user_id}.json"


def get_default_config() -> Dict[str, Any]:
    """Get default configuration for a new user.

    Tries to load from Default.json if it exists, otherwise returns minimal config.
    """
    ensure_config_dir()
    default_path = CONFIG_DIR / "Default.json"

    if default_path.exists():
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                _log.info("Loaded default config from Default.json")
                return config
        except Exception as e:
            _log.error(f"Failed to load Default.json: {e}")

    # Fallback to minimal config
    return {
        "version": 1,
        "username": "User",
        "buttons": [],
        "grid_size": {"cols": 6, "rows": 0},  # 0 rows means auto
        "recent_sounds": [],
        "favorites": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


def load_user_config(user_id: str) -> Dict[str, Any]:
    """Load user configuration from JSON file.

    Args:
        user_id: User identifier (username or hash)

    Returns:
        User configuration dictionary
    """
    ensure_config_dir()
    config_path = get_user_config_path(user_id)

    if not config_path.exists():
        _log.info(f"Creating new config for user {user_id}")
        config = get_default_config()
        config["username"] = user_id
        save_user_config(user_id, config)
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            _log.debug(f"Loaded config for user {user_id}")
            return config
    except Exception as e:
        _log.error(f"Failed to load config for user {user_id}: {e}")
        return get_default_config()


def save_user_config(user_id: str, config: Dict[str, Any]) -> bool:
    """Save user configuration to JSON file.

    Args:
        user_id: User identifier
        config: Configuration dictionary to save

    Returns:
        True if successful, False otherwise
    """
    ensure_config_dir()
    config_path = get_user_config_path(user_id)

    try:
        # Update timestamp
        config["updated_at"] = datetime.utcnow().isoformat()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        _log.debug(f"Saved config for user {user_id}")
        return True
    except Exception as e:
        _log.error(f"Failed to save config for user {user_id}: {e}")
        return False


def add_recent_sound(user_id: str, sound_path: str, max_recent: int = 20) -> None:
    """Add a sound to user's recent sounds list.

    Args:
        user_id: User identifier
        sound_path: Path to the sound file
        max_recent: Maximum number of recent sounds to keep
    """
    config = load_user_config(user_id)

    # Remove if already exists
    if sound_path in config["recent_sounds"]:
        config["recent_sounds"].remove(sound_path)

    # Add to front
    config["recent_sounds"].insert(0, sound_path)

    # Trim to max size
    config["recent_sounds"] = config["recent_sounds"][:max_recent]

    save_user_config(user_id, config)


def delete_user_config(user_id: str) -> bool:
    """Delete user configuration file.

    Args:
        user_id: User identifier

    Returns:
        True if successful, False otherwise
    """
    config_path = get_user_config_path(user_id)

    try:
        if config_path.exists():
            config_path.unlink()
            _log.info(f"Deleted config for user {user_id}")
            return True
        return False
    except Exception as e:
        _log.error(f"Failed to delete config for user {user_id}: {e}")
        return False


def list_all_users() -> list:
    """List all users who have configurations.

    Returns:
        List of user IDs
    """
    ensure_config_dir()
    return [f.stem for f in CONFIG_DIR.glob("*.json")]
