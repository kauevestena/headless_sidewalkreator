Python API
==========

.. py:module:: headless_sidewalkreator

.. py:function:: sidewalkreator(input_polygon_gdf=None, place_name=None, bbox=None, osm_gdf=None, parameters=None, ignore_existing=False)

   Generate candidate sidewalks, crossings and kerbs. Supply exactly one area
   selector; a conflict or missing selector raises ``ValueError``.

   :param input_polygon_gdf: Polygon GeoDataFrame with a defined CRS.
   :param place_name: Place string passed to OSMnx geocoding. This still needs a network request if ``osm_gdf`` is supplied.
   :param bbox: WGS84 ``(west, south, east, north)`` in degrees.
   :param osm_gdf: Optional saved OSM-like GeoDataFrame with a CRS, line geometry and highway classes. A combined snapshot can also contain building/amenity/shop features. Supplied data skips download but is still clipped/preprocessed.
   :param parameters: Optional dictionary of :doc:`runtime overrides <parameters>`, merged shallowly with defaults. Unknown or unsupported keys raise ``ValueError``.
   :param ignore_existing: If True, bypass mapped-sidewalk block coverage filtering. The default False excludes blocks above ``cutoff_percent_protoblock``. Separate road-tag exclusions still apply. See :doc:`parameters` for the coverage formula.
   :returns: A dictionary with the entries below.

.. list-table:: Result entries
   :header-rows: 1

   * - Key
     - Value
   * - ``sidewalks``
     - Generated line GeoDataFrame.
   * - ``crossings``
     - Crossing line GeoDataFrame.
   * - ``kerbs``
     - Kerb point GeoDataFrame, normally two per accepted crossing.
   * - ``protoblocks``
     - All intermediate block polygons, including blocks excluded by existing sidewalk coverage.
   * - ``intersection_points``
     - Crossing centroid points used in final splitting.
   * - ``pois``
     - Unified building-centroid/address/amenity/shop inputs for splitting.
   * - ``input_area``
     - Resolved area GeoDataFrame in its input CRS.
   * - ``parameters``
     - Merged runtime dictionary and optional diagnostic metadata.

Processing/output geometry layers use the estimated metric UTM CRS;
``input_area`` retains its input CRS. The API does not write final output
files unless the caller requests exports; ``save_debug_layers`` is the
documented exception.

.. py:function:: generate_protoblocks(input_polygon_gdf=None, place_name=None, bbox=None, osm_gdf=None, parameters=None)

   Return only a protoblock polygon GeoDataFrame, in the estimated local UTM
   CRS. Area selection and supplied-data semantics match
   :py:func:`sidewalkreator`. This API does not prune dead-end streets, draw
   sidewalks/crossings, or apply sidewalk segmentation. The
   :doc:`parameter reference <parameters>` identifies which keys are used by
   this function. Full-pipeline-only controls raise ``ValueError``.

``generate_sidewalks_gdf`` is the backward-compatible alias for
:py:func:`sidewalkreator`.
