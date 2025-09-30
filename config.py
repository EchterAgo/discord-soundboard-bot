import os
from pathlib import Path


NO_DEFAULT = object()


def get_setting(name: str, default: str | None = NO_DEFAULT) -> str | None:
    if res := os.environ.get(name):
        return res
    if default is NO_DEFAULT:
        raise KeyError(f"Config variable {name} not found in environment and no default value!")
    return default


CONFIG_DISCORD_TOKEN = get_setting("CONFIG_DISCORD_TOKEN")
if not CONFIG_DISCORD_TOKEN:
    raise RuntimeError("No Discord token specified")

CONFIG_AUDIO_BASE_DIR = Path(get_setting("CONFIG_AUDIO_BASE_DIR"))
CONFIG_NANOGPT_BASE_URL = get_setting("CONFIG_NANOGPT_BASE_URL", "https://nano-gpt.com/api/v1")
CONFIG_NANOGPT_API_KEY = get_setting("CONFIG_NANOGPT_API_KEY")
