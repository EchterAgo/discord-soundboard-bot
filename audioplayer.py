import logging
from pathlib import PurePosixPath
import random
import asyncio
import subprocess
import threading
import time
import os
import discord
from discord import app_commands
from discord.ext import commands
import json
from functools import lru_cache

from config import CONFIG_AUDIO_BASE_DIR
from utils import caseless_in, find_files
from observable import ObservableDeque, ObservableDict, ObservableDequeDict
from typing import Callable, Iterator, Optional, Dict
import audioop
from audio_stats import audio_stats

_log = logging.getLogger(__name__)


@lru_cache(maxsize=1024)
def get_audio_duration(filepath: str) -> Optional[float]:
    """Get audio duration in seconds using ffprobe.

    Args:
        filepath: Path to audio file

    Returns:
        Duration in seconds, or None if unable to determine
    """
    try:
        args = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", filepath]
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            return duration if duration > 0 else None
    except Exception as e:
        _log.debug(f"Could not get duration for {filepath}: {e}")
    return None


def get_sounds() -> Iterator[str]:
    return find_files(CONFIG_AUDIO_BASE_DIR)


class QueueItem:
    def __init__(
        self,
        query: str,
        user_id: int,
        user_name: str = "System",
        after: Optional[Callable[[], None]] = None,
        volume_boost: float = 1.0,
        audio_filters: Optional[Dict] = None,
        request_timestamp: Optional[float] = None,
    ):
        self.query = query
        self.user_id = user_id
        self.user_name = user_name
        self.after = after
        self.request_timestamp = request_timestamp
        # Handle backward compatibility: volume_boost can be in audio_filters or as separate param
        self.audio_filters = audio_filters or {}
        if "volume_boost" in self.audio_filters:
            self.volume_boost = self.audio_filters["volume_boost"]
        else:
            self.volume_boost = volume_boost
            self.audio_filters["volume_boost"] = volume_boost


