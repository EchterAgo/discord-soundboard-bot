import random
from discord.ext import commands

class MagischeKugel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.responses = [
            "Ja.", 
            "Nein.",
            "Vielleicht.",
            "Frag später noch einmal.",
            "Bestimmt!",
            "Darauf kannst du zählen.",
            "Ich weiß es nicht.",
            "Sehr unwahrscheinlich.",
            "Sicher!",
            "Nicht in deiner wildesten Fantasie.",
            "Es sieht gut aus.",
            "Es sieht nicht gut aus.",
            "Ich würde nicht darauf wetten.",
            "Zweifelhaft.",
        ]

    @commands.slash_command(name="magischekugel", help="Stelle der Magischen Kugel eine Frage.")
    async def magischekugel(self, ctx, *, frage: str):
        response = random.choice(self.responses)
        await ctx.interaction.response.send_message(f"🔮 Frage: {frage}\nAntwort: {response}")
