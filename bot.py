import asyncio
import logging
from pathlib import Path

import nextcord
from nextcord.ext import commands

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
    JsonRpcError,
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


BOT_BASE_DIR = Path(__file__).parent.resolve()

_log = logging.getLogger(__name__)


# It seems there is a bug with aiodns / pycares that sometimes makes DNS queries
# never return, not even when the timeout is reached.
# https://github.com/aio-libs/aiodns/issues/122
# https://github.com/saghul/pycares/issues/197
aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver


class MyBot(commands.Bot):
    async def on_ready(self):
        _log.info(f"We have logged in as {self.user} (ID: {self.user.id})")
        await self.sync_all_application_commands()

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
async def jsonrpc_play(context, channelid, query) -> Result:
    bot = context.app["bot"]

    channel = bot.get_channel(int(channelid))
    if not channel:
        return InvalidParams("Channel not found")

    guild = channel.guild

    audio_player = bot.get_cog("Audio Player")

    try:
        await audio_player.rpc_ensure_voice(guild, channel)
        await audio_player.rpc_play(guild, query)
    except commands.CommandError as e:
        return JsonRpcError(1, str(e))

    return Success("Playback successful")


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
    intents = nextcord.Intents.default()
    intents.message_content = True

    bot = MyBot(
        command_prefix=commands.when_mentioned_or("!"),
        description="ObstNudler",
        intents=intents,
    )

    bot.add_cog(AudioPlayer(bot))
    bot.add_cog(Controller(bot))
    bot.add_cog(RegelnDesErwerbs(bot))
    bot.add_cog(LLM(bot))
    bot.add_cog(TextToImage(bot))
    bot.add_cog(MagischeKugel(bot))
    bot.add_cog(Bloedsinn(bot))
    bot.add_cog(Statistics(bot))

    asyncio.create_task(start_webserver(bot))

    await bot.start(CONFIG_DISCORD_TOKEN)


async def main():
    # logging.basicConfig(level=logging.INFO)
    logging.basicConfig(level=logging.DEBUG)

    await start_discord_bot()


if __name__ == "__main__":
    asyncio.run(main())

# https://discord.com/api/oauth2/authorize?client_id=1085103559244251179&permissions=2048&scope=bot
