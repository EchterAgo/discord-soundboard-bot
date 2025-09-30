import random
import nextcord
from nextcord.ext import commands


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

    @nextcord.slash_command(name="magischekugel", description="Stelle der Magischen Kugel eine Frage.")
    async def magischekugel(self, interaction: nextcord.Interaction, frage: str):
        response = random.choice(self.responses)
        await interaction.response.send_message(f"🔮 Frage: {frage}\nAntwort: {response}")