class UserAudioStream:
    """Represents an audio stream for a single user"""

    def __init__(
        self,
        filepath: str,
        user_id: int,
        user_name: str,
        volume_boost: float = 1.0,
        audio_filters: Optional[Dict] = None,
        request_timestamp: Optional[float] = None,
    ):
        self.filepath = filepath
        self.user_id = user_id
        self.user_name = user_name
        # Handle backward compatibility: volume_boost can be in audio_filters or as separate param
        self.audio_filters = audio_filters or {}
        if "volume_boost" in self.audio_filters:
            volume_boost = self.audio_filters["volume_boost"]
        self.volume_boost = max(0.0, min(3.0, volume_boost))  # Clamp between 0 and 3
        self.audio_filters["volume_boost"] = self.volume_boost
        self.process: Optional[subprocess.Popen] = None
        self.finished = False
        self.after_callback: Optional[Callable[[], None]] = None
        self.request_timestamp = request_timestamp  # Timestamp when playback was requested
        self.first_byte_timestamp: Optional[float] = None  # Timestamp when first byte was read
        base_duration = get_audio_duration(filepath)

        # Adjust duration if timestretch is applied
        if base_duration and self.audio_filters.get("rubberband_tempo", 1.0) != 1.0:
            tempo = self.audio_filters.get("rubberband_tempo", 1.0)
            self.duration = base_duration / tempo  # Slower tempo = longer duration
        else:
            self.duration = base_duration

        self.current_time_us: int = 0  # Current playback position in microseconds
        self.progress_thread: Optional[threading.Thread] = None
        self.progress_stop_event = threading.Event()

    def start(self):
        """Start the FFmpeg process for this audio stream"""
        import os

        # Create pipe for progress output
        progress_r, progress_w = os.pipe()

        args = [
            "ffmpeg",
            "-thread_queue_size",
            "512",  # Force separate input thread, prevent packet drops in low-latency scenarios
            "-fflags",
            "+discardcorrupt",  # Only discard corrupt frames, keep buffering for accurate decoding
            "-i",
            str(self.filepath),
            "-progress",
            f"pipe:{progress_w}",  # Progress output to the write end of our pipe
            "-stats_period",
            "0.5",  # Update progress every 500ms (was 0.1 - reduced to prevent pipe blocking)
        ]

        # Build audio filter chain
        filters = []

        # Compressor filter (upward mode to boost quiet signals aggressively)
        if self.audio_filters.get("compressor"):
            # mode=upward: expand quiet signals instead of compressing loud ones
            # ratio=2: aggressive expansion (doubles the volume increase)
            # makeup=2: amplify signal by 2x after processing
            # Keeps other settings at defaults for smooth operation
            filters.append("acompressor=mode=upward:ratio=2:makeup=2")

        # Bass boost (low shelf filter at 100Hz)
        bass_boost = self.audio_filters.get("bass_boost", 0)
        if bass_boost != 0:
            filters.append(f"bass=g={bass_boost}:f=100")

        # Treble boost (high shelf filter at 3000Hz)
        treble_boost = self.audio_filters.get("treble_boost", 0)
        if treble_boost != 0:
            filters.append(f"treble=g={treble_boost}:f=3000")

        # High-pass filter (remove frequencies below threshold)
        highpass = self.audio_filters.get("highpass", 0)
        if highpass > 0:
            filters.append(f"highpass=f={highpass}")

        # Low-pass filter (remove frequencies above threshold)
        lowpass = self.audio_filters.get("lowpass", 0)
        if lowpass > 0:
            filters.append(f"lowpass=f={lowpass}")

        # Chorus effect
        if self.audio_filters.get("chorus"):
            filters.append("chorus=0.5:0.9:50|60|40:0.4|0.32|0.3:0.25|0.4|0.3:2|2.3|1.3")

        # Earwax effect (makes audio sound like it's coming through ear wax)
        if self.audio_filters.get("earwax"):
            filters.append("earwax")

        # Rubberband time stretching (pitch shift)
        rubberband_pitch = self.audio_filters.get("rubberband_pitch", 0)
        if rubberband_pitch != 0:
            # Convert semitones to ratio (each semitone is 2^(1/12))
            ratio = 2 ** (rubberband_pitch / 12.0)
            filters.append(f"rubberband=pitch={ratio}")

        # Rubberband time stretch (tempo change without pitch change)
        rubberband_tempo = self.audio_filters.get("rubberband_tempo", 1.0)
        if rubberband_tempo != 1.0:
            filters.append(f"rubberband=tempo={rubberband_tempo}")

        # Silence removal
        if self.audio_filters.get("silence_remove"):
            filters.append(
                "silenceremove=start_periods=1:start_duration=0.1:start_threshold=-50dB:stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB"
            )

        # Tremolo effect (amplitude modulation)
        tremolo_freq = self.audio_filters.get("tremolo_freq", 0)
        if tremolo_freq > 0:
            tremolo_depth = self.audio_filters.get("tremolo_depth", 0.5)
            filters.append(f"tremolo=f={tremolo_freq}:d={tremolo_depth}")

        # Vibrato effect (frequency modulation)
        vibrato_freq = self.audio_filters.get("vibrato_freq", 0)
        if vibrato_freq > 0:
            vibrato_depth = self.audio_filters.get("vibrato_depth", 0.5)
            filters.append(f"vibrato=f={vibrato_freq}:d={vibrato_depth}")

        # Super equalizer (10-band)
        supereq_bands = self.audio_filters.get("supereq_bands")
        if supereq_bands and any(v != 0 for v in supereq_bands):
            # Bands: 65, 130, 260, 520, 1k, 2k, 4k, 8k, 16k Hz
            filters.append(
                f"superequalizer=1b={supereq_bands[0]}:2b={supereq_bands[1]}:3b={supereq_bands[2]}:4b={supereq_bands[3]}:5b={supereq_bands[4]}:6b={supereq_bands[5]}:7b={supereq_bands[6]}:8b={supereq_bands[7]}:9b={supereq_bands[8]}"
            )

        # Volume filter (always apply if not 1.0)
        if self.volume_boost != 1.0:
            filters.append(f"volume={self.volume_boost}")

        # Apply filter chain if any filters were added
        if filters:
            args.extend(["-af", ",".join(filters)])

        args.extend(
            [
                "-f",
                "s16le",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-bufsize",
                "16k",  # TEST 2: Reduced buffer for lower latency (was 64k)
                "-loglevel",
                "warning",
                "pipe:1",
            ]
        )
        try:
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # Prevent stderr buffer from blocking FFmpeg
                bufsize=0,  # Unbuffered
                pass_fds=(progress_w,),
            )
            # Close write end in parent, keep read end
            os.close(progress_w)

            # Track stream start for stats only if we have a request timestamp (not a queue transition)
            if self.request_timestamp is not None:
                audio_stats.mark_stream_start(self.user_id)

            # Start thread to read progress updates
            self.progress_thread = threading.Thread(target=self._read_progress, args=(progress_r,), daemon=True)
            self.progress_thread.start()

        except FileNotFoundError:
            _log.error("FFmpeg not found! Please install FFmpeg to use audio mixing.")
            os.close(progress_r)
            os.close(progress_w)
            raise commands.CommandError("FFmpeg is required for audio playback")
        except Exception as e:
            _log.error(f"Failed to start FFmpeg: {e}", exc_info=True)
            os.close(progress_r)
            try:
                os.close(progress_w)
            except:
                pass
            raise

    def _read_progress(self, progress_fd: int):
        """Read progress updates from ffmpeg in a background thread."""
        try:
            # Use line buffering (buffering=1) to avoid internal buffering that can block the pipe
            with os.fdopen(progress_fd, "r", buffering=1) as progress_file:
                current_block = {}
                for line in progress_file:
                    line = line.strip()
                    if not line:
                        continue

                    if "=" in line:
                        key, value = line.split("=", 1)
                        current_block[key] = value

                        # When we get out_time_us, update our position
                        if key == "out_time_us" and value != "N/A":
                            try:
                                self.current_time_us = int(value)
                            except ValueError:
                                pass

                        # Check if this block is complete
                        if key == "progress":
                            current_block = {}

                    if self.progress_stop_event.is_set():
                        break
        except Exception:
            pass

    def read(self, size: int) -> bytes:
        """Read audio data from the stream"""
        if self.finished or not self.process:
            return b""

        try:
            data = self.process.stdout.read(size)
            if not data:
                self.finished = True
                if self.after_callback:
                    self.after_callback()
            else:
                # Track first byte latency only if we're tracking this request (not a queue transition)
                if self.first_byte_timestamp is None:
                    self.first_byte_timestamp = time.time()
                    if self.request_timestamp is not None:
                        audio_stats.mark_first_byte(self.user_id)
                        latency_ms = (self.first_byte_timestamp - self.request_timestamp) * 1000
                        _log.info(
                            f"[LATENCY] {self.user_name}: {latency_ms:.2f}ms from button press to first byte decoded (file: {self.filepath})"
                        )
            return data
        except Exception as e:
            _log.error(f"Error reading from stream: {e}")
            self.finished = True
            return b""

    def get_progress_percentage(self) -> Optional[float]:
        """Calculate playback progress as percentage.

        Returns:
            Progress percentage (0-100), or None if duration unknown
        """
        if not self.duration or self.duration <= 0:
            return None

        elapsed_seconds = self.current_time_us / 1_000_000.0  # Convert microseconds to seconds
        percentage = min(100.0, (elapsed_seconds / self.duration) * 100.0)
        return round(percentage, 1)

    def cleanup(self):
        """Clean up the FFmpeg process"""
        # Track stream end for stats synchronously - must happen before we return
        if self.request_timestamp is not None:
            audio_stats.mark_stream_end(self.user_id)

        # Kill the process and signal stop event asynchronously (non-blocking)
        # This is done in a thread to avoid blocking on process termination
        def async_cleanup():
            if self.process:
                try:
                    self.process.kill()
                    # Don't wait for process to fully terminate - just kill and move on
                    # The OS will clean it up
                except Exception as e:
                    _log.debug(f"Error killing process: {e}")
            
            # Signal progress thread to stop
            self.progress_stop_event.set()
        
        # Run cleanup in background thread
        threading.Thread(target=async_cleanup, daemon=True).start()


