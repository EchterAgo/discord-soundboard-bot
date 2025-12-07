"""JSON-RPC server for Discord Soundboard Bot."""

import logging
import time
import json
import asyncio
from typing import Set
from pathlib import Path

import aiohttp
from discord.ext import commands
from jsonrpcserver import (
    method,
    Result,
    Success,
    InvalidParams,
    Error,
)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils import find_files
from config import CONFIG_AUDIO_BASE_DIR
import user_config


_log = logging.getLogger(__name__)

# WebSocket connections registry
websocket_connections: Set[aiohttp.web.WebSocketResponse] = set()

# File watcher
file_observer = None
event_loop = None


class AudioFileHandler(FileSystemEventHandler):
    """Handler for audio file system events."""
    
    def __init__(self, loop):
        self.loop = loop
        self.debounce_timer = None
    
    def _schedule_broadcast(self):
        """Schedule a broadcast after a short delay to debounce rapid changes."""
        if self.debounce_timer:
            self.debounce_timer.cancel()
        
        async def do_broadcast():
            await asyncio.sleep(0.5)  # Debounce delay
            await broadcast_file_list_update()
        
        self.debounce_timer = asyncio.run_coroutine_threadsafe(
            do_broadcast(), self.loop
        )
    
    def on_created(self, event):
        if not event.is_directory:
            _log.info(f"Audio file created: {event.src_path}")
            self._schedule_broadcast()
    
    def on_deleted(self, event):
        if not event.is_directory:
            _log.info(f"Audio file deleted: {event.src_path}")
            self._schedule_broadcast()
    
    def on_moved(self, event):
        if not event.is_directory:
            _log.info(f"Audio file moved: {event.src_path} -> {event.dest_path}")
            self._schedule_broadcast()


async def broadcast_file_list_update():
    """Broadcast file list update to all connected WebSocket clients."""
    if not websocket_connections:
        return
    
    try:
        files = list(find_files(CONFIG_AUDIO_BASE_DIR))
        message = json.dumps({
            "type": "file_list_update",
            "files": files
        })
        
        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send file list update to WebSocket client: {e}")
                disconnected.add(ws)
        
        # Remove disconnected clients
        websocket_connections.difference_update(disconnected)
        
        _log.info(f"Broadcasted file list update to {len(websocket_connections)} clients")
        
    except Exception as e:
        _log.error(f"Error broadcasting file list update: {e}", exc_info=True)


def start_file_watcher(loop):
    """Start watching the audio directory for changes."""
    global file_observer, event_loop
    
    event_loop = loop
    event_handler = AudioFileHandler(loop)
    file_observer = Observer()
    
    # Watch the audio directory recursively
    file_observer.schedule(event_handler, CONFIG_AUDIO_BASE_DIR, recursive=True)
    file_observer.start()
    
    _log.info(f"Started watching audio directory: {CONFIG_AUDIO_BASE_DIR}")


def stop_file_watcher():
    """Stop the file watcher."""
    global file_observer
    
    if file_observer:
        file_observer.stop()
        file_observer.join()
        file_observer = None
        _log.info("Stopped file watcher")


