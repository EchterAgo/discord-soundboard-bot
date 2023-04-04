import asyncio
import logging
import os
from pathlib import Path, PureWindowsPath

import discord
from discord.ext import commands

from aiohttp import web

from jsonrpcserver import method, Result, Success, InvalidParams, JsonRpcError, async_dispatch

import requests

from utils import find_files


def get_setting(name: str) -> str:
    if res := os.environ.get(name):
        return res
    raise KeyError()


BOT_BASE_DIR = Path(__file__).parent.resolve()

CONFIG_DISCORD_TOKEN = get_setting('CONFIG_DISCORD_TOKEN')
CONFIG_AUDIO_BASE_DIR = Path(get_setting('CONFIG_AUDIO_BASE_DIR'))

# _log = logging.getLogger(__name__)
_log = logging.getLogger('discord')


class AudioPlayer(commands.Cog, name='Audio Player'):
    queues_ = {}

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx: discord.ext.commands.Context):
        await ctx.send('pong')

    @commands.command()
    async def play(self, ctx: discord.ext.commands.Context, *, query: str):
        try:
            await self.rpc_play(ctx.guild, query)
        except commands.CommandError as e:
            await ctx.send(str(e))
            raise

    async def rpc_play(self, guild: discord.Guild, query: str):
        if not guild.voice_client or not guild.voice_client.is_connected():
            raise commands.CommandError('Bot is not connected to a voice channel.')

        filename = CONFIG_AUDIO_BASE_DIR / PureWindowsPath(query)

        try:
            filename.resolve().relative_to(CONFIG_AUDIO_BASE_DIR.resolve())
        except ValueError:
            raise commands.CommandError('Naughty.')

        if not filename.is_file():
            raise commands.CommandError('Audio file not found.')

        guild.voice_client.play(discord.FFmpegOpusAudio(filename), after=lambda e: _log.info(f'Playback done {e}'))

    @commands.command()
    async def stop(self, ctx: discord.ext.commands.Context):
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.voice_client.disconnect()
            #ctx.voice_client.cleanup()

    @play.before_invoke
    async def ensure_voice(self, ctx: discord.ext.commands.Context):
        try:
            channel = ctx.channel
            if hasattr(ctx.author, 'voice') and ctx.author.voice:
                channel = ctx.author.voice.channel
            await self.rpc_ensure_voice(ctx.guild, channel)
        except commands.CommandError as e:
            await ctx.send(str(e))
            raise

    async def rpc_ensure_voice(self, guild: discord.Guild, channel: discord.abc.GuildChannel):
        if guild.voice_client is None:
            if not channel:
                channel = next(iter(guild.voice_channels), None)

            if channel:
                await channel.connect()
                await guild.change_voice_state(channel=channel, self_deaf=True)
            else:
                raise commands.CommandError('Author not connected to a voice channel.')
        elif guild.voice_client.is_playing():
            guild.voice_client.stop()

    async def rpc_send_message(self, channel: discord.abc.GuildChannel, message: str):
        await channel.send(content=message)


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

    async def on_ready(self):
        _log.info(f'We have logged in as {self.user} (ID: {self.user.id})')


async def start_bot(app):
    intents = discord.Intents.default()
    intents.message_content = True

    bot = MyBot(
        command_prefix=commands.when_mentioned_or('!'),
        description='Simple Audio player bot',
        intents=intents
    )
    app['bot'] = bot
    bot.add_cog(AudioPlayer(bot))
    bot.add_cog(Controller(bot))
    bot_task = asyncio.create_task(bot.start(CONFIG_DISCORD_TOKEN))

    yield

    await bot.close()
    await bot_task


async def http_hello(request):
    return web.Response(text='Hello, world')


@method(name='list')
async def jsonrpc_list(context) -> Result:
    return Success(list(find_files(CONFIG_AUDIO_BASE_DIR)))


@method(name='search')
async def jsonrpc_search(context, query) -> Result:
    files = list(find_files(CONFIG_AUDIO_BASE_DIR))

    files = [f for f in files if query in f]

    return Success(files)


@method(name='play')
async def jsonrpc_play(context, channelid, query) -> Result:
    bot = context.app['bot']

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams('Channel not found')

    guild = channel.guild

    audio_player = bot.get_cog('Audio Player')

    try:
        await audio_player.rpc_ensure_voice(guild, channel)
        await audio_player.rpc_play(guild, query)
    except commands.CommandError as e:
        return JsonRpcError(1, str(e))

    return Success('Playback successful')


@method(name='message')
async def jsonrpc_message(context, channelid, content) -> Result:
    bot = context.app['bot']

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams('Channel not found')

    await channel.send(content=content)

    return Success('Playback successful')


async def http_handle_rpc(request):
    return web.Response(
        text=await async_dispatch(await request.text(), context=request),
        content_type='application/json',
        headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type'}
    )

async def http_handle_rpc_options(request):
    return web.Response(
        headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type'}
    )

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # discord.utils.setup_logging()

    app = web.Application()
    app.cleanup_ctx.append(start_bot)
    app.router.add_get('/', http_hello)
    app.router.add_post('/rpc', http_handle_rpc)
    app.router.add_options('/rpc', http_handle_rpc_options)
    app.router.add_static('/soundboard', BOT_BASE_DIR / 'web')
    web.run_app(app, port=28914)

# https://discord.com/api/oauth2/authorize?client_id=1085103559244251179&permissions=2048&scope=bot
