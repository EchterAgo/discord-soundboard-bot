import asyncio
import logging
import os
from pathlib import Path, PureWindowsPath

import discord
from discord.ext import commands

import requests


def get_setting(name: str) -> str:
    if res := os.environ.get(name):
        return res
    raise KeyError()


CONFIG_DISCORD_TOKEN = get_setting('CONFIG_DISCORD_TOKEN')
CONFIG_AUDIO_BASE_DIR = Path(get_setting('CONFIG_AUDIO_BASE_DIR'))


# _log = logging.getLogger(__name__)
_log = logging.getLogger('discord')


class AudioPlayer(commands.Cog, name='Audio Player'):
    queues_ = {}

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def summon(self, ctx):
        pass

    @staticmethod
    async def raise_error(ctx, msg):
        await ctx.send(msg)
        raise commands.CommandError(msg)

    @commands.command()
    async def play(self, ctx, *, query: str):
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            await self.raise_error(ctx, "Bot is not connected to a voice channel.")

        filename = CONFIG_AUDIO_BASE_DIR / PureWindowsPath(query)

        if not filename.is_file():
            await ctx.send("Audio file not found.")
            return

        ctx.voice_client.play(discord.FFmpegOpusAudio(filename), after=lambda e: _log.info(f'Playback done {e}'))

    @commands.command()
    async def stop(self, ctx):
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.voice_client.disconnect()

    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            channel = None
            if hasattr(ctx.author, 'voice') and ctx.author.voice:
                channel = ctx.author.voice.channel
            else:
                channel = next(iter(ctx.guild.voice_channels), None)

            if channel:
                # Bot does not need to listen to the channel, so self-deafen
                await channel.connect(self_deaf=True)
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()


class Controller(commands.Cog, name='Controller'):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def set_avatar(self, ctx, url):
        img = requests.get(url).content
        await self.bot.user.edit(avatar=img)

    @commands.command()
    async def set_name(self, ctx, name):
        await self.bot.user.edit(username=name)


class MyBot(commands.Bot):
    async def process_commands(self, message: discord.Message, /) -> None:
        ctx = await self.get_context(message)
        await self.invoke(ctx)


intents = discord.Intents.default()
intents.message_content = True
bot = MyBot(
    command_prefix=commands.when_mentioned_or("!"),
    description='Simple Audio player bot',
    intents=intents
)


@bot.event
async def on_ready():
    _log.info(f'We have logged in as {bot.user} (ID: {bot.user.id})')


async def main():
    async with bot:
        await bot.add_cog(AudioPlayer(bot))
        await bot.add_cog(Controller(bot))
        await bot.start(CONFIG_DISCORD_TOKEN)

discord.utils.setup_logging()

asyncio.run(main())

# https://discord.com/api/oauth2/authorize?client_id=1085103559244251179&permissions=2048&scope=bot
