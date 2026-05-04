"""JSON-RPC server for Discord Soundboard Bot."""

import logging
import time
import json
import asyncio
import socket
import math
from typing import Dict

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

from utils import find_files, json_dumps_strict
from config import CONFIG_AUDIO_BASE_DIR
import user_config
from audioplayer_stats import audioplayer_stats


_log = logging.getLogger(__name__)

# WebSocket connections registry - maps WebSocket to user info dict {"username": str, "ip": str, "hostname": str, "last_ping": float, "registered": bool}
websocket_connections: Dict = {}

# File watcher
file_observer = None
event_loop = None

# Periodic broadcast task
periodic_broadcast_task = None


def get_hostname_from_ip(ip: str) -> str:
    """Get hostname from IP address using reverse DNS lookup.

    Args:
        ip: IP address string

    Returns:
        Hostname if found, otherwise returns the IP address
    """
    try:
        # Try reverse DNS lookup with a short timeout
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout):
        # If lookup fails, return the IP as-is
        return ip


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

        self.debounce_timer = asyncio.run_coroutine_threadsafe(do_broadcast(), self.loop)

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
        message = json_dumps_strict({"type": "file_list_update", "files": files})

        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send file list update to WebSocket client: {e}")
                disconnected.add(ws)

        # Remove disconnected clients
        for ws in disconnected:
            websocket_connections.pop(ws, None)

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
    file_observer.schedule(event_handler, str(CONFIG_AUDIO_BASE_DIR), recursive=True)
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


async def periodic_queue_broadcast(bot, channel_id, interval=5.0):
    """Periodically broadcast queue status to keep UI updated with ping/clock offset data.
    
    Args:
        bot: Discord bot instance
        channel_id: Voice channel ID
        interval: Broadcast interval in seconds (default: 5.0)
    """
    while True:
        try:
            await asyncio.sleep(interval)
            # Only broadcast if there are connected clients
            if websocket_connections:
                await broadcast_queue_update(bot, channel_id)
        except asyncio.CancelledError:
            _log.info("Periodic broadcast task cancelled")
            break
        except Exception as e:
            _log.error(f"Error in periodic broadcast: {e}", exc_info=True)


def start_periodic_broadcast(bot, channel_id, interval=5.0):
    """Start periodic queue status broadcasts.
    
    Args:
        bot: Discord bot instance
        channel_id: Voice channel ID
        interval: Broadcast interval in seconds (default: 5.0)
    """
    global periodic_broadcast_task
    
    if periodic_broadcast_task is None or periodic_broadcast_task.done():
        periodic_broadcast_task = asyncio.create_task(periodic_queue_broadcast(bot, channel_id, interval))
        _log.info(f"Started periodic queue status broadcasts (interval: {interval}s)")


def stop_periodic_broadcast():
    """Stop periodic queue status broadcasts."""
    global periodic_broadcast_task
    
    if periodic_broadcast_task and not periodic_broadcast_task.done():
        periodic_broadcast_task.cancel()
        periodic_broadcast_task = None
        _log.info("Stopped periodic queue status broadcasts")


