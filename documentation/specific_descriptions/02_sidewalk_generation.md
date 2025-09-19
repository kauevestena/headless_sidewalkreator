# Step 2: Sidewalk Generation

This is the core step where the actual sidewalk geometries are created. The main function responsible for this is `draw_sidewalks_gdf`.

1.  **Building Overlap Check**: To prevent generated sidewalks from overlapping existing building polygons, the algorithm can adjust road widths. The `adjust_buffer_for_buildings` function calculates the distance to the nearest building for each road segment. If a sidewalk would overlap, its buffer distance is reduced to maintain a minimum separation.

2.  **Buffering**: The primary method for creating sidewalks is buffering:
    *   A buffer is generated around each road segment. The buffer distance is dynamic, calculated based on the road width and other parameters.
    *   These individual buffers are dissolved into a single polygon representing the entire road network area.
    *   To create smooth, rounded corners at intersections, a two-step buffering process is applied: a positive buffer is created with a "Curve Radius", and then a negative buffer of the same radius is applied.

3.  **Sidewalk Extraction (Difference Method)**:
    *   A very large buffer is created around the entire dissolved road network buffer.
    *   The algorithm then computes the geometric "difference" between this large buffer and the road network buffer.
    *   The result of this operation is a layer containing the polygons that fall *outside* the road network. The largest of these polygons (the area surrounding the entire map extent) is discarded, leaving only the internal polygons, which are the sidewalks.

4.  **Polygon to Line Conversion**: The sidewalk polygons are converted into line geometries, representing the edges of the sidewalks.

5.  **Exclusion/Sure Zones**: The `handle_sidewalk_tags` function processes `sidewalk=no/left/right/both` tags on streets. It creates "exclusion zones" (from `sidewalk=no`, etc.) and "sure zones" (from `sidewalk=yes/both`, etc.). The exclusion zone polygons are subtracted from the generated sidewalk layer, and if sure zones exist, the output is constrained to those areas.

6.  **Protoblock Filtering**: The `filter_and_buffer_protoblocks_gdf` function is used to prevent drawing sidewalks where they already exist. It checks if any protoblocks already contain a significant network of `footway=sidewalk` ways. If the sidewalk coverage is above a certain percentage, that protoblock is removed from consideration.
