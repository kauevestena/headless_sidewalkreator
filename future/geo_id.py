
"""
geo_id.py — Robust polygon IDs using polylabel + S2 and Web-Mercator Z/X/Y

Core ideas:
- Choose a stable anchor: pole of inaccessibility (maximum inscribed circle center, "polylabel"),
  computed in a local Lambert Azimuthal Equal-Area (LAEA) projection to get metric distances.
- Derive a per-polygon "scale" from the inradius (and optionally area), and map it to:
    (a) an S2 level (and optional CellId token if `s2sphere` is installed),
    (b) a Web-Mercator Z/X/Y tile for display and easy bucketing.
- Enforce "not finer than epsilon" to avoid ID flapping from tiny edits/noise.

Dependencies:
- Pure Python. Optionally uses `s2sphere` for real S2 CellId tokens if available.

Input geometry:
- Accepts GeoJSON-like dicts for Polygon or MultiPolygon, or a simple tuple/list:
    Polygon: {"type": "Polygon", "coordinates": [outer, hole1, hole2, ...]}
    MultiPolygon: {"type": "MultiPolygon", "coordinates": [[poly1_rings], [poly2_rings], ...]}
    or tuple: (outer_ring, [hole1, hole2, ...]) where rings are [(lon,lat), ...] (closed or open).
- Rings need not be closed; we'll close them if needed.

Outputs:
- Anchor (lon,lat), inradius (m), scale (m).
- S2 level and (if available) token/ID.
- Web-Mercator Z/X/Y tile at chosen zoom (bounded by epsilon).

Algorithmic notes:
- Polylabel is based on Mapbox's algorithm (best-first search over a cell quadtree),
  reimplemented here with a point-to-polygon signed distance function.
- LAEA projection is spherical; sufficient for robust local metric work without external libs.
- S2 level selection uses a global average size approximation to avoid depending on a library
  just to get cell sizes — if `s2sphere` is present, we also return the exact parent cell token.

Author: ChatGPT (GPT-5 Pro)
License: MIT (this file)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from math import sin, cos, asin, atan2, sqrt, pi, floor, ceil, log2, hypot, tan, radians, degrees, fabs, isfinite
import heapq
from typing import List, Tuple, Dict, Optional, Any

EARTH_RADIUS_M = 6371008.8  # IUGG mean Earth radius (meters)
MERCATOR_MAXLAT = 85.0511287798066  # web mercator cut-off

# -------------------------
# Geometry utilities
# -------------------------

def close_ring(ring: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(ring) == 0:
        return ring
    if ring[0] != ring[-1]:
        return ring + [ring[0]]
    return ring

def normalize_polygon(geom: Any) -> Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]]]:
    """
    Returns (outer, holes) with coords as [(lon,lat), ...], rings closed.
    For MultiPolygon, picks the largest-area polygon by outer ring area (approx).
    """
    def ring_area(r: List[Tuple[float, float]]) -> float:
        # naive lon/lat "area" just for ranking; correctness doesn't matter here
        a = 0.0
        for i in range(len(r) - 1):
            (x1, y1) = r[i]
            (x2, y2) = r[i+1]
            a += x1 * y2 - x2 * y1
        return 0.5 * fabs(a)

    def fix_poly(coords: List[List[Tuple[float, float]]]) -> Tuple[List[Tuple[float, float]], List[List[Tuple[float, float]]]]:
        rings = [close_ring([(float(x), float(y)) for x,y in ring]) for ring in coords if len(ring) >= 3]
        if not rings:
            raise ValueError("Polygon has no valid rings.")
        outer = rings[0]
        holes = rings[1:]
        return outer, holes

    if isinstance(geom, dict):
        t = geom.get("type")
        if t == "Polygon":
            coords = geom["coordinates"]
            outer, holes = fix_poly(coords)
            return outer, holes
        elif t == "MultiPolygon":
            # pick the largest by outer ring area (rough proxy)
            polys = []
            for poly in geom["coordinates"]:
                if not poly:
                    continue
                o, h = fix_poly(poly)
                polys.append((o, h, ring_area(o)))
            if not polys:
                raise ValueError("MultiPolygon has no valid components.")
            polys.sort(key=lambda x: x[2], reverse=True)
            o, h, _ = polys[0]
            return o, h
        else:
            raise ValueError(f"Unsupported geometry type: {t}")
    elif isinstance(geom, (list, tuple)):
        if len(geom) == 0:
            raise ValueError("Empty geometry.")
        if isinstance(geom[0], (list, tuple)) and len(geom) == 2 and isinstance(geom[1], list):
            # (outer, holes)
            outer = close_ring(geom[0])
            holes = [close_ring(r) for r in geom[1]]
            return outer, holes
        else:
            # assume it's just an outer ring
            outer = close_ring(list(geom))
            return outer, []
    else:
        raise ValueError("Unsupported geometry format.")

def spherical_centroid_lonlat(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Returns an approximate spherical centroid of a set of lon/lat points (degrees) using
    unit-vector averaging (robust near antimeridian).
    """
    if not points:
        return 0.0, 0.0
    x = y = z = 0.0
    for lon, lat in points:
        lon_r, lat_r = radians(lon), radians(lat)
        clat = cos(lat_r)
        x += clat * cos(lon_r)
        y += clat * sin(lon_r)
        z += sin(lat_r)
    x /= len(points); y /= len(points); z /= len(points)
    lon0 = atan2(y, x)
    hyp = sqrt(x*x + y*y)
    lat0 = atan2(z, hyp)
    return (degrees(lon0), degrees(lat0))

