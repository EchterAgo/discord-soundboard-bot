import argparse
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

from jsonrpcserver import async_dispatch

from config import CONFIG_DISCORD_TOKEN
from erwerbregeln import RegelnDesErwerbs
from audioplayer import AudioPlayer
from controller import Controller
from llm import LLM
from text2image import TextToImage
from magischekugel import MagischeKugel
from bloedsinn import Bloedsinn
from stats import Statistics

# Import RPC methods (this registers them with jsonrpcserver)
import rpc_server  # noqa: F401


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


async def http_soundboard_index(request):
    """Serve index.html at /soundboard/"""
    index_path = BOT_BASE_DIR / "web" / "index.html"
    return aiohttp.web.FileResponse(index_path)


async def http_soundboard_index_redirect(request):
    """Redirect /soundboard/index.html to /soundboard/"""
    raise aiohttp.web.HTTPFound("/soundboard/")


async def start_webserver(bot: commands.Bot):
    app = aiohttp.web.Application()

    app["bot"] = bot  # to get the bot in handlers

    app.router.add_get("/", http_hello)
    app.router.add_post("/rpc", http_handle_rpc)
    app.router.add_options("/rpc", http_handle_rpc_options)
    app.router.add_get("/ws", rpc_server.handle_websocket)  # WebSocket endpoint
    app.router.add_get("/soundboard", http_soundboard_index)
    app.router.add_get("/soundboard/", http_soundboard_index)
    app.router.add_get("/soundboard/index.html", http_soundboard_index_redirect)
    app.router.add_get("/soundboard/index-vue.html", http_soundboard_index_redirect)
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
    
    # Set up queue update callback for WebSocket broadcasts
    audio_player = bot.get_cog("AudioPlayer")
    if audio_player:
        # Define the callback that broadcasts to all WebSocket clients
        async def queue_update_callback():
            # Use the default Discord voice channel for soundboard
            await rpc_server.broadcast_queue_update(bot, '1033659964457230392')
        
        audio_player.queue_update_callback = queue_update_callback

    # Start file watcher for audio directory changes
    loop = asyncio.get_event_loop()
    rpc_server.start_file_watcher(loop)

    asyncio.create_task(start_webserver(bot))

    if not CONFIG_DISCORD_TOKEN:
        raise ValueError("CONFIG_DISCORD_TOKEN must be set and cannot be None")

    await bot.start(CONFIG_DISCORD_TOKEN)


async def main(args):
    # Set logging level based on verbose flag
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    
    # Disable verbose logging for ffmpeg and aiohttp unless verbose is set
    if not args.verbose:
        logging.getLogger('discord.player').setLevel(logging.WARNING)
        logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

    await start_discord_bot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discord Soundboard Bot")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()
    
    asyncio.run(main(args))

# https://discord.com/api/oauth2/authorize?client_id=1085103559244251179&permissions=2048&scope=bot
