from discord.ext import commands
import requests


class Controller(commands.Cog, name="Controller"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def set_avatar(self, ctx, url):
        img = requests.get(url).content
        await self.bot.user.edit(avatar=img)

    @commands.command()
    async def set_name(self, ctx, name):
        await self.bot.user.edit(username=name)
