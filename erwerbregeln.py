import random
import discord
from discord.ext import commands

# fmt: off

REGELN_DES_ERWERBS = [
    (0, "Wenn keine passende Regel vorhanden ist, dann erfinde eine!"),  # Sonderregel
    (1, "Geld und Gold das mag ich sehr, und hab ich es erst von andern geb ich es nicht mehr her."),
    (3, "Gib niemals mehr für einen Erwerb aus, als es unbedingt sein muss."),
    (6, "Gestatte niemals, dass Verwandte einer günstigen Gelegenheit im Wege stehen."),
    (None, "Erlaube nie, dass deine Verwandten einem Profit im Wege stehen."),
    (7, "Halte Deine Ohren offen."),
    (8, "Kleingedrucktes birgt großes Risiko."),
    (9, "Gelegenheit plus Instinkt gleich Profit."),
    (10, "Gier ist unendlich."),
    (16, "Ein Geschäft ist ein Geschäft … bis ein besseres daherkommt."),
    (17, "Ein Vertrag ist ein Vertrag ist ein Vertrag … aber nur zwischen Ferengis."),
    (18, "Ein Ferengi ohne Profit ist kein Ferengi."),
    (21, "Niemals Freundschaft über Profit stellen."),
    (22, "Ein weiser Mann hört den Profit aus dem Wind."),
    (23, "Nichts ist wichtiger als deine Gesundheit – außer dein Vermögen."),
    (31, "Mach niemals Witze über eine Ferengimutter."),
    (33, "Es ist nie verkehrt, sich bei seinem Boss einzuschmeicheln."),
    (34, "Krieg ist gut für das Geschäft."),
    (35, "Frieden ist gut für das Geschäft."),
    (45, "Wer nicht expandiert ist tot."),
    (47, "Vertraue keinem, der einen besseren Anzug trägt als Du. Entweder hat er dann kein Geld, oder man hat es mit einem Hochstapler zu tun."),
    (48, "Je breiter jemand lacht, desto schärfer ist sein Messer."),
    (49, "Weibliche und Finanzen lassen sich einfach nicht vereinbaren."),
    (57, "Gute Konsumenten sind fast so rar wie Latinum. Ehre sie."),
    (59, "Frage immer erst nach dem Kostenpunkt."),
    (62, "Je riskanter der Weg, desto größer der Profit."),
    (74, "Wissen ist gleich Profit."),
    (75, "Die Heimat ist, wo das Herz ist, aber die Sterne bestehen aus Latinum."),
    (76, "Du musst für eine Weile sagen, ich brauche Frieden. Deine Feinde sind dadurch völlig verwirrt."),
    (91, "Der Boss ist nur so viel wert, wie er einem zahlt."),
    (94, "Frauen und Finanzen vertragen sich nicht."),
    (95, "Expandiere oder verrecke."),
    (98, "Jeder Mann hat seinen Preis."),
    (102, "Die Natur ist vergänglich, aber Latinum wird immer bestehen."),
    (103, "Schlaf kann verhindern, dass Profit gemacht wird."),
    (109, "Stolz und Armut ist Armut."),
    (111, "Sieh in Gläubigern einen Teil der Familie und beute sie aus."),
    (None, "Behandle Leute, die in Deiner Schuld stehen, wie Familienangehörige – beute sie aus."),
    (112, "Schlafe niemals mit der Schwester deines Chefs."),
    (125, "Wenn Du tot bist, dann machst Du keine Geschäfte."),
    (139, "Frauen arbeiten, Brüder sind Erben."),
    (168, "Flüstere Dich zum Erfolg."),
    (190, "Höre alles, glaube nichts."),
    (194, "Gute Geschäfte macht man nur, wenn man über seine Kundschaft vorher bescheid weiß."),
    (203, "Neue Kunden sind wie Gree-Würmer mit rasierklingenscharfen Zähnen. Sie können sehr saftig sein, aber manchmal beißen sie auch zurück."),
    (208, "Manchmal ist das einzige, was gefährlicher als eine Frage ist, eine Antwort."),
    (211, "Angestellte sind die Sprossen auf der Leiter zum Erfolg – zögere nicht auf sie zu trampeln."),
    (214, "Bevor Du nichts gegessen hast, führe keine geschäftlichen Verhandlungen."),
    (217, "Hole keinen Fisch aus seinem Wasser."),
    (None, "Man kann einen Fisch nicht aus dem Wasser befreien."),
    (229, "Latinum hält länger als Wollust."),
    (239, "Hab' keine Angst davor, ein Produkt falsch zu etikettieren."),
    (263, "Lass niemals Zweifel Deine Lust nach Latinum trüben."),
    (285, "Einer guten Tat folgt die Strafe auf dem Fuße."),
    (None, "Keine gute Tat bleibt ungestraft."),
    (289, "Erst schießen, dann den Profit ausrechnen."),
    (None, "Ausbeutung beginnt in den eigenen vier Wänden."),
    (299, "Wenn du jemanden ausgebeutet hast, dann lohnt es, sich zu bedanken. So ist es einfacher, denjenigen nochmals auszubeuten."), # Sonderregel
]

# fmt: on


class RegelnDesErwerbs(commands.Cog, name="Regeln des Erwerbs"):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="erwerbsregel",
        description="Regeln des Erwerbs",
    )
    async def erwerbsregel(self, ctx: discord.ApplicationContext, nummer: int = -1, text: str = None):
        if text:
            regel = (nummer, text)
        else:
            if nummer >= 0:
                regel = next((r for r in REGELN_DES_ERWERBS if r[0] == nummer), None)
            else:
                regel = random.choice(REGELN_DES_ERWERBS)

        if not regel:
            await ctx.interaction.response.send_message(f"Regel des Erwerbs #0815: PEBCAK")
            return

        if regel[0] is not None:
            await ctx.interaction.response.send_message(f"Regel des Erwerbs #{regel[0]}: {regel[1]}")
        else:
            await ctx.interaction.response.send_message(f"Regel des Erwerbs: {regel[1]}")
