import logging
from pathlib import PureWindowsPath
import random
import nextcord
from nextcord.ext import commands

from config import CONFIG_AUDIO_BASE_DIR
from utils import caseless_in, find_files
from typing import Callable, Iterator, List

_log = logging.getLogger(__name__)


def get_sounds() -> Iterator[str]:
    return find_files(CONFIG_AUDIO_BASE_DIR)


class AudioPlayer(commands.Cog, name="Audio Player"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, interaction: nextcord.Interaction):
        await interaction.response.send_message("pong")

    @commands.command()
    async def play(self, interaction: nextcord.Interaction, query: str):
        try:
            await self.rpc_play(interaction.guild, query)
        except commands.CommandError as e:
            await interaction.response.send_message(str(e))
            raise

    @nextcord.slash_command(name="p", description="Plays a sound in voice channel")
    async def play_slash(
        self,
        interaction: nextcord.Interaction,
        sound: str = nextcord.SlashOption(required=True, description="Pick a sound!", autocomplete=True),
    ):
        response = await interaction.response.send_message(
            f'Playing sound "{sound}"...', ephemeral=True, delete_after=10
        )

        def delete_response():
            pass
            # await response.delete_original_response()

        try:
            await self.rpc_play(interaction.guild, sound, after=delete_response)
        except commands.CommandError as e:
            await interaction.response.send_message(str(e), ephemeral=True, delete_after=10)
            raise

    @play_slash.on_autocomplete("sound")
    async def autocomplete_sounds(self, interaction: nextcord.Interaction, item: str):
        choices = [sound for sound in get_sounds() if caseless_in(item.lower(), sound)]
        await interaction.response.send_autocomplete(choices[:25])

    @nextcord.slash_command(name="mimi", description="Plays a random mimi sound in voice channel")
    async def mimi(self, interaction: nextcord.Interaction):
        mimi_sounds = [sound for sound in get_sounds() if sound.startswith("ago/mimi")]
        sound = random.choice(mimi_sounds)

        response = await interaction.response.send_message(
            f'Playing sound "{sound}"...', ephemeral=True, delete_after=10
        )

        def delete_response():
            pass
            # await response.delete_original_response()

        try:
            await self.rpc_play(interaction.guild, sound, after=delete_response)
        except commands.CommandError as e:
            await interaction.response.send_message(str(e), ephemeral=True, delete_after=10)
            raise

    async def rpc_play(self, guild: nextcord.Guild, query: str, after: Callable[[], None] = None):
        if not guild.voice_client or not guild.voice_client.is_connected():
            raise commands.CommandError("Bot is not connected to a voice channel.")

        filename = CONFIG_AUDIO_BASE_DIR / PureWindowsPath(query)

        try:
            filename.resolve().relative_to(CONFIG_AUDIO_BASE_DIR.resolve())
        except ValueError:
            raise commands.CommandError("Naughty.")

        if not filename.is_file():
            raise commands.CommandError("Audio file not found.")

        def after_callback(e):
            if after:
                after()
            _log.info(f'Playback "{query}" done.')

        guild.voice_client.play(nextcord.FFmpegOpusAudio(filename), after=after_callback)

    @commands.command()
    async def stop(self, ctx: nextcord.ext.commands.Context):
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            # await ctx.voice_client.disconnect()
            # ctx.voice_client.cleanup()

    @play.before_invoke
    @play_slash.before_invoke
    @mimi.before_invoke
    async def ensure_voice(self, ctx: nextcord.ext.commands.Context):
        try:
            channel = ctx.channel
            if hasattr(ctx.user, "voice") and ctx.user.voice:
                channel = ctx.user.voice.channel
            await self.rpc_ensure_voice(ctx.guild, channel)
        except commands.CommandError as e:
            await ctx.send(str(e))
            raise

    async def rpc_ensure_voice(self, guild: nextcord.Guild, channel: nextcord.abc.GuildChannel):
        if guild.voice_client is None:
            if not channel:
                channel = next(iter(guild.voice_channels), None)

            if channel:
                await channel.connect()
                await guild.change_voice_state(channel=channel, self_deaf=True)
            else:
                raise commands.CommandError("Author not connected to a voice channel.")
        elif guild.voice_client.is_playing():
            guild.voice_client.stop()

    async def rpc_send_message(self, channel: nextcord.abc.GuildChannel, message: str):
        await channel.send(content=message)