def _build_queue_status(audio_player, guild):
    """Build queue status dictionary from audio player state.
    
    Args:
        audio_player: AudioPlayer cog instance
        guild: Discord guild object
        
    Returns:
        Dictionary containing queue status
    """
    status = {
        "is_playing": audio_player.is_processing,
        "connected": guild.voice_client is not None,
        "connected_users": len(websocket_connections),
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
            stream_info = {
                "user_id": user_id,
                "user_name": stream.user_name,
                "filepath": stream.filepath,
                "finished": stream.finished
            }
            # Add progress percentage if available
            progress = stream.get_progress_percentage()
            if progress is not None:
                stream_info["progress"] = progress
            status["active_streams"].append(stream_info)
    
    return status


async def broadcast_queue_update(bot, channelid):
    """Broadcast queue status update to all connected WebSocket clients."""
    if not websocket_connections:
        return
    
    try:
        channel = bot.get_channel(int(channelid))
        if not channel:
            return

        guild = channel.guild
        audio_player = bot.get_cog("AudioPlayer")
        if not audio_player:
            return

        status = _build_queue_status(audio_player, guild)
        status["type"] = "queue_update"  # Add type for WebSocket message
        
        # Broadcast to all connected clients
        message = json.dumps(status)
        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send to WebSocket client: {e}")
                disconnected.add(ws)
        
        # Remove disconnected clients
        websocket_connections.difference_update(disconnected)
        
    except Exception as e:
        _log.error(f"Error broadcasting queue update: {e}", exc_info=True)


async def broadcast_config_update(user_name: str):
    """Broadcast config change notification to all connected WebSocket clients.
    
    Clients will receive the username and should fetch the config themselves if needed.
    """
    if not websocket_connections:
        return
    
    try:
        message = json.dumps({
            "type": "config_update",
            "user_name": user_name
        })
        
        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send config update to WebSocket client: {e}")
                disconnected.add(ws)
        
        # Remove disconnected clients
        websocket_connections.difference_update(disconnected)
        
        _log.info(f"Broadcasted config update notification for {user_name} to {len(websocket_connections)} clients")
        
    except Exception as e:
        _log.error(f"Error broadcasting config update: {e}", exc_info=True)


@method(name="list")
async def jsonrpc_list(context) -> Result:
    """List all available sound files."""
    return Success(list(find_files(CONFIG_AUDIO_BASE_DIR)))


@method(name="search")
async def jsonrpc_search(context, query) -> Result:
    """Search for sound files matching a query."""
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
    start_time = time.time()
    
    try:
        _log.debug(f"[RPC] play request started - user: {user_name}, query: {query}, interrupt: {interrupt}, play_next: {play_next}")
        
        bot = context.app["bot"]

        channel = bot.get_channel(int(channelid))
        if not channel:
            _log.warning(f"[RPC] play request failed - channel not found: {channelid}")
            return InvalidParams("Channel not found")

        guild = channel.guild

        audio_player = bot.get_cog("AudioPlayer")
        if not audio_player:
            _log.error("[RPC] play request failed - AudioPlayer cog not found")
            return Error(1, "Audio player cog not found")

        # Ensure bot is connected to voice channel
        vc_start = time.time()
        vc = await audio_player.ensure_voice_connection(guild, channel)
        vc_time = (time.time() - vc_start) * 1000
        _log.debug(f"[RPC] Voice connection ensured in {vc_time:.2f}ms")
        
        if not vc:
            _log.error("[RPC] play request failed - could not establish voice connection")
            return Error(1, "Failed to establish voice connection")

        # Generate user_id from user_name hash for per-user queuing
        user_id = hash(user_name) & 0x7FFFFFFF  # Positive 32-bit integer

        # Create a simple context object for queue_sound
        class RpcContext:
            voice_client = vc

        queue_start = time.time()
        await audio_player.queue_sound(
            RpcContext(), 
            query, 
            user_id=user_id,
            after=None,
            interrupt=interrupt,
            play_next=play_next,
            user_name=user_name
        )
        queue_time = (time.time() - queue_start) * 1000
        _log.debug(f"[RPC] Sound queued in {queue_time:.2f}ms")
        
        # Track in recent sounds and broadcast config update
        user_config.add_recent_sound(user_name, query)
        await broadcast_config_update(user_name)
        
        # Broadcast queue update to WebSocket clients
        await broadcast_queue_update(bot, channelid)
        
        total_time = (time.time() - start_time) * 1000
        _log.debug(f"[RPC] play request completed successfully in {total_time:.2f}ms")
        
        return Success("Playback successful")
        
    except commands.CommandError as e:
        total_time = (time.time() - start_time) * 1000
        _log.error(f"[RPC] CommandError in jsonrpc_play after {total_time:.2f}ms: {e}", exc_info=True)
        return Error(1, str(e))
    except Exception as e:
        total_time = (time.time() - start_time) * 1000
        _log.error(f"[RPC] Unexpected error in jsonrpc_play after {total_time:.2f}ms: {e}", exc_info=True)
        return Error(1, f"Unexpected error: {str(e)}")


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
    
    # Broadcast queue update to WebSocket clients
    await broadcast_queue_update(bot, channelid)
    
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

    status = _build_queue_status(audio_player, guild)
    
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
    
    # Broadcast queue update to WebSocket clients
    await broadcast_queue_update(bot, channelid)
    
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
            # Broadcast config update notification to all connected clients
            await broadcast_config_update(user_name)
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
        # Broadcast config update notification to all connected clients
        await broadcast_config_update(user_name)
        return Success(default_config)
    except Exception as e:
        _log.error(f"Failed to reset user config for {user_name}: {e}", exc_info=True)
        return Error(1, f"Failed to reset user config: {str(e)}")


@method(name="message")
async def jsonrpc_message(context, channelid, content) -> Result:
    """Send a message to a Discord channel.
    
    Args:
        channelid: Channel ID to send message to
        content: Message content
        
    Returns:
        Success or error result
    """
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    await channel.send(content=content)

    return Success("Message sent successfully")


async def handle_websocket(request):
    """Handle WebSocket connections for real-time updates and RPC commands."""
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)
    
    websocket_connections.add(ws)
    _log.info(f"WebSocket client connected. Total connections: {len(websocket_connections)}")
    
    bot = request.app["bot"]
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    # Handle JSON-RPC over WebSocket
                    if "method" in data:
                        from jsonrpcserver import async_dispatch
                        response = await async_dispatch(msg.data, context=request)
                        await ws.send_str(response)
                    
                except json.JSONDecodeError:
                    await ws.send_json({"error": "Invalid JSON"})
                except Exception as e:
                    _log.error(f"Error handling WebSocket message: {e}", exc_info=True)
                    await ws.send_json({"error": str(e)})
                    
            elif msg.type == aiohttp.WSMsgType.ERROR:
                _log.error(f"WebSocket connection closed with exception: {ws.exception()}")
    
    finally:
        websocket_connections.discard(ws)
        _log.info(f"WebSocket client disconnected. Total connections: {len(websocket_connections)}")
    
    return ws
