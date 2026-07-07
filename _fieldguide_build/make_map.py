# -*- coding: utf-8 -*-
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

ink = '#2c1f0e'
gold = '#b09060'
accent = '#8b3a1a'
parchment = '#f2e8d5'

legends = [
    ("Barghest", 54.284, -0.404),
    ("Beast of Dean", 51.787, -2.554),
    ("Black Dog of Bouley Bay", 49.255, -2.08),
    ("Black Shuck", 52.731, 1.286),
    ("Church Grim", 51.752, -1.258),
    ("Dando's Dogs", 50.337, -4.632),
    ("Dead Men of Burton-on-Trent", 52.8019, -1.6441),
    ("Gwyllgi", 53.147, -3.241),
    ("Jan Tregeagle", 50.5697, -4.5899),
    ("La Bete De La Tour", 49.47, -2.55),
    ("Lady Howard of Okehampton", 50.738, -4.003),
    ("Macphie / Black Dog of Colonsay", 56.0739, -6.1967),
    ("Moddey Dhoo", 54.225, -4.697),
    ("Old Cockern", 50.583, -3.919),
    ("Padfoot", 53.8, -1.55),
    ("Phantom Hare of Bolingbroke", 53.134, -0.018),
    ("Shug Monkey", 52.1441, 0.3333),
    ("Skriker", 53.79, -2.4),
    ("Stratford Lion", 52.192, -1.708),
    ("Tchico", 49.46, -2.54),
    ("Black Dog of Newgate", 51.5157, -0.1019),
    ("Dragon of Loschy Hill", 54.204, -0.957),
    ("Girt Dog of Ennerdale", 54.522, -3.378),
    ("The Wild Hunt", 53.96, -1.086),
    ("Tyrell's Hound", 50.876, -1.625),
    ("Windhouse", 60.5987, -1.0764),
    ("Crodh Mara", 57.78, -7.02),
    ("Cu Sith", 57.4, -6.25),
]

fig, ax = plt.subplots(figsize=(6.6, 8.4), dpi=200)
fig.patch.set_facecolor(parchment)
ax.set_facecolor(parchment)

lats = [l[1] for l in legends]
lngs = [l[2] for l in legends]
ax.scatter(lngs, lats, s=90, color=accent, edgecolor=ink, linewidth=0.8, zorder=3, alpha=0.88)

for name, lat, lng in legends:
    pass  # names shown in a table elsewhere, keep the map clean

ax.set_xlim(-8.8, 2.2)
ax.set_ylim(49.0, 61.2)
ax.set_aspect(1.65)
for spine in ax.spines.values():
    spine.set_edgecolor(gold)
    spine.set_linewidth(1.4)
ax.set_xticks([])
ax.set_yticks([])

# Soft border frame
ax.text(0.02, 0.985, 'N', transform=ax.transAxes, fontsize=13, color=ink, fontweight='bold', va='top')
ax.annotate('', xy=(0.03, 0.975), xytext=(0.03, 0.92), xycoords='axes fraction',
            arrowprops=dict(arrowstyle='-|>', color=ink, lw=1.4))

plt.tight_layout(pad=1.2)
plt.savefig('distribution_map.png', facecolor=parchment, bbox_inches='tight')
print("saved", len(legends), "points")
