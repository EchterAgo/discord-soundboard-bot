import logging
from pathlib import PureWindowsPath
import random
import asyncio
from collections import deque
import discord
from discord import app_commands
from discord.ext import commands

from config import CONFIG_AUDIO_BASE_DIR
from utils import caseless_in, find_files
from typing import Callable, Iterator, List, Optional

_log = logging.getLogger(__name__)


def get_sounds() -> Iterator[str]:
    return find_files(CONFIG_AUDIO_BASE_DIR)


class QueueItem:
    def __init__(self, query: str, user_id: int, user_name: str = "System", after: Optional[Callable[[], None]] = None):
        self.query = query
        self.user_id = user_id
        self.user_name = user_name
        self.after = after


class AudioPlayer(commands.Cog):
    def __init__(self, bot):
        self.qualified_name
        self.bot = bot
        self.queue: deque[QueueItem] = deque()
        self.current_item: Optional[QueueItem] = None
        self.is_processing = False

    @commands.command()
    @commands.guild_only()
    async def ping(self, ctx: commands.Context):
        await ctx.send("pong")

    @commands.command()
    @commands.guild_only()
    async def play(self, ctx: commands.Context, query: str):
        try:
            await self.queue_sound(ctx, query, ctx.author.id, user_name=str(ctx.author))
        except commands.CommandError as e:
            await ctx.send(str(e))
            raise

    def can_interrupt(self, user_id: int) -> bool:
        """Check if user can interrupt current playback"""
        if self.current_item is None:
            return True
        # User can interrupt their own sound or if they have manage_guild permission
        # We'll check permissions later when we have the interaction/context
        return self.current_item.user_id == user_id

    def _get_queue_message(self, sound: str, interrupt: bool, play_next: bool, user_id: int, has_manage_permission: bool) -> str:
        """Generate queue status message based on action.
        
        Args:
            sound: Sound file name
            interrupt: Whether interrupt was requested
            play_next: Whether play_next was requested
            user_id: User ID making the request
            has_manage_permission: Whether user has manage_guild permission
            
        Returns:
            Status message string
        """
        queue_position = len(self.queue)
        if interrupt or (self.is_processing and self.can_interrupt(user_id)):
            if has_manage_permission or self.can_interrupt(user_id):
                return f'Interrupting and playing "{sound}"...'
            else:
                return f'Queued "{sound}" (position {queue_position + 1})...'
        elif play_next:
            return f'Queued "{sound}" to play next...'
        elif queue_position > 0:
            return f'Queued "{sound}" (position {queue_position + 1})...'
        else:
            return f'Playing "{sound}"...'

    async def _handle_slash_play(self, interaction: discord.Interaction, sound: str, interrupt: bool, play_next: bool):
        """Common handler for slash command plays.
        
        Args:
            interaction: Discord interaction
            sound: Sound to play
            interrupt: Whether to interrupt current playback
            play_next: Whether to play next or append to queue
        """
        assert interaction.guild is not None
        
        has_manage = interaction.user.guild_permissions.manage_guild
        message = self._get_queue_message(sound, interrupt, play_next, interaction.user.id, has_manage)
        await interaction.response.send_message(message, ephemeral=True, delete_after=10)

        try:
            class InteractionContext:
                voice_client = interaction.guild.voice_client
                user = interaction.user
            
            await self.queue_sound(
                InteractionContext(), 
                sound, 
                interaction.user.id, 
                after=None,
                interrupt=interrupt,
                play_next=play_next,
                user_name=str(interaction.user)
            )
        except commands.CommandError as e:
            await interaction.followup.send(content=str(e), ephemeral=True)
            raise

    async def queue_sound(self, ctx, query: str, user_id: int, after: Optional[Callable[[], None]] = None, interrupt: bool = False, play_next: bool = False, user_name: str = "System"):
        """Queue a sound to play.
        
        Args:
            ctx: Context with voice_client
            query: Sound file to play
            user_id: User ID requesting playback
            after: Optional callback after playback
            interrupt: If True, force interrupt (requires permission). If False, check user permissions.
            play_next: If True, insert at front of queue. If False, append to end.
            user_name: Display name of user requesting playback
        """
        if not ctx.voice_client:
            raise commands.CommandError("Bot is not connected to a voice channel.")

        item = QueueItem(query, user_id, user_name, after)
        
        # Determine if interruption is allowed
        should_interrupt = interrupt
        
        if not should_interrupt:
            # Check if user can interrupt based on permissions
            can_interrupt = self.can_interrupt(user_id)
            
            # Check for manage_guild permission if not their own sound
            if not can_interrupt and hasattr(ctx, 'author'):
                member = ctx.author
                if member.guild_permissions.manage_guild:
                    can_interrupt = True
            elif not can_interrupt and hasattr(ctx, 'user'):
                member = ctx.user
                if member.guild_permissions.manage_guild:
                    can_interrupt = True
            
            should_interrupt = can_interrupt
        
        if should_interrupt and ctx.voice_client.is_playing():
            # Interrupt current playback
            _log.info(f"{user_name} (ID: {user_id}) interrupting current sound, clearing queue ({len(self.queue)} items)")
            ctx.voice_client.stop()
            self.queue.clear()
        
        # Add to queue
        if play_next:
            # Insert at the beginning of the queue (play next)
            _log.info(f"{user_name} (ID: {user_id}) queued '{query}' to play next (queue size: {len(self.queue) + 1})")
            self.queue.appendleft(item)
        else:
            # Add to the end of the queue
            _log.info(f"{user_name} (ID: {user_id}) queued '{query}' at position {len(self.queue) + 1}")
            self.queue.append(item)
        
        if not self.is_processing:
            await self.process_queue(ctx.voice_client)

    async def process_queue(self, voice_client):
        """Process the audio queue"""
        if self.is_processing:
            return
            
        self.is_processing = True
        _log.info(f"Starting queue processing with {len(self.queue)} items")
        
        while self.queue:
            item = self.queue.popleft()
            self.current_item = item
            
            _log.info(f"Playing '{item.query}' for {item.user_name} (ID: {item.user_id}) - {len(self.queue)} remaining in queue")
            
            try:
                await self._play_sound(voice_client, item.query, item.after)
                # Wait for playback to finish
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)
            except Exception as e:
                _log.error(f"Error playing sound '{item.query}': {e}", exc_info=True)
            
        self.current_item = None
        self.is_processing = False
        _log.info("Queue processing finished")

    async def _play_sound(self, voice_client, query: str, after: Optional[Callable[[], None]] = None):
        """Internal method to play a sound"""
        filename = CONFIG_AUDIO_BASE_DIR / PureWindowsPath(query)

        try:
            filename.resolve().relative_to(CONFIG_AUDIO_BASE_DIR.resolve())
        except ValueError:
            raise commands.CommandError("Naughty.")

        if not filename.is_file():
            raise commands.CommandError("Audio file not found.")

        # Wait for voice client to be ready
        from bot import wait_for_voice_connection
        if not await wait_for_voice_connection(voice_client):
            raise commands.CommandError("Voice client not connected after waiting")

        def after_callback(e):
            if e:
                _log.error(f'Player error: {e}')
            if after:
                after()
            _log.info(f'Playback "{query}" done.')

        # Use FFmpegPCMAudio for audio playback
        source = discord.FFmpegPCMAudio(str(filename))
        voice_client.play(source, after=after_callback)

    @app_commands.command(name="p", description="Plays a sound in voice channel")
    @app_commands.describe(
        sound="Pick a sound!",
        interrupt="Force interrupt current sound (default: auto based on permissions)",
        play_next="Play after current sound instead of at end of queue"
    )
    @app_commands.guild_only()
    async def play_slash(
        self,
        interaction: discord.Interaction,
        sound: str,
        interrupt: bool = False,
        play_next: bool = False,
    ):
        await self._handle_slash_play(interaction, sound, interrupt, play_next)

    @play_slash.autocomplete('sound')
    async def autocomplete_sounds(self, interaction: discord.Interaction, current: str):
        choices = [sound for sound in get_sounds() if caseless_in(current, sound)]
        return [app_commands.Choice(name=choice, value=choice) for choice in choices[:25]]

    @app_commands.command(name="mimi", description="Plays a random mimi sound in voice channel")
    @app_commands.describe(
        interrupt="Force interrupt current sound (default: auto based on permissions)",
        play_next="Play after current sound instead of at end of queue"
    )
    @app_commands.guild_only()
    async def mimi(
        self, 
        interaction: discord.Interaction,
        interrupt: bool = False,
        play_next: bool = False,
    ):
        assert interaction.guild is not None  # guild_only ensures this
        mimi_sounds = [sound for sound in get_sounds() if sound.startswith("ago/mimi")]
        sound = random.choice(mimi_sounds)
        await self._handle_slash_play(interaction, sound, interrupt, play_next)

    async def rpc_play(self, ctx, query: str, after: Optional[Callable[[], None]] = None):
        """Legacy RPC play method - queues sound with system user ID"""
        await self.queue_sound(ctx, query, 0, after, interrupt=False, play_next=False, user_name="RPC/System")  # Use user_id=0 for RPC/system calls

    async def ensure_voice_connection(self, guild, channel) -> Optional[discord.VoiceClient]:
        """Ensure bot is connected to a voice channel and wait for connection.
        
        Args:
            guild: Discord guild
            channel: Channel to connect to (or None to find a voice channel)
            
        Returns:
            Voice client if successful, None otherwise
        """
        from bot import wait_for_voice_connection
        
        # Check if already connected and ready
        if guild.voice_client is not None and guild.voice_client.is_connected():
            _log.debug("Already connected to voice channel")
            return guild.voice_client
        
        # Need to connect
        try:
            if hasattr(channel, 'connect'):
                _log.info(f"Connecting to voice channel {channel.id}")
                await channel.connect(timeout=10.0, reconnect=False)
                await guild.change_voice_state(channel=channel, self_deaf=True)
            else:
                # Find a voice channel in the guild
                voice_channel = next((c for c in guild.voice_channels if c), None)
                if voice_channel:
                    _log.info(f"Connecting to voice channel {voice_channel.id}")
                    await voice_channel.connect(timeout=10.0, reconnect=False)
                    await guild.change_voice_state(channel=voice_channel, self_deaf=True)
                else:
                    _log.error("No voice channel available in guild")
                    return None
            
            # Wait for voice client to be ready
            if guild.voice_client:
                if not await wait_for_voice_connection(guild.voice_client):
                    _log.error("Voice client failed to connect after waiting")
                    # Clean up failed connection
                    if guild.voice_client:
                        await guild.voice_client.disconnect(force=True)
                    return None
            
            _log.info("Voice connection established successfully")
            return guild.voice_client
            
        except asyncio.TimeoutError:
            _log.error("Voice connection timed out")
            # Clean up failed connection
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception as e:
                    _log.error(f"Error disconnecting after timeout: {e}")
            return None
        except Exception as e:
            _log.error(f"Error establishing voice connection: {e}", exc_info=True)
            # Clean up failed connection
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception:
                    pass
            return None

    def stop_playback(self, voice_client, user_name: str = "System") -> dict:
        """Stop current playback and clear queue.
        
        Args:
            voice_client: The voice client to stop
            user_name: Name of user requesting stop (for logging)
            
        Returns:
            dict with 'stopped' (bool), 'queue_cleared' (int) keys
        """
        queue_size = len(self.queue)
        was_playing = voice_client and voice_client.is_playing()
        
        # Clear the queue
        if queue_size > 0:
            _log.info(f"{user_name} cleared {queue_size} queued items")
            self.queue.clear()
        
        # Stop current playback
        if was_playing:
            _log.info(f"{user_name} stopped current playback")
            voice_client.stop()
        
        return {
            'stopped': was_playing,
            'queue_cleared': queue_size
        }

    @commands.command()
    @commands.guild_only()
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue"""
        if ctx.voice_client:
            result = self.stop_playback(ctx.voice_client, user_name=str(ctx.author))
            if result['stopped'] or result['queue_cleared'] > 0:
                msg_parts = []
                if result['stopped']:
                    msg_parts.append("Stopped playback")
                if result['queue_cleared'] > 0:
                    msg_parts.append(f"cleared {result['queue_cleared']} queued items")
                await ctx.send(" and ".join(msg_parts))
            else:
                await ctx.send("Nothing to stop")
        else:
            await ctx.send("Not connected to voice")

    async def cog_before_invoke(self, ctx: commands.Context):
        """This runs before every command in the cog"""
        # Only run for regular commands, not app commands
        if isinstance(ctx, commands.Context):
            assert ctx.guild is not None  # guild_only on all commands ensures this
            if ctx.voice_client is None:
                if ctx.author.voice:
                    await ctx.author.voice.channel.connect()
                else:
                    await ctx.send('You are not connected to a voice channel.')
                    raise commands.CommandError('Author not connected to a voice channel.')

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """This runs before app commands in the cog"""
        assert interaction.guild is not None  # guild_only on all app commands ensures this
        if interaction.guild.voice_client is None:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                await interaction.response.send_message('You are not connected to a voice channel.', ephemeral=True)
                return False
        return True
