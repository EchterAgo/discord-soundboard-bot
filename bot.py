import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

import aiohttp
import aiohttp.web
import aiohttp.resolver

import matplotlib

# Use the matplotlib Agg backend because we don't want GUI
# This needs to happen before any cog imports
matplotlib.use("Agg")

from jsonrpcserver import (
    method,
    Result,
    Success,
    InvalidParams,
    Error,
    async_dispatch,
)


from utils import find_files
from config import CONFIG_DISCORD_TOKEN, CONFIG_AUDIO_BASE_DIR
from erwerbregeln import RegelnDesErwerbs
from audioplayer import AudioPlayer
from controller import Controller
from llm import LLM
from text2image import TextToImage
from magischekugel import MagischeKugel
from bloedsinn import Bloedsinn
from stats import Statistics
import user_config


BOT_BASE_DIR = Path(__file__).parent.resolve()

_log = logging.getLogger(__name__)


# It seems there is a bug with aiodns / pycares that sometimes makes DNS queries
# never return, not even when the timeout is reached.
# https://github.com/aio-libs/aiodns/issues/122
# https://github.com/saghul/pycares/issues/197
aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver


async def wait_for_voice_connection(voice_client, max_wait: float = 5.0) -> bool:
    """Wait for voice client to be connected.
    
    Args:
        voice_client: The voice client to wait for
        max_wait: Maximum time to wait in seconds
        
    Returns:
        True if connected, False if timeout
    """
    wait_time = 0.0
    while not voice_client.is_connected() and wait_time < max_wait:
        await asyncio.sleep(0.2)
        wait_time += 0.2
    return voice_client.is_connected()


class MyBot(commands.Bot):
    async def setup_hook(self):
        # This is called when the bot is starting up
        _log.info("Bot setup hook called")

    async def on_ready(self):
        _log.info(f"We have logged in as {self.user} (ID: {self.user.id})")
        await self.tree.sync()

    async def on_connect(self):
        _log.info(f"Connected to server")


async def http_hello(request):
    return aiohttp.web.Response(text="Hello, world")


@method(name="list")
async def jsonrpc_list(context) -> Result:
    return Success(list(find_files(CONFIG_AUDIO_BASE_DIR)))


@method(name="search")
async def jsonrpc_search(context, query) -> Result:
    files = list(find_files(CONFIG_AUDIO_BASE_DIR))

    files = [f for f in files if query in f]

    return Success(files)


@method(name="play")
async def jsonrpc_play(context, channelid, query, interrupt=False, play_next=False, user_name="RPC") -> Result:
    """Play a sound via JSON-RPC.
    
    Args:
        channelid: Voice channel ID to connect to
        query: Sound file path to play
        interrupt: If True, interrupt current playback (default: False)
        play_next: If True, play after current sound (default: False, adds to end of queue)
        user_name: Display name for logging (default: "RPC")
    """
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild

    audio_player = bot.get_cog("AudioPlayer")
    if not audio_player:
        return Error(1, "Audio player cog not found")

    try:
        # Ensure bot is connected to voice channel
        vc = await audio_player.ensure_voice_connection(guild, channel)
        if not vc:
            return Error(1, "Failed to establish voice connection")

        # Generate user_id from user_name hash for per-user queuing
        user_id = hash(user_name) & 0x7FFFFFFF  # Positive 32-bit integer

        # Create a simple context object for queue_sound
        class RpcContext:
            voice_client = vc

        await audio_player.queue_sound(
            RpcContext(), 
            query, 
            user_id=user_id,
            after=None,
            interrupt=interrupt,
            play_next=play_next,
            user_name=user_name
        )
        
        # Track in recent sounds
        user_config.add_recent_sound(user_name, query)
        
    except commands.CommandError as e:
        _log.error(f"CommandError in jsonrpc_play: {e}", exc_info=True)
        return Error(1, str(e))
    except Exception as e:
        _log.error(f"Unexpected error in jsonrpc_play: {e}", exc_info=True)
        return Error(1, f"Unexpected error: {str(e)}")

    return Success("Playback successful")