def _build_queue_status(audio_player, guild):
    """Build queue status dictionary from audio player state.

    Args:
        audio_player: AudioPlayer cog instance
        guild: Discord guild object

    Returns:
        Dictionary containing queue status
    """
    # Filter out unregistered connections (debug windows, etc.) from the connection list
    registered_connections = [conn for conn in websocket_connections.values() if conn.get("registered", False)]
    
    status = {
        "is_playing": audio_player.is_processing,
        "connected": guild.voice_client is not None,
        "connected_users": len(registered_connections),
        "connected_user_list": registered_connections,
        "user_queues": [],
        "active_streams": [],
        "total_queued": 0,
        "average_latency": None,
        "voice_server_endpoint": None,
    }

    # Get voice client latency and endpoint if connected
    if guild.voice_client is not None:
        try:
            # average_latency is in seconds, convert to ms and round to 1 decimal
            latency_ms = guild.voice_client.average_latency * 1000
            # Only set if finite (not inf or nan)
            if math.isfinite(latency_ms):
                status["average_latency"] = round(latency_ms, 1)
            
            # Get voice server endpoint if available
            if hasattr(guild.voice_client, 'endpoint') and guild.voice_client.endpoint:
                status["voice_server_endpoint"] = guild.voice_client.endpoint
        except Exception:
            pass

    # Get user queues
    for user_id, queue in audio_player.user_queues.items():
        if queue:
            queue_items = [{"query": item.query, "user_name": item.user_name} for item in queue]
            status["user_queues"].append(
                {
                    "user_id": user_id,
                    "user_name": queue[0].user_name if queue else "Unknown",
                    "count": len(queue),
                    "items": queue_items,
                }
            )
            status["total_queued"] += len(queue)

    # Get active streams
    if audio_player.mixed_source:
        for user_id, stream in audio_player.mixed_source.streams.items():
            stream_info = {
                "user_id": user_id,
                "user_name": stream.user_name,
                "filepath": stream.filepath,
                "finished": stream.finished,
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
        try:
            message = json_dumps_strict(status)  # Enforce strict JSON and sanitize non-finite numbers
        except (ValueError, TypeError) as e:
            _log.error(f"Failed to serialize queue status to JSON: {e}. Status data: {status}")
            return
            
        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send to WebSocket client: {e}")
                disconnected.add(ws)

        # Remove disconnected clients
        for ws in disconnected:
            websocket_connections.pop(ws, None)

    except Exception as e:
        _log.error(f"Error broadcasting queue update: {e}", exc_info=True)


async def broadcast_config_update(user_name: str):
    """Broadcast config change notification to all connected WebSocket clients.

    Clients will receive the username and should fetch the config themselves if needed.
    """
    if not websocket_connections:
        return

    try:
        message = json_dumps_strict({"type": "config_update", "user_name": user_name})

        disconnected = set()
        for ws in websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                _log.warning(f"Failed to send config update to WebSocket client: {e}")
                disconnected.add(ws)

        # Remove disconnected clients
        for ws in disconnected:
            websocket_connections.pop(ws, None)

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
async def jsonrpc_play(
    context,
    channelid,
    query,
    interrupt=False,
    play_next=False,
    user_name="RPC",
    audio_filters=None,
    request_timestamp=None,
) -> Result:
    """Play a sound via JSON-RPC.

    Args:
        channelid: Voice channel ID to connect to
        query: Sound file path to play
        interrupt: If True, interrupt current playback (default: False)
        play_next: If True, play after current sound (default: False, adds to end of queue)
        user_name: Display name for logging (default: "RPC")
        audio_filters: Dict containing volume_boost and audio filter settings (default: None)
        request_timestamp: Timestamp when the request was initiated (for latency tracking, default: None)
    """
    start_time = time.time()

    # Extract volume_boost from audio_filters for logging
    audio_filters = audio_filters or {}
    volume_boost = audio_filters.get("volume_boost", 1.0)

    try:
        _log.debug(
            f"[RPC] play request started - user: {user_name}, query: {query}, interrupt: {interrupt}, play_next: {play_next}, volume: {volume_boost}x"
        )

        bot = context["app"]["bot"]

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
        
        # Use both client and server timestamps:
        # - client timestamp (if provided and adjusted for clock offset) for end-to-end latency
        # - server timestamp for intermediate pipeline measurements to avoid clock skew
        server_request_timestamp = queue_start

        await audio_player.queue_sound(
            RpcContext(),
            query,
            user_id=user_id,
            after=None,
            interrupt=interrupt,
            play_next=play_next,
            user_name=user_name,
            volume_boost=volume_boost,
            audio_filters=audio_filters,
            request_timestamp=server_request_timestamp,
            client_request_timestamp=request_timestamp,  # Client timestamp adjusted for clock offset
        )
        queue_time = (time.time() - queue_start) * 1000
        _log.debug(f"[RPC] Sound queued in {queue_time:.2f}ms")

        # Track in recent sounds and broadcast config update
        user_config.add_recent_sound(user_name, query)
        await broadcast_config_update(user_name)

        # Queue update will be broadcast automatically via debounced callback
        # (removed redundant broadcast_queue_update call here)

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
    bot = context["app"]["bot"]

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

    if result["stopped"] and result["queue_cleared"] > 0:
        return Success(f"Playback stopped and cleared {result['queue_cleared']} queued items")
    elif result["stopped"]:
        return Success("Playback stopped")
    elif result["queue_cleared"] > 0:
        return Success(f"Cleared {result['queue_cleared']} queued items")
    else:
        return Success("No playback to stop")


@method(name="stop")
async def jsonrpc_stop(context, channelid, user_name="RPC") -> Result:
    """Stop playback and clear queue via JSON-RPC.

    Args:
        channelid: Voice channel ID to stop playback in
        user_name: Display name for logging (default: "RPC")
    """
    bot = context["app"]["bot"]

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

    if result["stopped"] and result["queue_cleared"] > 0:
        return Success(f"Playback stopped and cleared {result['queue_cleared']} queued items")
    elif result["stopped"]:
        return Success("Playback stopped")
    elif result["queue_cleared"] > 0:
        return Success(f"Cleared {result['queue_cleared']} queued items")
    else:
        return Success("No playback to stop")


@method(name="skip")
async def jsonrpc_skip(context, channelid, user_name="RPC") -> Result:
    """Skip current sound for the user and play the next one via JSON-RPC.

    Args:
        channelid: Voice channel ID to skip on
        user_name: Display name for logging (default: "RPC")
    """
    bot = context["app"]["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild

    audio_player = bot.get_cog("AudioPlayer")
    if not audio_player:
        return Error(1, "Audio player cog not found")

    if not guild.voice_client:
        return Success("Not connected to voice")

    # Generate user_id from user_name hash for per-user queuing
    user_id = hash(user_name) & 0x7FFFFFFF  # Positive 32-bit integer

    result = audio_player.skip_current(guild.voice_client, user_id=user_id, user_name=user_name)

    # Broadcast queue update to WebSocket clients
    await broadcast_queue_update(bot, channelid)

    if result["skipped"]:
        if result["playing_next"]:
            return Success("Skipped current sound, playing next")
        else:
            return Success("Skipped current sound")
    else:
        return Success("Nothing playing to skip")


@method(name="queue_status")
async def jsonrpc_queue_status(context, channelid) -> Result:
    """Get current queue status via JSON-RPC.

    Args:
        channelid: Voice channel ID to check queue for

    Returns:
        Queue status including all user queues and currently playing streams
    """
    bot = context["app"]["bot"]

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
    bot = context["app"]["bot"]

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
    bot = context["app"]["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    await channel.send(content=content)

    return Success("Message sent successfully")


@method(name="update_ping")
async def jsonrpc_update_ping(context, ping_ms: int) -> Result:
    """Update the ping/latency for the current WebSocket connection.

    Args:
        ping_ms: Round-trip latency in milliseconds

    Returns:
        Success result
    """
    ws = context.get("ws")
    if ws and ws in websocket_connections:
        websocket_connections[ws]["ping_ms"] = max(0, int(ping_ms))
    return Success("Ping updated")


@method(name="update_clock_offset")
async def jsonrpc_update_clock_offset(context, offset_ms: float) -> Result:
    """Update the clock offset for the current WebSocket connection.

    Args:
        offset_ms: Clock offset in milliseconds (server_time - client_time)

    Returns:
        Success result
    """
    ws = context.get("ws")
    if ws and ws in websocket_connections:
        websocket_connections[ws]["clock_offset_ms"] = round(offset_ms, 1)
    return Success("Clock offset updated")


@method(name="get_audio_stats")
async def jsonrpc_get_audio_stats(context) -> Result:
    """Get audio pipeline latency statistics.

    Returns:
        Success result containing:
        - recent: List of recent playback stats
        - active: Currently active streams
        - averages: Average latency metrics
        - percentiles: Percentile latency metrics
        - total_samples: Total number of samples collected
    """
    try:
        stats = audioplayer_stats.get_summary()
        return Success(stats)
    except Exception as e:
        _log.error(f"Failed to get audio stats: {e}", exc_info=True)
        return Error(1, f"Failed to get audio stats: {str(e)}")


@method(name="clear_audio_stats")
async def jsonrpc_clear_audio_stats(context) -> Result:
    """Clear all audio pipeline statistics.

    Returns:
        Success result
    """
    try:
        audioplayer_stats.clear()
        return Success("Audio statistics cleared")
    except Exception as e:
        _log.error(f"Failed to clear audio stats: {e}", exc_info=True)
        return Error(1, f"Failed to clear audio stats: {str(e)}")


@method(name="register_user")
async def jsonrpc_register_user(context, user_name: str, channelid: str = "1033659964457230392") -> Result:
    """Register the username for the current WebSocket connection.

    Args:
        user_name: Username to associate with this connection
        channelid: Voice channel ID for broadcasting updates (optional)

    Returns:
        Success or error result
    """
    ws = context.get("ws")
    if not ws:
        return Error(1, "No WebSocket connection found")

    # Update the username for this connection and mark as registered
    if ws in websocket_connections:
        websocket_connections[ws]["username"] = user_name
        websocket_connections[ws]["registered"] = True
        _log.info(
            f"Updated user to '{user_name}' from IP {websocket_connections[ws]['ip']}. Total connections: {len(websocket_connections)}"
        )
    else:
        # Shouldn't happen, but handle it
        websocket_connections[ws] = {"username": user_name, "ip": "unknown", "registered": True}
        _log.warning(f"Registered user '{user_name}' for unknown WebSocket connection")

    # Broadcast updated connection list
    bot = context["app"]["bot"]
    await broadcast_queue_update(bot, channelid)

    return Success(f"Registered as {user_name}")


async def handle_websocket(request):
    """Handle WebSocket connections for real-time updates and RPC commands."""
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)

    # Get real IP from X-Real-IP header (set by reverse proxy) or fall back to remote address
    real_ip = request.headers.get("X-Real-IP", request.remote or "unknown")

    # Get hostname via reverse DNS lookup
    hostname = await asyncio.get_event_loop().run_in_executor(None, get_hostname_from_ip, real_ip)

    current_time = time.time()
    websocket_connections[ws] = {
        "username": "Anonymous",
        "ip": real_ip,
        "hostname": hostname,
        "connected_at": current_time,
        "last_ping": current_time,
        "ping_ms": 0,
        "registered": False,
    }
    _log.info(
        f"WebSocket client connected from {real_ip} ({hostname}). Total connections: {len(websocket_connections)}"
    )

    bot = request.app["bot"]

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                    # Handle ping/pong for latency measurement and clock synchronization
                    if data.get("type") == "ping":
                        # Send back pong with server timestamp for clock sync
                        server_time = time.time()
                        websocket_connections[ws]["last_ping"] = server_time
                        pong_response = {"type": "pong", "server_time": server_time}
                        # Echo back ping_id if provided
                        if "ping_id" in data:
                            pong_response["ping_id"] = data["ping_id"]
                        await ws.send_json(pong_response)
                        continue

                    # Handle JSON-RPC over WebSocket
                    if "method" in data:
                        from jsonrpcserver import async_dispatch

                        # Create context with request app and ws
                        rpc_context = {"app": request.app, "ws": ws}
                        response = await async_dispatch(msg.data, context=rpc_context)
                        await ws.send_str(response)

                except json.JSONDecodeError:
                    await ws.send_json({"error": "Invalid JSON"})
                except Exception as e:
                    _log.error(f"Error handling WebSocket message: {e}", exc_info=True)
                    await ws.send_json({"error": str(e)})

            elif msg.type == aiohttp.WSMsgType.ERROR:
                _log.error(f"WebSocket connection closed with exception: {ws.exception()}")

    finally:
        websocket_connections.pop(ws, None)
        _log.info(f"WebSocket client disconnected. Total connections: {len(websocket_connections)}")

        # Broadcast updated connection list (use default channel)
        try:
            await broadcast_queue_update(bot, "1033659964457230392")
        except Exception as e:
            _log.warning(f"Failed to broadcast queue update on disconnect: {e}")

    return ws