# -------------------------
# Lambert Azimuthal Equal-Area (spherical) projection centered at (lon0,lat0)
# -------------------------

def laea_forward(lon: float, lat: float, lon0: float, lat0: float, R: float = EARTH_RADIUS_M) -> Tuple[float, float]:
    lon_r, lat_r = radians(lon), radians(lat)
    lon0_r, lat0_r = radians(lon0), radians(lat0)
    k = sqrt(2.0/(1.0 + sin(lat0_r)*sin(lat_r) + cos(lat0_r)*cos(lat_r)*cos(lon_r - lon0_r)))
    x = R * k * cos(lat_r) * sin(lon_r - lon0_r)
    y = R * k * (cos(lat0_r)*sin(lat_r) - sin(lat0_r)*cos(lat_r)*cos(lon_r - lon0_r))
    return (x, y)

def laea_inverse(x: float, y: float, lon0: float, lat0: float, R: float = EARTH_RADIUS_M) -> Tuple[float, float]:
    lon0_r, lat0_r = radians(lon0), radians(lat0)
    rho = sqrt(x*x + y*y)
    if rho < 1e-12:
        return (lon0, lat0)
    c = 2.0 * asin(min(1.0, rho/(2.0*R)))
    sin_c = sin(c)
    cos_c = cos(c)
    lat_r = asin(cos_c*sin(lat0_r) + (y*sin_c*cos(lat0_r)/rho))
    lon_r = lon0_r + atan2(x*sin_c, rho*cos(lat0_r)*cos_c - y*sin(lat0_r)*sin_c)
    return (degrees(lon_r), degrees(lat_r))

# -------------------------
# Point-in-polygon & distance utilities (planar)
# -------------------------

def point_in_ring(pt: Tuple[float, float], ring: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm (odd-even rule). ring must be closed."""
    x, y = pt
    inside = False
    for i in range(len(ring)-1):
        x1, y1 = ring[i]
        x2, y2 = ring[i+1]
        # Check edge crosses horizontal ray
        if ((y1 > y) != (y2 > y)):
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1 + 1e-300)
            if x_intersect > x:
                inside = not inside
    return inside

def point_in_polygon(pt: Tuple[float, float], outer: List[Tuple[float, float]], holes: List[List[Tuple[float, float]]]) -> bool:
    if not point_in_ring(pt, outer):
        return False
    for h in holes:
        if point_in_ring(pt, h):
            return False
    return True

def dist_to_segment_sq(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Squared distance from point P to segment AB."""
    vx, vy = x2 - x1, y2 - y1
    wx, wy = px - x1, py - y1
    seg_len_sq = vx*vx + vy*vy
    if seg_len_sq == 0.0:
        dx, dy = px - x1, py - y1
        return dx*dx + dy*dy
    t = (wx*vx + wy*vy) / seg_len_sq
    if t < 0.0:
        dx, dy = px - x1, py - y1
        return dx*dx + dy*dy
    elif t > 1.0:
        dx, dy = px - x2, py - y2
        return dx*dx + dy*dy
    projx = x1 + t * vx
    projy = y1 + t * vy
    dx, dy = px - projx, py - projy
    return dx*dx + dy*dy

def point_to_ring_distance(pt: Tuple[float, float], ring: List[Tuple[float, float]]) -> float:
    px, py = pt
    min_d2 = float('inf')
    for i in range(len(ring)-1):
        x1, y1 = ring[i]
        x2, y2 = ring[i+1]
        d2 = dist_to_segment_sq(px, py, x1, y1, x2, y2)
        if d2 < min_d2:
            min_d2 = d2
    return sqrt(min_d2)

def point_to_polygon_signed_distance(pt: Tuple[float, float], outer: List[Tuple[float, float]], holes: List[List[Tuple[float, float]]]) -> float:
    inside_outer = point_in_ring(pt, outer)
    inside_hole = False
    for h in holes:
        if point_in_ring(pt, h):
            inside_hole = True
            break
    inside = inside_outer and not inside_hole

    # Distance to nearest boundary (outer or any hole)
    d = point_to_ring_distance(pt, outer)
    for h in holes:
        dh = point_to_ring_distance(pt, h)
        if dh < d:
            d = dh

    return d if inside else -d

def ring_bbox(ring: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))