@method(name="stop")
async def jsonrpc_stop(context, channelid, user_name="RPC") -> Result:
    """Stop playback and clear queue via JSON-RPC.
    
    Args:
        channelid: Voice channel ID to stop playback in
        user_name: Display name for logging (default: "RPC")
    """
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild
    
    audio_player = bot.get_cog("AudioPlayer")
    if not audio_player:
        return Error(1, "Audio player cog not found")

    if not guild.voice_client:
        return Success("Not connected to voice")
    
    result = audio_player.stop_playback(guild.voice_client, user_name=user_name)
    
    if result['stopped'] and result['queue_cleared'] > 0:
        return Success(f"Playback stopped and cleared {result['queue_cleared']} queued items")
    elif result['stopped']:
        return Success("Playback stopped")
    elif result['queue_cleared'] > 0:
        return Success(f"Cleared {result['queue_cleared']} queued items")
    else:
        return Success("No playback to stop")


@method(name="queue_status")
async def jsonrpc_queue_status(context, channelid) -> Result:
    """Get current queue status via JSON-RPC.
    
    Args:
        channelid: Voice channel ID to check queue for
    
    Returns:
        Queue status including all user queues and currently playing streams
    """
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild
    
    audio_player = bot.get_cog("AudioPlayer")
    if not audio_player:
        return Error(1, "Audio player cog not found")

    status = {
        "is_playing": audio_player.is_processing,
        "connected": guild.voice_client is not None,
        "user_queues": [],
        "active_streams": [],
        "total_queued": 0
    }
    
    # Get user queues
    for user_id, queue in audio_player.user_queues.items():
        if queue:
            queue_items = [{"query": item.query, "user_name": item.user_name} for item in queue]
            status["user_queues"].append({
                "user_id": user_id,
                "user_name": queue[0].user_name if queue else "Unknown",
                "count": len(queue),
                "items": queue_items
            })
            status["total_queued"] += len(queue)
    
    # Get active streams
    if audio_player.mixed_source:
        for user_id, stream in audio_player.mixed_source.streams.items():
            status["active_streams"].append({
                "user_id": user_id,
                "user_name": stream.user_name,
                "filepath": stream.filepath,
                "finished": stream.finished
            })
    
    return Success(status)


@method(name="remove_queue_item")
async def jsonrpc_remove_queue_item(context, channelid, user_id, item_index) -> Result:
    """Remove a specific item from a user's queue via JSON-RPC.
    
    Args:
        channelid: Voice channel ID
        user_id: User ID whose queue to modify
        item_index: Index of the item to remove (0-based)
    
    Returns:
        Success or error result
    """
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild
    
    audio_player = bot.get_cog("AudioPlayer")
    if not audio_player:
        return Error(1, "Audio player cog not found")

    user_id = int(user_id)
    item_index = int(item_index)
    
    # Check if user has a queue
    if user_id not in audio_player.user_queues:
        return Error(1, "User has no queued items")
    
    queue = audio_player.user_queues[user_id]
    
    # Validate index
    if item_index < 0 or item_index >= len(queue):
        return Error(1, f"Invalid item index: {item_index}")
    
    # Convert deque to list, remove item, convert back
    queue_list = list(queue)
    removed_item = queue_list.pop(item_index)
    audio_player.user_queues[user_id].clear()
    audio_player.user_queues[user_id].extend(queue_list)
    
    # Clean up empty queue
    if not audio_player.user_queues[user_id]:
        del audio_player.user_queues[user_id]
    
    _log.info(f"Removed queue item '{removed_item.query}' at index {item_index} for user {user_id}")
    
    return Success(f"Removed '{removed_item.query}' from queue")


@method(name="get_user_config")
async def jsonrpc_get_user_config(context, user_name: str) -> Result:
    """Get user configuration via JSON-RPC.
    
    Args:
        user_name: User identifier (username)
        
    Returns:
        User configuration dictionary
    """
    try:
        config = user_config.load_user_config(user_name)
        return Success(config)
    except Exception as e:
        _log.error(f"Failed to get user config for {user_name}: {e}", exc_info=True)
        return Error(1, f"Failed to load user config: {str(e)}")


