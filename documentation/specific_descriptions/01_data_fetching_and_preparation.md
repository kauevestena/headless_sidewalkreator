# Step 1: Data Fetching and Preparation

This document describes the initial steps of the SidewalKreator process, where map data is fetched from OpenStreetMap (OSM) and prepared for sidewalk generation.

## Data Fetching

The process begins by acquiring the necessary map data for a specified area of interest.

1.  **Input Area**: The process starts with a user-provided polygon that defines the area of interest. This is typically read from a GeoJSON file using the `read_input_polygon` function.

2.  **Bounding Box**: The bounding box of the input polygon is calculated using `get_bbox_from_gdf`. This bounding box is used to query the OSM Overpass API.

3.  **Overpass Query**: The `fetch_street_network_for_bbox` function (which utilizes `osm_fetch.py`) constructs and sends an Overpass API query to fetch all `highway` and `building` features within the bounding box. A timeout can be configured for this request.

4.  **Data Acquisition**: The data is retrieved from the Overpass API. The `osm_fetch` module uses the `osmnx` library to handle the request and parse the response into a GeoDataFrame.

5.  **Clipping**: The retrieved OSM data is clipped to the precise boundary of the input polygon using the `clip_gdf` function.

6.  **Reprojection**: The clipped data is reprojected from WGS 84 (EPSG:4326) to a local Transverse Mercator projection using `reproject_gdf`. This is essential for accurate metric measurements (e.g., buffer distances).

## Data Cleaning and Preparation

Once the data is fetched, it is processed to make it suitable for generating sidewalks. This is primarily handled by the `data_clean_gdf` function.

1.  **Filter Roads**: Roads with a configured width of 0 are removed. This allows for the exclusion of certain road types from the analysis. Existing ways tagged as `footway=sidewalk` or `footway=crossing` are identified and stored separately.

2.  **Network Simplification**: The road lines are split at every intersection to create individual segments. This is a critical step for topological analysis and is performed by the `split_lines_at_intersections` function.

3.  **Width Assignment**: A width attribute is assigned to each road segment based on its `highway` tag. These widths are defined in the project's parameters.

4.  **Protoblock Creation**: The cleaned and split road network is polygonized to create "protoblocks" using the `polygonize_lines_gdf` function. These are the enclosed areas formed by the road network, analogous to city blocks. These protoblocks are used in later steps to determine where sidewalks should be generated.