def polygon_area_and_centroid(outer: List[Tuple[float, float]], holes: List[List[Tuple[float, float]]]) -> Tuple[float, Tuple[float, float]]:
    """
    Planar polygon (with holes) area and centroid via standard formulas.
    Returns (area, (cx, cy)); area is positive.
    """
    def ring_area_centroid(r: List[Tuple[float,float]]) -> Tuple[float, float, float]:
        a = 0.0; cx = 0.0; cy = 0.0
        for i in range(len(r)-1):
            x1, y1 = r[i]
            x2, y2 = r[i+1]
            cross = x1*y2 - x2*y1
            a += cross
            cx += (x1 + x2) * cross
            cy += (y1 + y2) * cross
        a *= 0.5
        if a != 0:
            cx /= (6.0 * a)
            cy /= (6.0 * a)
        else:
            # degenerate; just average points
            sx = sum([p[0] for p in r]); sy = sum([p[1] for p in r])
            n = max(1, len(r)-1)
            cx, cy = sx/n, sy/n
        return (a, cx, cy)

    a0, cx0, cy0 = ring_area_centroid(outer)
    total_area = fabs(a0)
    total_cx = cx0 * a0
    total_cy = cy0 * a0

    for h in holes:
        ah, cxh, cyh = ring_area_centroid(h)
        # holes have opposite sign
        total_area -= fabs(ah)
        total_cx -= cxh * fabs(ah)
        total_cy -= cyh * fabs(ah)

    if total_area != 0:
        cx = total_cx / (a0 if a0 == 0 else a0)  # keep centroid direction from outer sign
        cy = total_cy / (a0 if a0 == 0 else a0)
        # The above keeps the centroid near the outer centroid; for robustness we'll
        # fallback to outer centroid if division is unstable
    else:
        cx, cy = cx0, cy0

    # Ensure positive area
    return (max(total_area, 0.0), (cx, cy))

# -------------------------
# Polylabel (Mapbox algorithm variant)
# -------------------------

@dataclass(order=True)
class _Cell:
    # For heapq: we want max-heap by 'maxd', so we'll store negative priority separately.
    priority: float
    x: float=field(compare=False)
    y: float=field(compare=False)
    h: float=field(compare=False)
    d: float=field(compare=False)
    maxd: float=field(compare=False)

def _create_cell(x: float, y: float, h: float, outer: List[Tuple[float, float]], holes: List[List[Tuple[float, float]]]) -> _Cell:
    d = point_to_polygon_signed_distance((x, y), outer, holes)
    maxd = d + h * 1.4142135623730951  # sqrt(2)
    return _Cell(priority=-maxd, x=x, y=y, h=h, d=d, maxd=maxd)

