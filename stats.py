from datetime import datetime, timedelta
import time
import nextcord
from nextcord.ext import commands


class Statistics(commands.Cog, name="Statistiken"):
    start_time: datetime

    @staticmethod
    def _now_no_us() -> datetime:
        return datetime.now().replace(microsecond=0)

    def __init__(self, bot):
        self.start_time = self._now_no_us()
        self.bot = bot

    @nextcord.slash_command(
        name="uptime",
        description="Uptime!",
    )
    async def uptime(self, interaction: nextcord.Interaction, fudge_hours: int = 0, fudge_days: int = 0):
        elapsed = self._now_no_us() - self.start_time

        if fudge_days > 0:
            elapsed = elapsed + timedelta(days=fudge_days)

        if fudge_hours > 0:
            elapsed = elapsed + timedelta(hours=fudge_hours)

        await interaction.response.send_message(f"Bot Uptime: {elapsed}")
