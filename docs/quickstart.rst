Quick start
===========

Python 3.11–3.14 are covered by the package's CI. Install normally:

.. code-block:: bash

   python -m pip install sidewalkreator

In Google Colab, use ``%pip install sidewalkreator`` in a code cell.

Generate from saved data
------------------------

Supply exactly one area argument. Providing an area polygon and saved street
data avoids geocoding and remote acquisition during generation:

.. code-block:: python

   import geopandas as gpd
   from headless_sidewalkreator import sidewalkreator

   aoi = gpd.read_file("area.geojson")
   osm = gpd.read_file("osm_snapshot.geojson")
   result = sidewalkreator(
       input_polygon_gdf=aoi,
       osm_gdf=osm,
       parameters={"show_progress": True, "buffer_dist": 2.0},
   )
   sidewalks = result["sidewalks"]
   sidewalks.to_crs(4326).to_file("sidewalks.geojson")

The returned geometries use the local UTM CRS estimated from the area.
Convert to EPSG:4326 when longitude/latitude GeoJSON is needed. Maplibreum
or another map library can display those converted geometries.

Download data automatically
---------------------------

.. code-block:: python

   result = sidewalkreator(
       bbox=(-72.53, 42.37, -72.52, 42.38),
       parameters={"timeout": 180},
   )

``bbox`` means ``(west, south, east, north)`` in WGS84 degrees. An AOI bounding
box does not reproduce an irregular area polygon, and current live OSM data
does not reproduce a saved snapshot. Use saved polygon/data inputs for a
reproducible area. Alternatively, pass ``place_name="Amherst, MA"`` instead
of ``bbox`` or ``input_polygon_gdf``.

Acquisition errors propagate and empty downloads stop with ``RuntimeError``;
the pipeline never substitutes a synthetic street network. Use inspected,
saved ``osm_gdf`` inputs for reproducible deliverables and record their source/date.

Configure and inspect
---------------------

Parameters belong in a dictionary, except for the area/data inputs and
``ignore_existing``. See :doc:`parameters` for existing-sidewalk coverage,
custom widths and crossing controls.

.. code-block:: python

   parameters_used = result["parameters"]
   print(parameters_used["buffer_dist"])

The returned dictionary records supplied/default values, not necessarily
clamped helper values or proof that a key affected the output. Review generated
geometry before using it as a mapped pedestrian network.
