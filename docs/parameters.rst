Parameter reference
===================

Three different kinds of input
----------------------------------

* **Function arguments** select the area, supply a dataset and control the
  existing-sidewalk policy through ``ignore_existing``. See :doc:`api`.
* **Runtime keys** go inside ``parameters={...}``. Every recognized runtime
  key is described below; defaults are generated from the source.
* **Module constants** in ``headless_sidewalkreator/parameters.py`` also include
  internal constants and style filenames. A name in that file is not
  automatically an effective runtime override.

Runtime options are combined with a shallow dictionary ``update``. Omitted
keys keep their defaults; a supplied dictionary such as ``default_widths``
replaces that entire value. Unknown keys raise ``ValueError`` before acquisition
or geometry processing, with a suggested spelling when available. A key that
only applies to the full pipeline is rejected by ``generate_protoblocks()``.
The override object, ``default_widths`` and ``provider_kwargs`` must be dictionaries.

Geometry distances are in **metres in the estimated local UTM CRS**, not
degrees or pixels. Percentages use values such as ``25`` for 25%, not ``0.25``.
The range guidance below distinguishes recommended inputs from actual
validation and clamping; the API has no comprehensive type/range validator.

Existing sidewalks
------------------

By default (``ignore_existing=False``), the pipeline excludes blocks whose
mapped ``highway=footway, footway=sidewalk`` coverage exceeds
``cutoff_percent_protoblock``. Coverage is the unique existing sidewalk length
clipped to each block, divided by its perimeter, multiplied by 100 and capped
at 100%. For a block with a 400 m perimeter, 180 m of mapped sidewalks gives
45% coverage: the default cutoff of 40 excludes that block. Duplicate ways
are counted once and portions outside the block are not counted.

Excluded blocks produce no new sidewalk segments or crossing centres.
``result["protoblocks"]`` still includes all blocks for inspection.
``ignore_existing=True`` bypasses this coverage filter; it does not disable
separate ``sidewalk=no/left/right`` road-tag exclusion geometry, topology
pruning, or crossing acceptance rules. This is a block-level heuristic, not
an exact duplicate-sidewalk detector. Standalone ``generate_protoblocks()``
returns the unfiltered blocks.

Changing widths and offsets
-------------------------------

Copy the table to change only selected highway classes. Supplying only
``{"residential": 7.0}`` would make all missing classes use the fallback,
including classes that the default table excludes.

.. code-block:: python

   from headless_sidewalkreator.parameters import default_widths

   widths = {**default_widths, "residential": 7.0, "service": 0.0}
   result = sidewalkreator(
       input_polygon_gdf=aoi,
       osm_gdf=osm,
       parameters={"default_widths": widths, "buffer_dist": 2.0},
   )

The nominal sidewalk-axis offset is ``road_width / 2 + buffer_dist / 2``.
For a 6 m road and ``buffer_dist=2``, that is 4 m from the road centreline
on each side, before building/rounding/tag adjustments. ``buffer_dist`` is
not a physical sidewalk width. Widths and road tags survive intersection
splitting and Protomaps repair. Noded segments inherit the source road with
the longest overlapping length; coincident sources use the first input row.

Splitting and crossing interactions
---------------------------------------

Splitting runs in order: block corners, POI/Voronoi boundaries,
``split_max_len``, ``split_num_segments``, crossings, then short-segment merging
even when no crossings are found. A maximum split length or requested part count is not
a final-output guarantee. ``min_stretch_size`` attempts merging, not removal
of every short line.

Crossing placement combines several controls: the source street must pass
``min_crossing_segment_length``; the centre must pass the protoblock test;
rays must hit sidewalks on both sides; the resulting length must satisfy
both the relative tolerance and ``abs_max_crossing_len``. Increasing a ray
search limit cannot override the acceptance limits.

Complete runtime reference
--------------------------

Each entry states which public API supports it. Standalone
``generate_protoblocks()`` supports acquisition, cleaning, topology and debug
options; it rejects crossing and sidewalk-only controls.

.. include:: _generated/parameter_reference.rst

Provider-specific nested options
------------------------------------

These options go inside ``parameters["provider_kwargs"]``, not at the same
level as ``buffer_dist``. They apply only to data acquisition. Unknown options
for the selected provider raise ``ValueError``. Put ``timeout`` and ``provider``
at the top level; they are rejected inside this dictionary. The wrapper inserts
``show_progress`` automatically and routes it separately from constructor options.

