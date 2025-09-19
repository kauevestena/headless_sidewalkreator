# Step 4: Sidewalk Splitting and Output Generation

This document covers the final steps of the process: subdividing the continuous sidewalk lines into smaller segments and generating the output files.

## Sidewalk Splitting

The `split_sidewalks_gdf` function orchestrates the splitting of the continuous sidewalk lines into smaller, more practical segments for mapping.

1.  **Split at Block Corners**: The sidewalks are first split at the corners of the protoblocks using the `split_sidewalks_by_protoblock_corners` function.

2.  **Advanced Splitting Rules**: Several methods are available for further splitting:
    *   **Voronoi Polygons**: If Points of Interest (POIs) are available (e.g., from building centroids or addresses), the `split_sidewalks_by_voronoi` function can be used. It generates Voronoi polygons around the POIs and splits the sidewalks where they intersect the Voronoi cell boundaries.
    *   **Maximum Length**: The `split_sidewalks_by_max_length` function splits sidewalks into segments that do not exceed a defined maximum length.
    *   **Number of Segments**: The `split_sidewalks_by_num_segments` function splits each sidewalk section into a specified number of equal-length segments.

3.  **Topological Cleaning**: After splitting, the `clean_geometries_gdf` function is used to perform snapping and remove duplicate vertices to ensure the final sidewalk network is topologically correct.

## Output Generation

The final step, handled by the `full_sidewalkreator_algorithm` function, prepares and exports all the generated data.

1.  **Data Finalization**: The final layers (sidewalks, crossings, kerbs) are cleaned of any temporary attributes.

2.  **File Export**:
    *   An output directory is created.
    *   The final sidewalk, crossing, and kerb layers are reprojected back to WGS 84 (EPSG:4326) and saved as separate GeoJSON files.

3.  **Merged GeoJSON**: To simplify importing into JOSM (a popular OSM editor), the `create_merged_output` function combines the individual GeoJSON files into a single `sidewalkreator_output.geojson` file.

4.  **Auxiliary Files**: Additional data generated during the process, such as the input polygon, protoblocks, and road intersection points, are saved in an `auxiliary` folder for reference.

5.  **Changeset Comment**: A text file is generated containing a recommended changeset comment for uploading the data to OpenStreetMap.

6.  **Parameters Dump**: The parameters used for the run are saved to a JSON file, allowing for easy replication of the results.