class MixedAudioSource(discord.AudioSource):
    """Audio source that mixes multiple per-user audio streams"""

    def __init__(
        self,
        stream_finished_event: Optional[asyncio.Event] = None,
        stream_changed_callback: Optional[Callable[[], None]] = None,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        # Use ObservableDict to automatically trigger callback on changes
        self.streams: Dict[int, UserAudioStream] = ObservableDict(stream_changed_callback)
        self.lock = threading.Lock()
        self._finished = False
        self.stream_finished_event = stream_finished_event
        self.stream_changed_callback = stream_changed_callback
        self.event_loop = event_loop

    def add_stream(
        self,
        user_id: int,
        filepath: str,
        user_name: str,
        after: Optional[Callable[[], None]] = None,
        volume_boost: float = 1.0,
        audio_filters: Optional[Dict] = None,
        request_timestamp: Optional[float] = None,
    ):
        """Add or replace a user's audio stream"""
        with self.lock:
            # Clean up existing stream for this user
            if user_id in self.streams:
                old_stream = self.streams[user_id]
                old_stream.cleanup()
                _log.info(f"Replaced stream for {user_name} (ID: {user_id})")

            # Create and start new stream
            stream = UserAudioStream(filepath, user_id, user_name, volume_boost, audio_filters, request_timestamp)
            stream.after_callback = after
            stream.start()
            # Assignment triggers ObservableDict callback
            self.streams[user_id] = stream
            _log.info(f"Added stream for {user_name} (ID: {user_id}): {filepath} (volume: {volume_boost}x)")

    def read(self) -> bytes:
        """Read and mix audio from all active streams"""
        if self._finished:
            return b""

        with self.lock:
            # Read from all streams
            chunk_size = 3840  # 20ms at 48kHz stereo 16-bit

            if not self.streams:
                # No streams yet, but we're not finished - return silence to keep playing
                return b"\x00" * chunk_size

            mixed_audio = None
            active_streams = []

            for user_id, stream in list(self.streams.items()):
                if stream.finished:
                    stream.cleanup()
                    # Deletion triggers ObservableDict callback
                    del self.streams[user_id]
                    # Signal that a stream finished
                    if self.stream_finished_event:
                        try:
                            # Use call_soon_threadsafe since we're in a thread
                            if self.event_loop:
                                self.event_loop.call_soon_threadsafe(self.stream_finished_event.set)
                            else:
                                _log.debug("No event loop available to signal stream finished")
                        except Exception as e:
                            _log.debug(f"Could not signal stream finished: {e}")
                    continue

                data = stream.read(chunk_size)
                if data:
                    active_streams.append((user_id, stream.user_name))
                    # Mix audio
                    if mixed_audio is None:
                        mixed_audio = bytearray(data)
                    else:
                        # Ensure both buffers are the same length
                        min_len = min(len(mixed_audio), len(data))
                        # Mix using audioop
                        mixed_audio[:min_len] = audioop.add(bytes(mixed_audio[:min_len]), data[:min_len], 2)
                else:
                    # No more data - stream is finished
                    stream.finished = True
                    stream.cleanup()
                    # Deletion triggers ObservableDict callback
                    del self.streams[user_id]
                    _log.info(f"Stream finished for {stream.user_name} (ID: {user_id}) - no more data")
                    # Signal that a stream finished
                    if self.stream_finished_event:
                        try:
                            # Use call_soon_threadsafe since we're in a thread
                            if self.event_loop:
                                self.event_loop.call_soon_threadsafe(self.stream_finished_event.set)
                        except Exception:
                            pass
                    # Also trigger the callback directly for immediate update
                    if self.stream_changed_callback:
                        try:
                            self.stream_changed_callback()
                        except Exception:
                            pass

            # If no active streams, return silence to keep playing
            if mixed_audio is None:
                # Don't set _finished here - let the queue processor control when to stop
                # Just return silence while waiting for new streams
                return b"\x00" * chunk_size

            # Pad if necessary
            if len(mixed_audio) < chunk_size:
                mixed_audio.extend(b"\x00" * (chunk_size - len(mixed_audio)))

            return bytes(mixed_audio[:chunk_size])

    def cleanup(self):
        """Clean up all streams"""
        with self.lock:
            for stream in self.streams.values():
                stream.cleanup()
            self.streams.clear()
            self._finished = True

    def stop_stream(self, user_id: int):
        """Stop a specific user's audio stream"""
        with self.lock:
            if user_id in self.streams:
                stream = self.streams[user_id]
                stream.finished = True
                stream.cleanup()
                del self.streams[user_id]
                _log.info(f"Stopped stream for {stream.user_name} (ID: {user_id})")
                # Signal that a stream finished
                if self.stream_finished_event:
                    try:
                        if self.event_loop:
                            self.event_loop.call_soon_threadsafe(self.stream_finished_event.set)
                    except Exception:
                        pass

    def is_opus(self) -> bool:
        return False


class AudioPlayer(commands.Cog):
    def __init__(self, bot):
        self.qualified_name
        self.bot = bot
        self.queue_update_callback = None  # Callback for queue updates
        self.user_queues: Dict[int, ObservableDeque] = ObservableDequeDict(
            on_change_callback=lambda: self.queue_update_callback() if self.queue_update_callback else None
        )
        self.mixed_source: Optional[MixedAudioSource] = None
        self.is_processing = False
        self.process_lock = asyncio.Lock()
        self.stream_finished_event = asyncio.Event()
        self.current_voice_client = None  # Track current voice client to detect reconnections

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
        # In mixed mode, users can always add to their own queue
        return True

    def _get_total_queue_size(self) -> int:
        """Get total number of queued items across all users"""
        return sum(len(queue) for queue in self.user_queues.values())

    def _get_queue_message(
        self, sound: str, interrupt: bool, play_next: bool, user_id: int, has_manage_permission: bool
    ) -> str:
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
        user_queue_size = len(self.user_queues[user_id])
        total_queue_size = self._get_total_queue_size()

        if user_queue_size > 0:
            return f'Queued "{sound}" (your queue: {user_queue_size + 1}, total: {total_queue_size + 1})...'
        else:
            return f'Playing "{sound}" (will mix with {total_queue_size} other sounds)...'

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
                user_name=str(interaction.user),
            )
        except commands.CommandError as e:
            await interaction.followup.send(content=str(e), ephemeral=True)
            raise

    async def queue_sound(
        self,
        ctx,
        query: str,
        user_id: int,
        after: Optional[Callable[[], None]] = None,
        interrupt: bool = False,
        play_next: bool = False,
        user_name: str = "System",
        volume_boost: float = 1.0,
        audio_filters: Optional[Dict] = None,
        request_timestamp: Optional[float] = None,
    ):
        """Queue a sound to play in the user's personal queue.

        Args:
            ctx: Context with voice_client
            query: Sound file to play
            user_id: User ID requesting playback
            after: Optional callback after playback
            interrupt: If True, stop this user's current stream and play immediately.
            play_next: If True, insert at front of user's queue. If False, append to end.
            user_name: Display name of user requesting playback
            volume_boost: Volume multiplier (0.0 to 3.0, default 1.0)
            audio_filters: Dictionary of audio filter settings
            request_timestamp: Timestamp when the request was initiated (for latency tracking)
        """
        if not ctx.voice_client:
            raise commands.CommandError("Bot is not connected to a voice channel.")

        # Validate file exists
        filename = CONFIG_AUDIO_BASE_DIR / PurePosixPath(query)
        try:
            filename.resolve().relative_to(CONFIG_AUDIO_BASE_DIR.resolve())
        except ValueError:
            raise commands.CommandError("Naughty.")
        if not filename.is_file():
            raise commands.CommandError("Audio file not found.")

        item = QueueItem(query, user_id, user_name, after, volume_boost, audio_filters, request_timestamp)

        # Check if voice client changed (reconnection) - need to restart playback
        if self.current_voice_client is not None and self.current_voice_client != ctx.voice_client:
            _log.warning("Voice client changed during queue_sound - resetting playback state")
            # Clean up old state without the lock to avoid deadlock
            if self.mixed_source:
                self.mixed_source.cleanup()
                self.mixed_source = None
            self.is_processing = False
            if self.stream_finished_event:
                self.stream_finished_event.set()
            self.current_voice_client = ctx.voice_client

        should_start_playback = False
        async with self.process_lock:
            # If interrupt, stop this user's current stream immediately
            if interrupt:
                # Stop the user's current stream in the mixer (if any)
                self._stop_user_stream(user_id, user_name)
                _log.info(f"{user_name} (ID: {user_id}) interrupted their own stream")

                # Track request start for stats AFTER stopping old stream
                if request_timestamp is None:
                    request_timestamp = audio_stats.start_request(user_id, user_name, str(filename))
                else:
                    audio_stats.start_request(user_id, user_name, str(filename), request_timestamp)
                item.request_timestamp = request_timestamp

                # Add to front of queue to play immediately
                self.user_queues[user_id].appendleft(item)
                audio_stats.mark_queued(user_id)
                _log.info(f"{user_name} (ID: {user_id}) queued '{query}' for instant playback")
                # Signal the processor to check for new work
                if self.stream_finished_event:
                    self.stream_finished_event.set()
            else:
                # Don't track stats for queued items - only track when they actually start playing
                # Set request_timestamp to None so queue transitions don't track stats
                item.request_timestamp = None

                # Add to user's queue
                if play_next and len(self.user_queues[user_id]) > 0:
                    self.user_queues[user_id].appendleft(item)
                    _log.info(f"{user_name} (ID: {user_id}) queued '{query}' to play next in their queue")
                else:
                    self.user_queues[user_id].append(item)
                    user_pos = len(self.user_queues[user_id])
                    total_queued = self._get_total_queue_size()
                    _log.info(
                        f"{user_name} (ID: {user_id}) queued '{query}' (user queue: {user_pos}, total: {total_queued})"
                    )

            # Check if we should start processing
            if not self.is_processing:
                should_start_playback = True

        # Start processing outside the lock to avoid deadlock
        if should_start_playback:
            await self.start_mixed_playback(ctx.voice_client)

    async def start_mixed_playback(self, voice_client):
        """Start the mixed audio playback system"""
        # Check if voice client has changed (reconnection)
        if self.current_voice_client is not None and self.current_voice_client != voice_client:
            _log.warning("Voice client changed - cleaning up old playback state")
            # Clean up old state
            if self.mixed_source:
                self.mixed_source.cleanup()
                self.mixed_source = None
            self.is_processing = False
            if self.stream_finished_event:
                self.stream_finished_event.set()

        self.current_voice_client = voice_client

        if self.is_processing:
            _log.debug("Already processing, not starting new playback")
            return

        self.is_processing = True

        try:
            # Get the current event loop to pass to the callback
            event_loop = asyncio.get_event_loop()

            # Create mixed audio source with callback for stream changes
            def on_stream_changed():
                # This gets called from the audio thread, so use call_soon_threadsafe
                if self.queue_update_callback:
                    event_loop.call_soon_threadsafe(lambda: asyncio.create_task(self.queue_update_callback()))

            self.mixed_source = MixedAudioSource(self.stream_finished_event, on_stream_changed, event_loop)

            # Start the first stream(s) before starting playback
            async with self.process_lock:
                for user_id in list(self.user_queues.keys()):
                    queue = self.user_queues[user_id]
                    if queue:
                        item = queue.popleft()
                        filename = CONFIG_AUDIO_BASE_DIR / PurePosixPath(item.query)
                        # Track stats for initial playback start (this is a new user action)
                        if item.request_timestamp is not None:
                            audio_stats.start_request(user_id, item.user_name, str(filename), item.request_timestamp)
                            audio_stats.mark_queued(user_id)
                        self.mixed_source.add_stream(
                            user_id,
                            str(filename),
                            item.user_name,
                            item.after,
                            item.volume_boost,
                            item.audio_filters,
                            item.request_timestamp,  # Initial playback - track latency
                        )
                        _log.info(f"Started playing '{item.query}' for {item.user_name}")

            voice_client.play(
                self.mixed_source,
                after=lambda e: self._on_playback_done(e),
                application="lowdelay",
                bitrate=128,
                fec=True,
            )

            # Process remaining queue items in background (don't await)
            asyncio.create_task(self.process_user_queues())

        except Exception as e:
            _log.error(f"Error in mixed playback: {e}", exc_info=True)
            self.is_processing = False
            if self.mixed_source:
                self.mixed_source.cleanup()
                self.mixed_source = None

    def _on_playback_done(self, error):
        """Called when the mixed audio source finishes"""
        if error:
            _log.error(f"Playback error: {error}")
        # Don't clean up here - the mixer keeps running until process_user_queues stops it
        # This callback is only for error reporting

    async def process_user_queues(self):
        """Process all user queues and add sounds to the mixer"""
        try:
            # Track last progress update time
            last_progress_update = 0.0
            progress_update_interval = 0.5  # Send progress updates every half second

            while self.is_processing:
                has_work = False

                # Safety check: if we're processing but voice client is not playing, something is wrong
                if self.current_voice_client and not self.current_voice_client.is_playing():
                    if self.user_queues or (self.mixed_source and self.mixed_source.streams):
                        _log.warning("Voice client not playing but we have work - restarting playback")
                        # Try to restart playback
                        if self.mixed_source:
                            try:
                                self.current_voice_client.play(
                                    self.mixed_source,
                                    after=lambda e: self._on_playback_done(e),
                                    application="lowdelay",  # TEST 1: Low-delay opus encoder
                                    bitrate=128,
                                    fec=True,
                                )
                                _log.info("Restarted voice client playback")
                            except Exception as e:
                                _log.error(f"Failed to restart playback: {e}")
                                # If we can't restart, clean up and exit
                                break

                # Check if we should send a progress update (throttled)
                current_time = time.time()
                if current_time - last_progress_update >= progress_update_interval:
                    if self.mixed_source and self.mixed_source.streams:
                        # Trigger queue update to send progress (throttled to 1/sec)
                        if self.queue_update_callback:
                            asyncio.create_task(self.queue_update_callback())
                        last_progress_update = current_time

                async with self.process_lock:
                    # Check each user's queue
                    for user_id in list(self.user_queues.keys()):
                        queue = self.user_queues[user_id]

                        if not queue:
                            # Remove empty queues
                            del self.user_queues[user_id]
                            continue

                        # Check if user already has an active stream
                        if self.mixed_source and user_id in self.mixed_source.streams:
                            has_work = True  # Still have active streams
                            continue  # User already playing, skip

                        # Get next item from user's queue (triggers callback via ObservableDeque)
                        item = queue.popleft()
                        has_work = True

                        # Add to mixer
                        if self.mixed_source:
                            filename = CONFIG_AUDIO_BASE_DIR / PurePosixPath(item.query)
                            # For items that already have stats tracking (interrupt=True items),
                            # pass the request_timestamp so the stream continues tracking.
                            # For normal queue transitions from initial playback, this will be None.
                            self.mixed_source.add_stream(
                                user_id,
                                str(filename),
                                item.user_name,
                                item.after,
                                item.volume_boost,
                                item.audio_filters,
                                item.request_timestamp,  # Pass through from item
                            )
                            _log.info(
                                f"Started playing '{item.query}' for {item.user_name} (user queue remaining: {len(queue)})"
                            )
                        else:
                            _log.error("Mixed source is None, cannot add stream!")

                # Check active streams in mixer
                if self.mixed_source:
                    if self.mixed_source.streams:
                        has_work = True

                # Check if we should stop
                if not has_work:
                    async with self.process_lock:
                        # Double check - no queues and no active streams
                        if not self.user_queues and (not self.mixed_source or not self.mixed_source.streams):
                            break

                # Wait for stream to finish or timeout
                try:
                    await asyncio.wait_for(self.stream_finished_event.wait(), timeout=0.2)
                    self.stream_finished_event.clear()
                except asyncio.TimeoutError:
                    pass  # Timeout is expected, just check again
        finally:
            self.is_processing = False
            if self.mixed_source:
                self.mixed_source._finished = True
                self.mixed_source.cleanup()
                self.mixed_source = None

    async def process_queue(self, voice_client):
        """Legacy method for compatibility - redirects to mixed playback"""
        await self.start_mixed_playback(voice_client)

    async def _play_sound(self, voice_client, query: str, after: Optional[Callable[[], None]] = None):
        """Legacy internal method - not used in mixed mode"""
        # This method is kept for compatibility but won't be used in mixed mode
        pass

    @app_commands.command(name="p", description="Plays a sound in voice channel")
    @app_commands.describe(
        sound="Pick a sound!",
        interrupt="Force interrupt current sound (default: auto based on permissions)",
        play_next="Play after current sound instead of at end of queue",
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

    @play_slash.autocomplete("sound")
    async def autocomplete_sounds(self, interaction: discord.Interaction, current: str):
        choices = [sound for sound in get_sounds() if caseless_in(current, sound)]
        return [app_commands.Choice(name=choice, value=choice) for choice in choices[:25]]

    @app_commands.command(name="mimi", description="Plays a random mimi sound in voice channel")
    @app_commands.describe(
        interrupt="Force interrupt current sound (default: auto based on permissions)",
        play_next="Play after current sound instead of at end of queue",
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
        await self.queue_sound(
            ctx, query, 0, after, interrupt=False, play_next=False, user_name="RPC/System"
        )  # Use user_id=0 for RPC/system calls

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
            return guild.voice_client

        # Need to connect
        try:
            if hasattr(channel, "connect"):
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
        """Stop current playback and clear all queues.

        Args:
            voice_client: The voice client to stop
            user_name: Name of user requesting stop (for logging)

        Returns:
            dict with 'stopped' (bool), 'queue_cleared' (int) keys
        """
        queue_size = self._get_total_queue_size()
        was_playing = voice_client and voice_client.is_playing()

        # Clear all user queues
        if queue_size > 0:
            _log.info(f"{user_name} cleared {queue_size} total queued items")
            self.user_queues.clear()

        # Stop current playback and cleanup mixer
        if was_playing or self.is_processing:
            _log.info(
                f"{user_name} stopped current playback (was_playing={was_playing}, is_processing={self.is_processing})"
            )
            if self.mixed_source:
                self.mixed_source.cleanup()
                self.mixed_source = None
            if voice_client:
                voice_client.stop()
            self.is_processing = False
            # Signal the event to wake up the processing loop so it can exit
            if self.stream_finished_event:
                self.stream_finished_event.set()

        return {"stopped": was_playing, "queue_cleared": queue_size}

    def _stop_user_stream(self, user_id: int, user_name: str = "") -> bool:
        """Stop a specific user's current stream in the mixer.

        Args:
            user_id: The user ID whose stream to stop
            user_name: Name for logging (optional)

        Returns:
            True if a stream was stopped, False if no active stream
        """
        if not self.mixed_source or user_id not in self.mixed_source.streams:
            return False

        stream = self.mixed_source.streams[user_id]
        
        # Mark finished and remove from mixer immediately
        stream.finished = True
        del self.mixed_source.streams[user_id]
        
        # Cleanup synchronously - stats are done sync, process killing is done async internally
        stream.cleanup()
            
        if user_name:
            _log.info(f"{user_name} (ID: {user_id}) stream stopped")
        return True

    def skip_current(self, voice_client, user_id: int, user_name: str = "System") -> dict:
        """Skip the currently playing sound for a specific user and move to the next one.
        Similar to interrupt mode, but just advances the queue instead of playing new sound.

        Args:
            voice_client: The voice client to skip on
            user_id: The user ID whose stream to skip
            user_name: Name of user requesting skip (for logging)

        Returns:
            dict with 'skipped' (bool), 'playing_next' (bool) keys
        """
        _log.info(f"{user_name} skipped current sound (user_id: {user_id})")

        # Stop only this user's stream in the mixer
        was_stopped = self._stop_user_stream(user_id, user_name)

        if was_stopped:
            # Signal the event to wake up the processing loop so it can play the next sound
            if self.stream_finished_event:
                self.stream_finished_event.set()

            return {"skipped": True, "playing_next": len(self.user_queues.get(user_id, [])) > 0}

        _log.info(f"{user_name} attempted to skip but no active stream for user {user_id}")
        return {"skipped": False, "playing_next": False}

    @commands.command()
    @commands.guild_only()
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue"""
        if ctx.voice_client:
            result = self.stop_playback(ctx.voice_client, user_name=str(ctx.author))
            if result["stopped"] or result["queue_cleared"] > 0:
                msg_parts = []
                if result["stopped"]:
                    msg_parts.append("Stopped playback")
                if result["queue_cleared"] > 0:
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
                    await ctx.send("You are not connected to a voice channel.")
                    raise commands.CommandError("Author not connected to a voice channel.")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """This runs before app commands in the cog"""
        assert interaction.guild is not None  # guild_only on all app commands ensures this
        if interaction.guild.voice_client is None:
            if interaction.user.voice:
                await interaction.user.voice.channel.connect()
            else:
                await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
                return False
        return True
