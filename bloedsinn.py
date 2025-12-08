import asyncio
import io
import logging
from pathlib import Path
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
from llm import talk_to_gpt


_log = logging.getLogger(__name__)


class Bloedsinn(commands.Cog):
    img_path: Path

    def __init__(self, bot):
        self.img_path = Path(__file__).resolve().parent / "images"
        self.bot = bot

    def _generate_pseudo_scientific_labels(self, seed: int):
        """Generate random pseudo-scientific labels based on seed."""
        random.seed(seed)
        
        # Basis-Komponenten
        prefixes = ["Hyper", "Mega", "Ultra", "Nano", "Piko", "Tera", "Giga", "Meta", "Para", "Quasi", "Proto", "Neo", "Iso", "Homo"]
        suffixes = ["ulation", "ometrie", "ismus", "ität", "onanz", "morphie", "logie", "feld", "welle", "faktor", "index", "spektrum", "gradient", "tensor"]
        
        # Erweitert mit Straub-Döner-Begriffen
        straub_words = ["Straubulation", "Straubillieren", "Straubonometrie", "Straubizität", "Straubonanz", 
                       "Straubismus", "Straubologie", "Straubionik", "Straubomorphie", "Straubografie", "Straubotronik",
                       "Dönerstraub", "Straubdöner", "Dönerstaubulation", "Straubdönigkeit"]
        
        phenomena = [
            "Fluktuations", "Oszillations", "Resonanz", "Interferenz", "Kohärenz", 
            "Dispersions", "Diffusions", "Emissions", "Absorptions", "Reflexions",
            "Polarisations", "Quanten", "Plasma", "Neutrino", "Photonen",
            "Elektron", "Hadron", "Boson", "Fermion", "Graviton",
            "Döner", "Straubdöner", "Dönerwelle"
        ]
        
        qualifiers = [
            "inkohärent", "stochastisch", "deterministisch", "chaotisch", "harmonisch",
            "anisotrop", "isomorph", "orthogonal", "parallel", "antiparallel",
            "linear", "exponentiell", "logarithmisch", "periodisch", "aperiodisch",
            "sträublich", "straubig", "dönerhaft", "sträublich straub"
        ]
        
        units = [
            "StraubHz", "GembeVolt", "MegaŞtraub", "NanoĞembe", "Straubulonen",
            "Gembonen", "StraubWatt", "GemboJoule", "Ş/Ğ²", "StraubTesla",
            "GembeKelvin", "StraubNewton", "Gembometer", "StraubPascal",
            "Döner/Ş²", "StraubDöner", "DönerHz"
        ]
        
        # Generiere Labels - manchmal mit Straub-Wörtern
        if random.random() > 0.5:
            axis_label = random.choice(straub_words)
        else:
            axis_label = f"{random.choice(prefixes)}{random.choice(['Straub', 'Gembe', 'Döner'])}{random.choice(suffixes)}"
        
        phenomenon = f"{random.choice(phenomena)}{random.choice(suffixes)}"
        qualifier = random.choice(qualifiers)
        unit = random.choice(units)
        
        plot_title = f"{random.choice(['Spektrale', 'Temporale', 'Räumliche', 'Dimensionale', 'Topologische', 'Sträubliche'])} {phenomenon}"
        
        return {
            "axis_label": axis_label,
            "phenomenon": phenomenon,
            "qualifier": qualifier,
            "unit": unit,
            "plot_title": plot_title
        }

    @app_commands.command(
        name="hammerzeit",
        description="Hammerzeit!",
    )
    async def hammerzeit(self, interaction: discord.Interaction):
        image_file = discord.File(self.img_path / "hammerzeit.png")
        await interaction.response.send_message("**HALT, HAMMERZEIT!**", file=image_file)

    @app_commands.command(name="gembo", description="Gembo!")
    @app_commands.describe(straub_fudge="Straub fudge factor")
    async def gembo(self, interaction: discord.Interaction, straub_fudge: float = 1.0):
        await interaction.response.send_message("Gembo wird berechnet, bitte warten...")

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

        # Calculate pseudo-scientific metrics
        gembe_norm = gembe / max_value
        straub_norm = straub / max_value
        ratio = (straub / gembe * 100.0) if gembe != 0 else 0
        
        # Harmonic Gembe-Straub Frequency (in StraubHz)
        harmonic_freq = np.sqrt(gembe * straub) / 1000
        
        # Phase coherence angle (in radians)
        phase_coherence = np.arctan2(straub, gembe)
        
        # Straubulation intensity (normalized)
        straubulation_intensity = (gembe_norm + straub_norm) / 2
        
        # Quantum entanglement coefficient
        entanglement = np.exp(-abs(gembe - straub) / max_value) * 100
        
        # Gembe-Straub Wave Interference Pattern
        interference_mode = "konstruktiv" if (gembe + straub) % 2 == 0 else "destruktiv"
        
        # Dimensional stability index
        stability_index = min(gembe, straub) / max(gembe, straub) if max(gembe, straub) > 0 else 1.0
        
        # Hyperstraubfeld energy level (in Megastraub)
        hyperfeld_energy = (gembe ** 0.33 + straub ** 0.33) / 1000
        
        # Straubische Dönermetrik - vereint Straub und Döner in sträublicher Weise
        doener_straub_quotient = (straub % 360) / 3.6  # Drehungen des Döners
        straubigkeit_des_doeners = np.sin(gembe_norm * np.pi) * np.cos(straub_norm * np.pi * 2)
        doener_straubulation = abs(straubigkeit_des_doeners) * doener_straub_quotient
        
        # Sträubliche Dönerdichte (Döner pro Straub²)
        doener_dichte = (gembe % 100) * (straub % 100) / 10000
        
        # Straubomorpher Döner-Index
        straubomorpher_index = (doener_straubulation + doener_dichte) / 2
        
        # Qualitative Bewertung der Straubigkeit
        if straubomorpher_index > 80:
            straubigkeits_kategorie = "sträublich straub"
        elif straubomorpher_index > 60:
            straubigkeits_kategorie = "straubig"
        elif straubomorpher_index > 40:
            straubigkeits_kategorie = "mäßig straub"
        elif straubomorpher_index > 20:
            straubigkeits_kategorie = "kaum straub"
        else:
            straubigkeits_kategorie = "unstraub"
        
        # Generate random pseudo-scientific labels
        labels = self._generate_pseudo_scientific_labels(gembe + straub)
        
        # Randomly select 2 additional plot types (bar chart is always first)
        np.random.seed((gembe + straub) % 100000)
        available_plots = [
            'surface3d', 'polar', 'spectrum', 'timeseries', 
            'heatmap', 'scatter3d', 'contour', 'waterfall'
        ]
        additional_plots = np.random.choice(available_plots, size=2, replace=False).tolist()
        selected_plots = ['bar'] + additional_plots  # Bar chart is always first
        
        # Create a comprehensive pseudo-scientific plot grid
        fig = plt.figure(figsize=(20, 11))
        
        # Use GridSpec for better space utilization
        from matplotlib.gridspec import GridSpec
        gs = GridSpec(1, 3, figure=fig, hspace=0.15, wspace=0.25,
                     left=0.05, right=0.98, top=0.93, bottom=0.08)
        
        # Define all possible plot functions
        def create_bar_plot(ax, pos):
            ax.set_ylim(min_value, max_value)
            bars = ax.bar(["Straub", "Gembe"], [straub, gembe], 
                         color=["#4169E1", "#32CD32"], edgecolor='black', linewidth=1.5)
            ax.set_title(f"{ratio_name}\nStabilität: {stability_index:.4f}", 
                        fontsize=12, fontweight='bold', pad=15)
            ax.set_ylabel(f"Magnitude ({labels['unit']})", fontsize=11)
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height):,}', ha='center', va='bottom', fontsize=10, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=1.2)
            ax.axhline(y=harmonic_freq * 1000, color='r', linestyle=':', 
                      alpha=0.7, linewidth=2, label=f'Harmonische Frequenz')
            ax.legend(fontsize=9)
            ax.set_facecolor('#f8f9fa')
        
        def create_surface3d_plot(ax, pos):
            u = np.linspace(0, 2 * np.pi, 70)
            v = np.linspace(0, np.pi, 70)
            U, V = np.meshgrid(u, v)
            X = np.sin(V) * np.cos(U) * (1 + 0.4 * gembe_norm * np.cos(phase_coherence))
            Y = np.sin(V) * np.sin(U) * (1 + 0.4 * straub_norm * np.sin(phase_coherence))
            Z = np.cos(V) * straubulation_intensity + 0.3 * np.sin(U * 3) * stability_index
            Z += np.sin(U * (gembe % 7 + 1)) * np.cos(V * (straub % 5 + 1)) * 0.15
            np.random.seed((gembe + straub) % 1000)
            Z += np.random.normal(0, 0.03 * entanglement / 100, Z.shape)
            cmap_choice = 'plasma' if interference_mode == "konstruktiv" else 'viridis'
            surf = ax.plot_surface(X, Y, Z, cmap=cmap_choice, alpha=0.9, 
                                  antialiased=True, edgecolor='none', shade=True)
            ax.set_xlabel('Gembe (ξ)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Straub (σ)', fontsize=11, fontweight='bold')
            ax.set_zlabel('Ψ-Straubulation', fontsize=11, fontweight='bold')
            ax.set_title(f'{labels["plot_title"]}\n{interference_mode.capitalize()}', 
                        fontsize=12, fontweight='bold', pad=15)
            rotation_angle = (ratio * 3.6) % 360
            elevation = 20 + (phase_coherence / np.pi * 20)
            ax.view_init(elev=elevation, azim=rotation_angle)
            ax.set_facecolor('#f0f0f0')
        
        def create_polar_plot(ax, pos):
            theta = np.linspace(0, 2 * np.pi, 150)
            r = 1 + 0.5 * np.sin((gembe % 13) * theta) * np.cos((straub % 11) * theta)
            r += 0.2 * np.random.random(len(theta))
            ax.plot(theta, r, 'b-', linewidth=2.5, alpha=0.8)
            ax.fill(theta, r, alpha=0.4, color='skyblue')
            ax.scatter([phase_coherence], [straubulation_intensity * 2], 
                      color='red', s=200, marker='*', zorder=5, edgecolors='black', linewidths=2,
                      label='Aktuelle Phase')
            ax.set_title(f'Phasenraum-Topologie\n{labels["qualifier"]}', 
                        fontsize=12, fontweight='bold', pad=20)
            ax.legend(fontsize=9, loc='upper right')
            ax.grid(True, alpha=0.4, linewidth=1.2)
            ax.set_facecolor('#fafafa')
        
        def create_spectrum_plot(ax, pos):
            freqs = np.linspace(0, 100, 250)
            np.random.seed((gembe * straub) % 10000)
            spectrum = np.random.exponential(0.5, len(freqs)) * 0.1
            peak_freq1 = (gembe % 79) + 5
            peak_freq2 = (straub % 73) + 10
            spectrum += 2 * np.exp(-((freqs - peak_freq1) ** 2) / 50)
            spectrum += 1.5 * np.exp(-((freqs - peak_freq2) ** 2) / 30)
            spectrum += 0.5 * np.sin(freqs * 0.5 + gembe_norm * 10)
            ax.plot(freqs, spectrum, 'purple', linewidth=2.5, alpha=0.9)
            ax.fill_between(freqs, spectrum, alpha=0.4, color='purple')
            ax.axvline(x=peak_freq1, color='red', linestyle='--', alpha=0.7, linewidth=2,
                      label=f'Gembe: {peak_freq1:.0f}Hz')
            ax.axvline(x=peak_freq2, color='blue', linestyle='--', alpha=0.7, linewidth=2,
                      label=f'Straub: {peak_freq2:.0f}Hz')
            ax.set_xlabel('Frequenz (StraubHz)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Amplitude', fontsize=11, fontweight='bold')
            ax.set_title(f'Spektrale {labels["phenomenon"]}', fontsize=12, fontweight='bold', pad=15)
            ax.grid(True, alpha=0.3, linestyle=':', linewidth=1.2)
            ax.legend(fontsize=9)
            ax.set_facecolor('#f8f9fa')
        
        def create_timeseries_plot(ax, pos):
            time = np.linspace(0, 10, 600)
            np.random.seed(gembe % 1000)
            signal = (gembe_norm * np.sin(2 * np.pi * (straub % 7 + 1) * time / 10) +
                     straub_norm * np.cos(2 * np.pi * (gembe % 5 + 1) * time / 10))
            signal += 0.3 * np.sin(2 * np.pi * 3 * (gembe % 3 + 1) * time / 10)
            signal += 0.2 * stability_index * np.cos(2 * np.pi * 5 * time / 10)
            envelope = np.exp(-time / (10 * max(stability_index, 0.1)))
            if ratio > 100:
                envelope = 1 - envelope
            signal *= envelope
            ax.plot(time, signal, 'darkgreen', linewidth=2.5, alpha=0.9)
            ax.fill_between(time, signal, alpha=0.3, color='green')
            ax.axhline(y=0, color='black', linestyle='-', linewidth=1, alpha=0.5)
            ax.set_xlabel('Zeit (Straubsekunden)', fontsize=11, fontweight='bold')
            ax.set_ylabel(f'{labels["axis_label"]}', fontsize=11, fontweight='bold')
            ax.set_title(f'Temporale Evolution\n{"Zerfall" if ratio < 100 else "Wachstum"}', 
                        fontsize=12, fontweight='bold', pad=15)
            ax.grid(True, alpha=0.3, linestyle=':', linewidth=1.2)
            ax.set_facecolor('#f8f9fa')
        
        def create_heatmap_plot(ax, pos):
            x_range = np.linspace(-1, 1, 120)
            y_range = np.linspace(-1, 1, 120)
            X_grid, Y_grid = np.meshgrid(x_range, y_range)
            np.random.seed((gembe + straub) % 10000)
            Z_grid = (np.sin((gembe % 11) * np.pi * X_grid) * 
                     np.cos((straub % 13) * np.pi * Y_grid) +
                     0.5 * np.sin((gembe % 7) * np.pi * (X_grid**2 + Y_grid**2)))
            rotation_matrix_angle = doener_straub_quotient * np.pi / 180
            Z_grid += 0.3 * np.sin(rotation_matrix_angle * (X_grid - Y_grid))
            Z_grid *= (1 + straubulation_intensity)
            contour = ax.contourf(X_grid, Y_grid, Z_grid, levels=25, 
                                 cmap='RdYlBu_r', alpha=0.95)
            ax.contour(X_grid, Y_grid, Z_grid, levels=12, 
                      colors='black', linewidths=0.8, alpha=0.4)
            ax.scatter([0], [0], color='red', s=300, marker='*', 
                      label='Zentrum', zorder=5, edgecolors='black', linewidths=2)
            ax.scatter([gembe_norm * 2 - 1], [straub_norm * 2 - 1], 
                      color='yellow', s=200, marker='D', 
                      label='Position', zorder=5, edgecolors='black', linewidths=2)
            ax.set_xlabel('Gembe-Achse', fontsize=11, fontweight='bold')
            ax.set_ylabel('Straub-Achse', fontsize=11, fontweight='bold')
            ax.set_title(f'Döner-Straub Korrelation\nIndex: {straubomorpher_index:.2f}', 
                        fontsize=12, fontweight='bold', pad=15)
            ax.legend(fontsize=9, loc='upper right')
            ax.set_aspect('equal')
        
        def create_scatter3d_plot(ax, pos):
            np.random.seed((gembe + straub) % 10000)
            n_points = 300
            theta = np.random.uniform(0, 2*np.pi, n_points)
            phi = np.random.uniform(0, np.pi, n_points)
            r = np.random.beta(2, 5, n_points) * (gembe_norm + straub_norm)
            x = r * np.sin(phi) * np.cos(theta) * (1 + 0.3 * gembe_norm)
            y = r * np.sin(phi) * np.sin(theta) * (1 + 0.3 * straub_norm)
            z = r * np.cos(phi) * straubulation_intensity
            colors_scatter = r / r.max()
            scatter = ax.scatter(x, y, z, c=colors_scatter, cmap='cool', 
                               s=50, alpha=0.7, edgecolors='black', linewidths=0.5)
            ax.set_xlabel('Gembe (ξ)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Straub (σ)', fontsize=11, fontweight='bold')
            ax.set_zlabel('Straubulation', fontsize=11, fontweight='bold')
            ax.set_title(f'Quanten-Verteilung\n{labels["qualifier"]}', 
                        fontsize=12, fontweight='bold', pad=15)
            ax.view_init(elev=25, azim=(ratio * 2) % 360)
            ax.set_facecolor('#f0f0f0')
        
        def create_contour_plot(ax, pos):
            x = np.linspace(-2, 2, 150)
            y = np.linspace(-2, 2, 150)
            X, Y = np.meshgrid(x, y)
            Z = (np.sin(X * (gembe % 5 + 1)) * np.cos(Y * (straub % 7 + 1)) +
                 0.5 * np.exp(-(X**2 + Y**2) / (2 * max(stability_index, 0.1))))
            levels = np.linspace(Z.min(), Z.max(), 20)
            contour = ax.contour(X, Y, Z, levels=levels, cmap='twilight', linewidths=2)
            ax.clabel(contour, inline=True, fontsize=8, fmt='%.2f')
            ax.contourf(X, Y, Z, levels=levels, cmap='twilight', alpha=0.6)
            ax.set_xlabel('Gembe-Parameter', fontsize=11, fontweight='bold')
            ax.set_ylabel('Straub-Parameter', fontsize=11, fontweight='bold')
            ax.set_title(f'Isolinien-Analyse\n{labels["phenomenon"]}', 
                        fontsize=12, fontweight='bold', pad=15)
            ax.grid(True, alpha=0.3, linewidth=1.2)
            ax.set_facecolor('#fafafa')
        
        def create_waterfall_plot(ax, pos):
            time = np.linspace(0, 10, 100)
            freqs = np.linspace(0, 50, 80)
            T, F = np.meshgrid(time, freqs)
            np.random.seed((gembe + straub) % 10000)
            Z = (np.sin(2 * np.pi * F / (gembe % 20 + 5) * T) * 
                 np.exp(-T / (straub_norm * 5 + 1)) +
                 0.3 * np.random.randn(*T.shape))
            im = ax.imshow(Z, aspect='auto', cmap='inferno', origin='lower',
                          extent=[time.min(), time.max(), freqs.min(), freqs.max()],
                          alpha=0.9)
            ax.set_xlabel('Zeit (s)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Frequenz (Hz)', fontsize=11, fontweight='bold')
            ax.set_title(f'Zeit-Frequenz-Spektrogramm\n{labels["axis_label"]}', 
                        fontsize=12, fontweight='bold', pad=15)
            plt.colorbar(im, ax=ax, label='Intensität', shrink=0.8)
        
        # Map plot names to functions
        plot_functions = {
            'bar': create_bar_plot,
            'surface3d': create_surface3d_plot,
            'polar': create_polar_plot,
            'spectrum': create_spectrum_plot,
            'timeseries': create_timeseries_plot,
            'heatmap': create_heatmap_plot,
            'scatter3d': create_scatter3d_plot,
            'contour': create_contour_plot,
            'waterfall': create_waterfall_plot
        }
        
        # Create the 3 selected plots
        for i, plot_type in enumerate(selected_plots):
            if plot_type in ['surface3d', 'scatter3d']:
                ax = fig.add_subplot(gs[0, i], projection='3d')
            elif plot_type == 'polar':
                ax = fig.add_subplot(gs[0, i], projection='polar')
            else:
                ax = fig.add_subplot(gs[0, i])
            
            plot_functions[plot_type](ax, i)

        plot_buffer = io.BytesIO()
        plt.savefig(plot_buffer, format="png", dpi=120, bbox_inches='tight')
        plt.close()
        plot_buffer.seek(0)

        discord_plot_file = discord.File(fp=plot_buffer, filename="gembo.png")
        
        # Randomly select which metrics to include (seed based on gembe + straub)
        np.random.seed((gembe + straub) % 100000)
        
        # Define optional metric sections
        primary_metrics = [
            f"• {ratio_name}: **{ratio:.2f}%**",
            f"• Harmonische Frequenz: `{harmonic_freq:.2f} {labels['unit']}`",
            f"• Phasen-Kohärenz: `{phase_coherence:.4f} rad` ({np.degrees(phase_coherence):.1f}°)",
            f"• Straubulations-Intensität: `{straubulation_intensity:.4f}` ({labels['qualifier']})",
            f"• Quanten-Verschränkung: `{entanglement:.2f}%`",
            f"• Interferenzmodus: **{interference_mode.upper()}**",
            f"• Dimensionale Stabilität: `{stability_index:.6f}`",
            f"• Hyperstraubfeld-Energie: `{hyperfeld_energy:.2f} MŞ`",
            f"• {labels['axis_label']}: `{(gembe_norm * straub_norm * 1000):.3f}`",
        ]
        
        doener_metrics = [
            f"• Döner-Straub-Quotient: `{doener_straub_quotient:.2f}° Drehungen`",
            f"• Straubigkeit des Döners: `{straubigkeit_des_doeners:.4f}`",
            f"• Döner-Straubulation: `{doener_straubulation:.2f}`",
            f"• Sträubliche Dönerdichte: `{doener_dichte:.2f} Döner/Ş²`",
            f"• Straubomorpher Index: `{straubomorpher_index:.2f}` (**{straubigkeits_kategorie.upper()}**)",
            f"• Bewertung: Der Döner ist *{straubigkeits_kategorie}* am straubigen Morgen",
        ]
        
        spectral_metrics = [
            f"• Gembe-Resonanzpeak: `{(gembe % 79) + 5:.0f} StraubHz`",
            f"• Straub-Resonanzpeak: `{(straub % 73) + 10:.0f} StraubHz`",
            f"• Phasenraum-Topologie: **{labels['qualifier'].upper()}**",
            f"• Zeitliche Dynamik: `{'Exponentieller Zerfall' if ratio < 100 else 'Exponentielles Wachstum'}`",
        ]
        
        # Select random subset of metrics (at least 3, at most 7 from each category)
        selected_primary = np.random.choice(primary_metrics, 
                                           size=np.random.randint(3, min(8, len(primary_metrics)+1)), 
                                           replace=False).tolist()
        
        # Döner section is optional (50% chance)
        include_doener = np.random.random() > 0.5
        selected_doener = []
        if include_doener:
            selected_doener = np.random.choice(doener_metrics,
                                              size=np.random.randint(2, len(doener_metrics)+1),
                                              replace=False).tolist()
        
        # Spectral section is optional (60% chance)
        include_spectral = np.random.random() > 0.4
        selected_spectral = []
        if include_spectral:
            selected_spectral = np.random.choice(spectral_metrics,
                                                 size=np.random.randint(2, len(spectral_metrics)+1),
                                                 replace=False).tolist()
        
        # Build the report dynamically
        scientific_report = (
            f"**═══ GEMBE-STRAUB QUANTENANALYSE ═══**\n"
            f"```\n"
            f"Gembe (Ğ):            {gembe:,}\n"
            f"Straub (Ş):           {straub:,}\n"
            f"Detektiertes Phänomen: {labels['phenomenon']}\n"
            f"```\n"
            f"**Primäre Metriken:**\n"
            f"{chr(10).join(selected_primary)}\n\n"
        )
        
        # Add optional Döner section
        if include_doener and selected_doener:
            scientific_report += (
                f"**Straubische Dönermetrik:**\n"
                f"{chr(10).join(selected_doener)}\n\n"
            )
        
        # Add optional Spectral section
        if include_spectral and selected_spectral:
            scientific_report += (
                f"**Spektrale Analyse:**\n"
                f"{chr(10).join(selected_spectral)}\n\n"
            )
        
        # Always include critical conditions
        scientific_report += (
            f"**Kritische Bedingungen:**\n"
            f"• Gembe→Straub Transformation: `{'JA ⚠️' if gembe == straub else 'NEIN ✓'}`\n"
            f"• Straub-Dominanz: `{'JA 📈' if straub > gembe else 'NEIN 📉'}`\n"
            f"• Resonanz-Schwellwert: `{'ERREICHT 🔔' if ratio > 95 and ratio < 105 else 'nicht erreicht'}`\n"
        )
        
        # Optional: Add Strauber status if Döner metrics were included
        if include_doener:
            scientific_report += f"• Strauber des Straubtums: `{'Erreicht 👑' if straubomorpher_index > 75 else 'In Arbeit 🔨'}`\n"

        await interaction.edit_original_response(
            content=scientific_report,
            attachments=[discord_plot_file],
        )

        # await started_message.delete_original_response()
        # await ctx.send(
        #     f"Gembe = {gembe}\n Straub = {straub}\n Wurde der Gembe zum Straub gemacht? {gembe  == straub}\n"
        #     f"Ist der Straub größer als der Gembe? {straub > gembe}\n"
        #     f"{ratio_name} ist bei {(straub / gembe) * 100.0:.2f}%",
        #     file=discord_plot_file
        # )

    @app_commands.command(name="gog", description="GoG!")
    async def gog(self, interaction: discord.Interaction):
        await interaction.response.send_message(" ".join([f"g{'o' * random.randint(10, 30)}g" for i in range(0, random.randint(1, 6))]))

    @app_commands.command(name="weg", description="Der Weg")
    async def weg(self, interaction: discord.Interaction):
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

        image_file = discord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Das ist der Weg!!!!!111einseinseins", file=image_file)

    @app_commands.command(name="fweg", description="Der falsche Weg")
    async def fweg(self, interaction: discord.Interaction):
        image_file_names = [
            "falscherweg1.jpg",
            "falscherweg2.jpg",
            "falscherweg3.jpg",
            "falscherweg4.jpg",
            "falscherweg5.jpg",
            "falscherweg6.jpg",
        ]

        image_file = discord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Das ist nicht der Weg!!!!!111einseinseins", file=image_file)

    @app_commands.command(name="lustig", description="Schluss mit Lustig")
    async def lustig(self, interaction: discord.Interaction):
        image_file_names = [
            "lustig1.webp",
            "lustig2.png",
            "lustig3.jpg",
        ]

        image_file = discord.File(self.img_path / random.choice(image_file_names))
        await interaction.response.send_message(f"Schluss mit Lustig!", file=image_file)

    @app_commands.command(name="passworttest", description="Passworttest")
    @app_commands.describe(passwort="Dein Passwort")
    @app_commands.guilds(1033659963580633088)
    async def passworttest(self, interaction: discord.Interaction, passwort: str):
        await interaction.response.send_message(f'Ist "{passwort}" ein gutes Passwort? Nein, du hast es in Discord gepostet!!11eins')

    @app_commands.command(name="straubenstraub", description="Straubenstraub")
    @app_commands.describe(add_inst="Additional instructions (optional)")
    @app_commands.guilds(1033659963580633088)
    async def straubenstraub(self, interaction: discord.Interaction, add_inst: str = ""):
        await interaction.response.send_message("Straubenstraub wird erstellt, bitte warten...")

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

                await interaction.edit_original_response(content=response_text)
            except Exception as e:
                _log.error("An unexpected error occurred", exc_info=True)
                await interaction.edit_original_response(content=f"**ERROR**: {e}")

        asyncio.create_task(task_func())
        # task = tasks.loop(seconds=0, count=1)(task_func)
        # task.start(ctx)