@method(name="save_user_config")
async def jsonrpc_save_user_config(context, user_name: str, config: dict) -> Result:
    """Save user configuration via JSON-RPC.
    
    Args:
        user_name: User identifier (username)
        config: Configuration dictionary to save
        
    Returns:
        Success or error result
    """
    try:
        # Validate required fields
        if "buttons" not in config or "grid_size" not in config:
            return InvalidParams("Config must include 'buttons' and 'grid_size'")
        
        success = user_config.save_user_config(user_name, config)
        if success:
            return Success("Configuration saved successfully")
        else:
            return Error(1, "Failed to save configuration")
    except Exception as e:
        _log.error(f"Failed to save user config for {user_name}: {e}", exc_info=True)
        return Error(1, f"Failed to save user config: {str(e)}")


@method(name="add_recent_sound")
async def jsonrpc_add_recent_sound(context, user_name: str, sound_path: str) -> Result:
    """Add a sound to user's recent sounds list.
    
    Args:
        user_name: User identifier
        sound_path: Path to the sound file
        
    Returns:
        Success result
    """
    try:
        user_config.add_recent_sound(user_name, sound_path)
        return Success("Added to recent sounds")
    except Exception as e:
        _log.error(f"Failed to add recent sound for {user_name}: {e}", exc_info=True)
        return Error(1, f"Failed to add recent sound: {str(e)}")


@method(name="reset_user_config")
async def jsonrpc_reset_user_config(context, user_name: str) -> Result:
    """Reset user configuration to defaults.
    
    Args:
        user_name: User identifier
        
    Returns:
        Success or error result
    """
    try:
        user_config.delete_user_config(user_name)
        default_config = user_config.get_default_config()
        default_config["username"] = user_name
        user_config.save_user_config(user_name, default_config)
        return Success(default_config)
    except Exception as e:
        _log.error(f"Failed to reset user config for {user_name}: {e}", exc_info=True)
        return Error(1, f"Failed to reset user config: {str(e)}")


@method(name="message")
async def jsonrpc_message(context, channelid, content) -> Result:
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    await channel.send(content=content)

    return Success("Playback successful")


async def http_handle_rpc(request):
    return aiohttp.web.Response(
        text=await async_dispatch(await request.text(), context=request),
        content_type="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


async def http_handle_rpc_options(request):
    return aiohttp.web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


async def start_webserver(bot: commands.Bot):
    app = aiohttp.web.Application()

    app["bot"] = bot  # to get the bot in handlers

    app.router.add_get("/", http_hello)
    app.router.add_post("/rpc", http_handle_rpc)
    app.router.add_options("/rpc", http_handle_rpc_options)
    app.router.add_static("/soundboard", BOT_BASE_DIR / "web")
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, port=28914)
    await site.start()


async def start_discord_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.presences = True

    bot = MyBot(
        command_prefix=commands.when_mentioned_or("!"),
        description="ObstNudler",
        intents=intents,
    )

    await bot.add_cog(AudioPlayer(bot))
    await bot.add_cog(Controller(bot))
    await bot.add_cog(RegelnDesErwerbs(bot))
    await bot.add_cog(LLM(bot))
    await bot.add_cog(TextToImage(bot))
    await bot.add_cog(MagischeKugel(bot))
    await bot.add_cog(Bloedsinn(bot))
    await bot.add_cog(Statistics(bot))

    asyncio.create_task(start_webserver(bot))

    if not CONFIG_DISCORD_TOKEN:
        raise ValueError("CONFIG_DISCORD_TOKEN must be set and cannot be None")

    await bot.start(CONFIG_DISCORD_TOKEN)


async def main():
    logging.basicConfig(level=logging.INFO)
    #logging.basicConfig(level=logging.DEBUG)
    
    # Disable verbose logging for ffmpeg and aiohttp
    logging.getLogger('discord.player').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

    await start_discord_bot()


if __name__ == "__main__":
    asyncio.run(main())

# https://discord.com/api/oauth2/authorize?client_id=1085103559244251179&permissions=2048&scope=bot