def polylabel_laea(outer_ll: List[Tuple[float, float]], holes_ll: List[List[Tuple[float, float]]],
                   precision: float = 1.0) -> Tuple[Tuple[float,float], float, Dict[str,float]]:
    """
    Compute polylabel in a local LAEA projection. Returns:
      - anchor_lonlat (lon, lat) in degrees
      - inradius_m (>=0)
      - stats dict with keys: {'iterations', 'bbox_width_m', 'bbox_height_m'}

    precision: stop when (cell.maxd - best.d) <= precision (meters)
    """
    if len(outer_ll) < 4:
        # degenerate polygon
        lon, lat = outer_ll[0]
        return (lon, lat), 0.0, {'iterations': 0, 'bbox_width_m': 0.0, 'bbox_height_m': 0.0}

    # projection center near polygon
    lon0, lat0 = spherical_centroid_lonlat(outer_ll)

    # project rings to LAEA
    outer_xy = [laea_forward(lon, lat, lon0, lat0) for lon, lat in outer_ll]
    holes_xy = [[laea_forward(lon, lat, lon0, lat0) for lon, lat in ring] for ring in holes_ll]

    # bounding box
    minx, miny, maxx, maxy = ring_bbox(outer_xy)
    width = maxx - minx
    height = maxy - miny
    if width == 0.0 and height == 0.0:
        lon, lat = outer_ll[0]
        return (lon, lat), 0.0, {'iterations': 0, 'bbox_width_m': width, 'bbox_height_m': height}

    cell_size = min(width, height)
    h = cell_size / 2.0

    # priority queue of cells
    queue: List[_Cell] = []

    # Cover bbox with initial cells of size 'cell_size'
    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cell = _create_cell(x + h, y + h, h, outer_xy, holes_xy)
            queue.append(cell)
            y += cell_size
        x += cell_size

    heapq.heapify(queue)

    # Best cell so far
    # Start with a cell at polygon centroid (planar) for speed
    _, (cx0, cy0) = polygon_area_and_centroid(outer_xy, holes_xy)
    best = _create_cell(cx0, cy0, 0.0, outer_xy, holes_xy)

    # Also consider bbox center
    bbox_center = _create_cell(minx + width/2.0, miny + height/2.0, 0.0, outer_xy, holes_xy)
    if bbox_center.d > best.d:
        best = bbox_center

    iterations = 0

    while queue:
        cell = heapq.heappop(queue)
        iterations += 1

        if cell.d > best.d:
            best = cell

        # Stop if we cannot find a better solution
        if (cell.maxd - best.d) <= precision:
            continue

        # Otherwise, split into four cells
        h2 = cell.h / 2.0
        for dx in (-h2, h2):
            for dy in (-h2, h2):
                c = _create_cell(cell.x + dx, cell.y + dy, h2, outer_xy, holes_xy)
                heapq.heappush(queue, c)

    # Best center in LAEA
    inradius = max(0.0, best.d)
    # Convert back to lon/lat
    anchor_lon, anchor_lat = laea_inverse(best.x, best.y, lon0, lat0)
    return (anchor_lon, anchor_lat), inradius, {'iterations': iterations, 'bbox_width_m': width, 'bbox_height_m': height}

# -------------------------
# Scale selection & S2/WM mappings
# -------------------------

def robust_scale_from_polygon(inradius_m: float, area_m2: float, eps_m: float, use_equivalent: bool = True) -> float:
    """Compute a robust per-polygon scale ℓ* in meters."""
    l_in = 2.0 * inradius_m
    if use_equivalent and area_m2 > 0.0:
        l_eq = 2.0 * sqrt(area_m2 / pi)  # equivalent circle diameter
        # median of two values = their average if only two
        l_star = 0.5 * (l_in + l_eq)
    else:
        l_star = l_in
    # clamp to epsilon floor
    return max(l_star, eps_m)

def s2_level_for_scale(l_star_m: float, eps_m: float, alpha: float = 0.6, level_cap: int = 30) -> Dict[str, Any]:
    """
    Choose an S2 level based on desired cell diagonal <= alpha * l_star, but not finer than epsilon.
    We use a global-average approximation: edge_length(l) ≈ 9.22e6 / 2^l meters; diag ≈ edge*sqrt(2).

    Returns dict with keys:
      - level (int)
      - approx_diag_m (float)
      - approx_edge_m (float)
      - level_due_to_eps_max (int) : the maximum allowed level subject to d >= eps
      - level_due_to_scale (int)
    """
    # target diagonal threshold from scale
    d_target = max(1e-6, alpha * l_star_m)  # meters

    # Minimal level achieving diag <= d_target
    # diag(l) ≈ (9.22e6 / 2^l) * sqrt(2)
    C = 9_220_000.0 * 1.4142135623730951
    level_scale = int(ceil(log2(C / d_target)))
    level_scale = max(0, min(level_scale, level_cap))

    # "Not finer than epsilon": i.e., we require diag >= eps
    # The maximal allowed level with diag >= eps is: level <= floor(log2(C/eps)) - 1
    level_eps_min = int(ceil(log2(C / max(1e-6, eps_m))))  # first level where diag <= eps
    level_eps_max_allowed = max(0, min(level_cap, level_eps_min - 1))

    level = min(level_scale, level_eps_max_allowed)
    # compute approximate metrics at chosen level
    edge_m = 9_220_000.0 / (2**level)
    diag_m = edge_m * 1.4142135623730951

    return {
        "level": level,
        "approx_diag_m": diag_m,
        "approx_edge_m": edge_m,
        "level_due_to_eps_max": level_eps_max_allowed,
        "level_due_to_scale": level_scale,
    }

