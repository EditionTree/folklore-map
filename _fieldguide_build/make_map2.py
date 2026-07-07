# -*- coding: utf-8 -*-
import re, random
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Polygon

ink = '#2c1f0e'
gold = '#b09060'
accent = '#8b3a1a'
accent_warm = '#c4622a'
parchment = '#f2e8d5'
land = '#e8dcc5'

svg = open('../region-map.svg', encoding='utf-8').read()
region_paths = dict(re.findall(r'id="region-([a-z-]+)" d="([^"]+)"', svg))

def parse_subpaths(d):
    """Split an SVG M/L/Z-only path into a list of closed point-lists."""
    subpaths = []
    for chunk in d.split('M')[1:]:
        chunk = chunk.rstrip('Z')
        nums = re.findall(r'-?\d+\.?\d*', chunk)
        pts = [(float(nums[i]), 500 - float(nums[i+1])) for i in range(0, len(nums) - 1, 2)]
        if len(pts) >= 3:
            subpaths.append(pts)
    return subpaths

region_polys = {name: parse_subpaths(d) for name, d in region_paths.items()}

fig, ax = plt.subplots(figsize=(6.6, 8.2), dpi=200)
fig.patch.set_facecolor(parchment)
ax.set_facecolor(parchment)

for name, subpaths in region_polys.items():
    for pts in subpaths:
        poly = Polygon(pts, closed=True, facecolor=land, edgecolor='#a88c61', linewidth=1.0, zorder=1)
        ax.add_patch(poly)

def biggest_subpath(name):
    return max(region_polys[name], key=len)

def point_in_region(name, rng, tries=200):
    """Rejection-sample a point inside the region's largest subpath's bbox."""
    pts = biggest_subpath(name)
    path = MplPath(pts)
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    for _ in range(tries):
        x = rng.uniform(min(xs), max(xs))
        y = rng.uniform(min(ys), max(ys))
        if path.contains_point((x, y)):
            return x, y
    cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
    return cx, cy

# name -> approximate nation region (of the 5 in region-map.svg); Channel
# Islands legends are placed by hand south of England (no shape for them).
legend_regions = {
    "Barghest": "england", "Beast of Dean": "england", "Black Shuck": "england",
    "Church Grim": "england", "Dando's Dogs": "england",
    "Dead Men of Burton-on-Trent": "england", "Jan Tregeagle": "england",
    "Lady Howard of Okehampton": "england", "Old Cockern": "england",
    "Padfoot": "england", "Phantom Hare of Bolingbroke": "england",
    "Shug Monkey": "england", "Skriker": "england", "Stratford Lion": "england",
    "Black Dog of Newgate": "england", "Dragon of Loschy Hill": "england",
    "Girt Dog of Ennerdale": "england", "The Wild Hunt": "england",
    "Tyrell's Hound": "england",
    "Gwyllgi": "wales",
    "Macphie / Black Dog of Colonsay": "scotland", "Windhouse": "scotland",
    "Crodh Mara": "scotland", "Cu Sith": "scotland",
}
channel_islands = ["Black Dog of Bouley Bay", "La Bete De La Tour", "Tchico"]

rng = random.Random(42)
placed = []
for name in legend_regions:
    x, y = point_in_region(legend_regions[name], rng)
    placed.append((name, x, y))

# Channel Islands: hand-placed just south of England's southern coast.
ci_spots = [(300, 8), (312, 14), (306, 4)]
for name, (x, y) in zip(channel_islands, ci_spots):
    placed.append((name, x, y))

xs = [p[1] for p in placed]
ys = [p[2] for p in placed]
ax.scatter(xs, ys, s=70, color=accent, edgecolor='#2c1f0e', linewidth=0.8, zorder=3, alpha=0.9)

ax.set_xlim(60, 400)
ax.set_ylim(0, 500)
ax.set_aspect('equal')
ax.set_xticks([]); ax.set_yticks([])
for spine in ax.spines.values():
    spine.set_visible(False)

ax.text(0.06, 0.97, 'N', transform=ax.transAxes, fontsize=15, color=ink, fontweight='bold', va='top', ha='center')
ax.annotate('', xy=(0.06, 0.955), xytext=(0.06, 0.88), xycoords='axes fraction',
            arrowprops=dict(arrowstyle='-|>', color=ink, lw=1.6))

plt.tight_layout(pad=0.6)
plt.savefig('distribution_map.png', facecolor=parchment, bbox_inches='tight')
print("ok", len(placed), "points plotted")