.. list-table:: Provider options
   :header-rows: 1
   :widths: 18 21 61

   * - Provider / option
     - Default
     - Meaning and handling
   * - OSMnx: ``max_retries``
     - ``2``
     - Non-negative integer; up to retries + 1 attempts, with backoff.
   * - Protomaps: ``url``
     - ``https://data.source.coop/protomaps/openstreetmap/tiles/v3.pmtiles``
     - PMTiles archive URL; subject to the downloader's allowed-domain check.
   * - Protomaps: ``zoom``
     - ``"auto"``
     - Integer in the archive's min/max zoom range, or ``"auto"`` (``None`` also selects auto). Booleans and other values raise ValueError.
   * - Protomaps: ``auto_zoom_tile_budget``
     - ``16``
     - Positive integer, excluding booleans. Auto selection uses detail zoom 15 for requests within the budget and zoom 14 otherwise, adjusted to archive limits.
   * - Protomaps: ``tile_workers``
     - Up to ``8``
     - Positive integer, excluding booleans, capped by the requested tile count. ``max_workers`` is an alias; ``tile_workers`` takes precedence.
   * - Protomaps: ``max_retries``
     - ``2``
     - Non-negative integer retries per request. The HTTP timeout comes from top-level ``timeout``.
   * - Protomaps: ``show_progress``
     - Inherits top-level value
     - Overrides only provider progress output. The driver alone defaults to True; the public pipeline forwards its own value (False by default).
   * - Overture: ``release``
     - ``"2026-06-17.0"``
     - Release identifier; alphanumeric characters, dots, hyphens and underscores only, without path traversal. This is a pinned implementation default, not a promise of the latest release.
   * - Overture: ``base_url``
     - ``https://overturemapswestus2.blob.core.windows.net/release``
     - Base URL for GeoParquet releases; subject to the allowed-domain check.

``sleep_fn`` is an advanced Python-only retry hook in the acquisition layer;
it is not JSON-serializable and is not a normal CLI configuration option.

Acquisition errors propagate, and an empty download raises ``RuntimeError``.
No synthetic data is substituted. Use a saved ``osm_gdf`` for reproducible inputs.
``show_progress`` controls pipeline output and the provider's progress where
supported; Overture's constructor receives only ``release`` and ``base_url``.

.. code-block:: python

   result = sidewalkreator(
       input_polygon_gdf=aoi,
       parameters={
           "provider": "protomaps",
           "provider_kwargs": {"zoom": "auto", "tile_workers": 4},
           "repair_protomaps_topology": True,
           "protomaps_endpoint_snap_tolerance": 0.5,
       },
   )

Command-line JSON
-----------------

Write runtime options as a JSON object (JSON uses ``true``, ``false`` and
``null``, while Python uses ``True``, ``False`` and ``None``):

.. code-block:: json

   {
     "timeout": 180,
     "show_progress": true,
     "min_crossing_segment_length": 20.0,
     "crossing_center_buffer_distance": 1.0,
     "crossing_direction_mode": "parallel"
   }

.. code-block:: bash

   sidewalkreator --input-file area.geojson --output-dir output --parameters parameters.json

Pass ``--ignore-existing`` as a CLI flag, never as a runtime dictionary key.
A missing/unreadable file, malformed JSON or a non-object JSON value stops
the CLI with an error. Provider CLI flags override the selected JSON provider
while preserving its nested options; incompatible options are rejected.
``--release`` overrides only the nested release value and requires Overture.
The CLI exports the merged settings to ``output/parameters.json``.

Module constants and output metadata
------------------------------------

Internal constants such as ``minimal_buffer``, ``big_buffer_d``,
``snap_disjointed_tol``, ``tiny_segments_tol`` and QGIS style filenames are not
general ``parameters={...}`` controls. Passing them as runtime keys raises
``ValueError``; it does not change the module constants.

``result["parameters"]`` contains the merged full-pipeline settings. It may
also contain ``protomaps_topology_stats``, diagnostic output added during a
Protomaps repair run; that is not a tuning parameter. Some helpers clamp
values locally, so this dictionary is not a complete record of effective
clamped values. The CLI exports this dictionary to ``parameters.json``.