def s2_cell_token_for_point(lat: float, lon: float, level: int) -> Dict[str, Optional[str]]:
    """
    If s2sphere is installed, returns {'token': '...', 'id': '...'} at given parent level.
    Otherwise returns {'token': None, 'id': None}.
    """
    try:
        from s2sphere import CellId, LatLng
    except Exception:
        return {"token": None, "id": None}
    latlng = LatLng.from_degrees(lat, lon)
    cid = CellId.from_lat_lng(latlng).parent(int(level))
    try:
        token = cid.to_token()
    except Exception:
        token = None
    return {"token": token, "id": str(int(cid.id()))}

def wm_tile_zoom_for_scale(lat: float, l_star_m: float, eps_m: float, beta: float = 0.6, max_zoom: int = 22) -> Dict[str, Any]:
    """
    Choose a Web-Mercator zoom so that tile ground width <= beta*l_star and not finer than epsilon.
    Returns dict with keys:
      - z (int), z_due_to_scale (int), z_due_to_eps_max (int), tile_width_m (at chosen z)
    """
    # Clamp latitude to Mercator domain for scale calculation
    phi = max(-MERCATOR_MAXLAT, min(MERCATOR_MAXLAT, lat))
    W = 2.0 * pi * EARTH_RADIUS_M * cos(radians(phi))  # ground width of the world at latitude for XY width proxy

    # minimal z satisfying width <= beta*l_star
    z_scale = int(ceil(log2(W / max(1e-6, beta * l_star_m))))
    z_scale = max(0, min(z_scale, max_zoom))

    # maximum z allowed to avoid going finer than epsilon: require width >= eps => z <= floor(log2(W/eps))
    z_eps_max = int(floor(log2(W / max(1e-6, eps_m))))
    z_eps_max = max(0, min(z_eps_max, max_zoom))

    z = min(z_scale, z_eps_max)
    tile_width = W / (2**z)
    return {"z": z, "z_due_to_scale": z_scale, "z_due_to_eps_max": z_eps_max, "tile_width_m": tile_width}

def wm_zxy_for_point(lat: float, lon: float, z: int) -> Tuple[int, int, int]:
    """
    Compute the Web-Mercator tile (Z/X/Y) containing (lat,lon) at zoom z.
    """
    lat_clamped = max(-MERCATOR_MAXLAT, min(MERCATOR_MAXLAT, lat))
    n = 2 ** z
    x = int(floor((lon + 180.0) / 360.0 * n))
    lat_rad = radians(lat_clamped)
    y = int(floor((1.0 - (log_mercator(lat_rad) / pi)) / 2.0 * n))
    return (z, x, y)

def log_mercator(lat_rad: float) -> float:
    """Return ln( tan(pi/4 + lat/2) ) with safeguards."""
    # Equivalent to asinh(tan(lat)) but use the conventional expression
    # Avoid extreme values at the poles due to clamping earlier
    return log_tan_pi4_plus_half(lat_rad)

def log_tan_pi4_plus_half(lat_rad: float) -> float:
    # ln( tan(pi/4 + lat/2) )
    return __import__("math").log( tan(pi/4.0 + lat_rad/2.0) )

# -------------------------
# Main entry
# -------------------------

