from datetime import datetime, timedelta
import time
import discord
from discord import app_commands
from discord.ext import commands


class Statistics(commands.Cog):
    start_time: datetime

    @staticmethod
    def _now_no_us() -> datetime:
        return datetime.now().replace(microsecond=0)

    def __init__(self, bot):
        self.start_time = self._now_no_us()
        self.bot = bot

    @app_commands.command(
        name="uptime",
        description="Uptime!",
    )
    @app_commands.describe(fudge_hours="Fudge hours", fudge_days="Fudge days")
    async def uptime(self, interaction: discord.Interaction, fudge_hours: int = 0, fudge_days: int = 0):
        elapsed = self._now_no_us() - self.start_time

        if fudge_days > 0:
            elapsed = elapsed + timedelta(days=fudge_days)

        if fudge_hours > 0:
            elapsed = elapsed + timedelta(hours=fudge_hours)

        await interaction.response.send_message(f"Bot Uptime: {elapsed}")
