"""Offline smoke test: run with the wheel interpreter, outside the checkout."""
import importlib
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys

import geopandas as gpd
from shapely.geometry import LineString, box
import headless_sidewalkreator as package

assert Path(sys.prefix).resolve() in Path(package.__file__).resolve().parents
for module in ("base", "overture", "protomaps"):
    importlib.import_module(f"headless_sidewalkreator.planet_download.{module}")
print("Installed sidewalkreator", version("sidewalkreator"), package.__file__)
subprocess.run([sys.executable, "-m", "headless_sidewalkreator", "--help"], check=True)
cli = Path(sys.executable).parent / ("sidewalkreator.exe" if sys.platform == "win32" else "sidewalkreator")
subprocess.run([str(cli), "--help"], check=True)

lines = []
for offset in (0, 100, 200):
    lines.extend([LineString([(offset, 0), (offset, 200)]),
                  LineString([(0, offset), (200, offset)])])
roads = gpd.GeoDataFrame({"highway": ["residential"] * len(lines)}, geometry=lines, crs=3857).to_crs(4326)
area = gpd.GeoDataFrame(geometry=[box(-20, -20, 220, 220)], crs=3857).to_crs(4326)
result = package.sidewalkreator(input_polygon_gdf=area, osm_gdf=roads,
                                parameters={"show_progress": False})
for name in ("sidewalks", "crossings", "kerbs", "protoblocks"):
    layer = result[name]
    assert not layer.empty, name
    assert layer.geometry.is_valid.all(), name
    assert not layer.geometry.is_empty.any(), name
assert len(result["kerbs"]) == 2 * len(result["crossings"])
print("Offline generation passed")