def compute_geo_ids(
    geom: Any,
    eps_m: float = 10.0,
    alpha_s2: float = 0.6,
    beta_wm: float = 0.6,
    s2_level_cap: int = 30,
    wm_zoom_cap: int = 22,
    polylabel_precision_m: float = 1.0,
) -> Dict[str, Any]:
    """
    Given a polygon (or multipolygon), compute:
      - anchor lon/lat (polylabel), inradius (m), per-polygon scale ℓ* (m)
      - S2 level and (if available) CellId token/ID
      - WM tile z/x/y at chosen zoom (bounded by epsilon)

    Parameters:
      eps_m: noise tolerance (do not pick resolutions finer than this)
      alpha_s2: fraction of ℓ* to target S2 cell diagonal
      beta_wm: fraction of ℓ* to target WM tile width
      polylabel_precision_m: polylabel search precision (meters) in LAEA plane

    Returns:
      dict with keys: 'anchor', 'scale_m', 's2', 'wm', 'stats'
    """
    outer_ll, holes_ll = normalize_polygon(geom)

    # Polylabel anchor in LAEA
    (anchor_lon, anchor_lat), inradius_m, stats = polylabel_laea(outer_ll, holes_ll, precision=polylabel_precision_m)

    # Compute polygon area (LAEA) for l_eq
    lon0, lat0 = spherical_centroid_lonlat(outer_ll)
    outer_xy = [laea_forward(lon, lat, lon0, lat0) for lon, lat in outer_ll]
    holes_xy = [[laea_forward(lon, lat, lon0, lat0) for lon, lat in ring] for ring in holes_ll]
    area_m2, _ = polygon_area_and_centroid(outer_xy, holes_xy)

    l_star_m = robust_scale_from_polygon(inradius_m, area_m2, eps_m)

    # S2 selection
    s2_sel = s2_level_for_scale(l_star_m, eps_m, alpha=alpha_s2, level_cap=s2_level_cap)
    s2_token = s2_cell_token_for_point(anchor_lat, anchor_lon, s2_sel["level"])
    s2_result = {
        "level": s2_sel["level"],
        "approx_edge_m": s2_sel["approx_edge_m"],
        "approx_diag_m": s2_sel["approx_diag_m"],
        "token": s2_token["token"],
        "id": s2_token["id"],
        "due_to": {"scale_level": s2_sel["level_due_to_scale"], "eps_level_max": s2_sel["level_due_to_eps_max"]},
    }

    # Web-Mercator tile selection
    wm_sel = wm_tile_zoom_for_scale(anchor_lat, l_star_m, eps_m, beta=beta_wm, max_zoom=wm_zoom_cap)
    z, x, y = wm_zxy_for_point(anchor_lat, anchor_lon, wm_sel["z"])
    wm_result = {
        "z": int(z), "x": int(x), "y": int(y),
        "tile_width_m": wm_sel["tile_width_m"],
        "due_to": {"scale_z": wm_sel["z_due_to_scale"], "eps_z_max": wm_sel["z_due_to_eps_max"]},
    }

    return {
        "anchor": {"lon": anchor_lon, "lat": anchor_lat, "inradius_m": inradius_m},
        "scale_m": l_star_m,
        "s2": s2_result,
        "wm": wm_result,
        "stats": stats,
        "params": {"eps_m": eps_m, "alpha_s2": alpha_s2, "beta_wm": beta_wm, "polylabel_precision_m": polylabel_precision_m},
        "notes": {
            "s2_token_requires_s2sphere": s2_token["token"] is None,
            "wm_lat_clamped": abs(anchor_lat) > MERCATOR_MAXLAT
        }
    }

# -------------- Convenience: brief pretty-printer

def summarize(result: Dict[str, Any]) -> str:
    a = result["anchor"]
    s2 = result["s2"]
    wm = result["wm"]
    lines = []
    lines.append(f"Anchor: lon={a['lon']:.6f}, lat={a['lat']:.6f}, inradius={a['inradius_m']:.2f} m")
    lines.append(f"Scale ℓ*: {result['scale_m']:.2f} m")
    lines.append(f"S2: level={s2['level']} (approx edge={s2['approx_edge_m']:.2f} m, diag={s2['approx_diag_m']:.2f} m)"
                 + (f", token={s2['token']}" if s2['token'] is not None else " (install 's2sphere' to get token)"))
    lines.append(f"WM tile: z/x/y = {wm['z']}/{wm['x']}/{wm['y']} (tile width ~ {wm['tile_width_m']:.2f} m)")
    return "\n".join(lines)

# -------------- Example usage as script

if __name__ == "__main__":
    # Rough rectangle around Central Park, NYC
    poly = {
        "type": "Polygon",
        "coordinates": [[
            (-73.9819,40.8006), (-73.9580,40.8006), (-73.9580,40.7643), (-73.9819,40.7643), (-73.9819,40.8006)
        ]]
    }
    res = compute_geo_ids(poly, eps_m=8.0, alpha_s2=0.6, beta_wm=0.6, wm_zoom_cap=22)
    print(summarize(res))
