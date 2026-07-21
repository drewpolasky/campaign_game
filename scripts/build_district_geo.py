"""Vectorize the game's per-state district pixel maps into SVG polygons.

The desktop game defines district regions as raster pixel maps
(`stateDistricts/<State>.txt`, one line `x,y,State,District` per pixel of that
state's image). This script traces each district's boundary into a simplified
polygon so the browser client can draw real district shapes (colored by leader,
clickable), instead of only a zoomed state outline.

Output: one JSON per state at `web/public/districts/<State>.json`:

    { "name": "Texas",
      "viewBox": [minx, miny, width, height],
      "districts": { "West Texas": [ [[x,y], ...], ... ], ... } }

plus an `index.json` listing the states that have geometry.

Run once (regenerate if the pixel maps change):
    python3 scripts/build_district_geo.py
"""
import json
import os

import numpy as np
from scipy import ndimage
from skimage import measure

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO, 'stateDistricts')
OUT_DIR = os.path.join(REPO, 'web', 'public', 'districts')

SIMPLIFY_TOL = 1.5   # Douglas-Peucker tolerance in pixels
MIN_AREA = 40        # drop connected components smaller than this (specks)


def load_labels(txt_path):
    """Read a state's pixel map into a 2D label grid + the district name list.
    Returns (labels[H,W] int, names list where id-1 indexes names, W, H)."""
    xs, ys, names_per_pixel = [], [], []
    name_to_id = {}
    ids = []
    with open(txt_path, 'r') as f:
        for line in f:
            parts = line.split(',')
            if len(parts) < 4:
                continue
            try:
                x = int(parts[0]); y = int(parts[1])
            except ValueError:
                continue
            name = parts[3].strip()
            if name not in name_to_id:
                name_to_id[name] = len(name_to_id) + 1  # 1-based; 0 = background
            xs.append(x); ys.append(y); ids.append(name_to_id[name])

    if not xs:
        return None
    xs = np.array(xs); ys = np.array(ys); ids = np.array(ids, dtype=np.int32)
    W = int(xs.max()) + 2
    H = int(ys.max()) + 2
    labels = np.zeros((H, W), dtype=np.int32)
    labels[ys, xs] = ids
    id_to_name = {v: k for k, v in name_to_id.items()}
    return labels, id_to_name, W, H


def trace_district(mask):
    """Return a list of simplified [x,y] polygons for a boolean mask."""
    polys = []
    comp, n = ndimage.label(mask)
    for c in range(1, n + 1):
        cm = comp == c
        if cm.sum() < MIN_AREA:
            continue
        padded = np.pad(cm.astype(float), 1)  # pad so edge-touching regions close
        contours = measure.find_contours(padded, 0.5)
        if not contours:
            continue
        contour = max(contours, key=len)  # outer boundary (largest)
        contour = measure.approximate_polygon(contour, tolerance=SIMPLIFY_TOL)
        # contour is (row, col); shift out the pad and emit (x, y) as ints.
        poly = [[int(round(col - 1)), int(round(row - 1))] for row, col in contour]
        if len(poly) >= 3:
            polys.append(poly)
    return polys


def build_state(txt_path):
    loaded = load_labels(txt_path)
    if loaded is None:
        return None
    labels, id_to_name, W, H = loaded
    districts = {}
    minx = miny = 10**9
    maxx = maxy = -10**9
    for did, name in id_to_name.items():
        polys = trace_district(labels == did)
        if not polys:
            continue
        districts[name] = polys
        for poly in polys:
            for x, y in poly:
                minx = min(minx, x); maxx = max(maxx, x)
                miny = min(miny, y); maxy = max(maxy, y)
    if not districts:
        return None
    pad = 6
    view = [minx - pad, miny - pad, (maxx - minx) + 2 * pad, (maxy - miny) + 2 * pad]
    return {'viewBox': view, 'districts': districts}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    txts = sorted(f for f in os.listdir(SRC_DIR) if f.endswith('.txt'))
    index = []
    for fn in txts:
        state = fn[:-4]
        out = build_state(os.path.join(SRC_DIR, fn))
        if out is None:
            print('  skip (no geometry): {}'.format(state))
            continue
        out['name'] = state
        with open(os.path.join(OUT_DIR, state + '.json'), 'w') as f:
            json.dump(out, f, separators=(',', ':'))
        index.append(state)
        ndist = len(out['districts'])
        pts = sum(len(p) for polys in out['districts'].values() for p in polys)
        print('  {:22s} {:2d} districts, {:5d} pts'.format(state, ndist, pts))
    with open(os.path.join(OUT_DIR, 'index.json'), 'w') as f:
        json.dump(sorted(index), f)
    print('Wrote {} states to {}'.format(len(index), OUT_DIR))


if __name__ == '__main__':
    main()
