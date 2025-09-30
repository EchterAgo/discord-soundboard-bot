import asyncio
import io
import logging
from pathlib import Path
import random
import nextcord
from nextcord.ext import commands, tasks
import matplotlib.pyplot as plt
from llm import talk_to_gpt


_log = logging.getLogger(__name__)


class Bloedsinn(commands.Cog, name="Blödsinn"):
    img_path: Path = None

    def __init__(self, bot):
        self.img_path = Path(__file__).resolve().parent / "images"
        self.bot = bot

    @nextcord.slash_command(
        name="hammerzeit",
        description="Hammerzeit!",
    )
    async def hammerzeit(self, interaction: nextcord.Interaction):
        image_file = nextcord.File(self.img_path / "hammerzeit.png")
        await interaction.response.send_message("**HALT, HAMMERZEIT!**", file=image_file)

    @nextcord.slash_command(name="gembo", description="Gembo!")
    async def gembo(self, interaction: nextcord.Interaction, straub_fudge: float = 1.0):
        started_message = await interaction.response.send_message("Gembo wird berechnet, bitte warten...")

        min_value = 1
        max_value = 999999999

        ratio_names = [
            "Gembe-Straub-Korrelation",
            "Straub-Gembe-Kohärenz",
            "Gembe-Straub-Dynamik",
            "Gembische Straub-Konstante",
            "Straub-Gembe-Modulus",
            "Gembe-Straub-Quotient",
            "Straub'sche Gembe-Resonanz",
            "Gembisch-Straub'sches Axiom",
            "Straub-Gembe-Paradigma",
            "Gembe-Straub'sche Fluxion",
            "Straub-Gembe-Gradient",
            "Gembe-Straub-Schwingungsspektrum",
            "Straub-Gembe-Dissipationsfaktor",
            "Gembe-Straub-Anomalie",
            "Straub-Gembe'sches Prinzip der Ausgleichung",
            "Gembe-Straub-Tensor",
            "Straub-Gembisches Oszillationsverhältnis",
            "Gembe-Straub'sches Relativitätsgesetz",
            "Straub-Gembe-Differential",
            "Gembe-Straub'sche Kompatibilitätsregel",
            "Gembe-Straubulation",
        ]

        ratio_name = random.choice(ratio_names)

        gembe = random.randint(min_value, max_value)
        straub = random.randint(min_value, max_value)
        # straub = random.randint(min_value, random.randint(min_value, max_value))
        straub = int(straub * straub_fudge)

        # plt.hist([gembe, straub], range=(min_value, max_value), bins=100)
        # plt.title("Histogram")
        # plt.xlabel("Value")
        # plt.ylabel("Frequency")

        plt.ylim(min_value, max_value)
        plt.bar(["Straub", "Gembe"], [straub, gembe], color=["blue", "green"])
        plt.title(ratio_name)

        plot_buffer = io.BytesIO()
        plt.savefig(plot_buffer, format="png")
        plt.close()
        plot_buffer.seek(0)

        discord_plot_file = nextcord.File(fp=plot_buffer, filename="gembo.png")

        await started_message.edit(
            content=f"Gembe = {gembe}\n Straub = {straub}\n Wurde der Gembe zum Straub gemacht? {gembe  == straub}\n"
            f"Ist der Straub größer als der Gembe? {straub > gembe}\n"
            f"{ratio_name} ist bei {(straub / gembe) * 100.0:.2f}%",
            file=discord_plot_file,
        )

        # await started_message.delete_original_response()
        # await ctx.send(
        #     f"Gembe = {gembe}\n Straub = {straub}\n Wurde der Gembe zum Straub gemacht? {gembe  == straub}\n"
        #     f"Ist der Straub größer als der Gembe? {straub > gembe}\n"
        #     f"{ratio_name} ist bei {(straub / gembe) * 100.0:.2f}%",
        #     file=discord_plot_file
        # )

    @nextcord.slash_command(name="gog", description="GoG!")
    async def gog(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(" ".join([f"g{'o' * random.randint(10, 30)}g" for i in range(0, random.randint(1, 6))]))

    @nextcord.slash_command(description="Der Weg")
    async def weg(self, interaction: nextcord.Interaction):
        image_file_names = [
            "weg1.jpg",
            "weg2.jpg",
            "weg3.jpg",
            "weg4.jpg",
            "weg5.jpg",
            "weg6.jpg",
            "weg7.jpg",
            "weg8.jpg",
            "weg9.jpg",
            "weg10.jpg",
        ]

        image_file = nextcord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Das ist der Weg!!!!!111einseinseins", file=image_file)

    @nextcord.slash_command(description="Der falsche Weg")
    async def fweg(self, interaction: nextcord.Interaction):
        image_file_names = [
            "falscherweg1.jpg",
            "falscherweg2.jpg",
            "falscherweg3.jpg",
            "falscherweg4.jpg",
            "falscherweg5.jpg",
            "falscherweg6.jpg",
        ]

        image_file = nextcord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Das ist nicht der Weg!!!!!111einseinseins", file=image_file)

    @nextcord.slash_command(description="Schluss mit Lustig")
    async def lustig(self, interaction: nextcord.Interaction):
        image_file_names = [
            "lustig1.webp",
            "lustig2.png",
            "lustig3.jpg",
        ]

        image_file = nextcord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Schluss mit Lustig!", file=image_file)

    @nextcord.slash_command(description="Passworttest", guild_ids=[1033659963580633088])
    async def passworttest(self, interaction: nextcord.Interaction, passwort: str):
        await interaction.response.send_message(f"Ist \"{passwort}\" ein gutes Passwort? Nein, du hast es in Discord gepostet!!11eins")

    @nextcord.slash_command(description="Straubenstraub", guild_ids=[1033659963580633088])
    async def straubenstraub(self, interaction: nextcord.Interaction, add_inst: str = None):
        started_message = await interaction.response.send_message("Straubenstraub wird erstellt, bitte warten...")

        async def task_func():
            try:
                prompt_parts = [
                    'Generiere einen Satz in dem möglichst oft der Text "Straub" vorkommt.',
                    "Erfinde viele Straubwörter wie Straubizität oder Straubonanz." "Maximal ein bis drei Sätze.",
                    "Verwende viele Worte die auf Straub reimen.",
                    # "Verwende selten Worte wie Straubulation, Straubillieren, Straubonometrie, Straubizität, Hyperstraubfeld, Straubonanz, Straubismus, Straubologie, Straubionik, Straubomorphie, Straubografie, Straubotronik.",
                ]

                if add_inst:
                    prompt_parts.append(add_inst)

                prompt_parts.append("Beispiele:")
                prompt_parts.append("* Der Straub straubte sträublich am straubigen Morgen im Straub am Straubtag")
                prompt_parts.append("* Die seine sträubliche Straubigkeit Straub der Erste, Strauber des Straubtums")
                prompt_parts.append("* Probleme sind nur straubige Chancen")

                prompt = "\n".join(prompt_parts)

                _log.info(f"Requested prompt is {len(prompt)} bytes")

                response = await talk_to_gpt(prompt=prompt, model="nousresearch/hermes-3-llama-3.1-405b")
                # response = await talk_to_gpt(prompt=prompt, model="google/gemini-flash-1.5")
                # response = await talk_to_gpt(prompt=prompt, model="chatgpt-4o-latest")

                response_text = response.text
                if not response_text:
                    response_text = "**ERROR**: No response generated by Nano-GPT"

                await started_message.edit(content=response_text)
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await started_message.edit(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())
        # task = tasks.loop(seconds=0, count=1)(task_func)
        # task.start(ctx)
