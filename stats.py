from datetime import datetime, timedelta
import time
import discord
from discord.ext import commands


class Statistics(commands.Cog, name="Statistiken"):
    start_time: datetime
    
    def __init__(self, bot):
        self.start_time = datetime.now()
        self.bot = bot

    @commands.slash_command(
        name="uptime",
        description="Uptime!",
    )
    async def uptime(self, ctx: discord.ApplicationContext):
        elapsed = datetime.now() - self.start_time
        await ctx.respond(f"Bot Uptime: {elapsed}")
