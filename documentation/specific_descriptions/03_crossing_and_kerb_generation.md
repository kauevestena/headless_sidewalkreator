# Step 3: Crossing and Kerb Generation

This step adds pedestrian crossings at intersections and generates kerb geometries. The key functions are `draw_crossings_gdf` and `generate_kerbs_gdf`.

## Crossing Generation

1.  **Identify Intersection Points**: The algorithm identifies intersections where three or more road segments meet, as these are candidates for crossings.

2.  **Calculate Crossing Geometry**: For each valid intersection, the algorithm attempts to generate crossing geometries. The primary method is the sophisticated **ABCDE points system**.

### Kerb Generation Logic (ABCDE Points System)

The `generate_crossing_abcde` function implements a detailed algorithm to create accurate kerb positions:

**Point Definition:**
- **Point A**: Intersection of the crossing line with the sidewalk geometry on one side.
- **Point B**: Kerb position on the first side (interpolated along the line from A to C).
- **Point C**: The center of the crossing, typically the road intersection point.
- **Point D**: Kerb position on the second side (interpolated along the line from E to C).
- **Point E**: Intersection of the crossing line with the sidewalk geometry on the opposite side.

**Iterative Intersection Finding:**
The algorithm uses an iterative approach to find a valid crossing:

1. **Vector Projection**: Starting from point C, vectors are projected outwards to find intersections with sidewalk geometries (points A and E).
2. **Iterative Scaling**: If no intersection is found, the search distance is increased, and the search is repeated.
3. **Distance Validation**: When intersections are found, the length of the crossing is validated against the expected street width.
4. **Adaptive Center Repositioning**: If the crossing is too long, the center point C is moved incrementally inward along the road, and the process repeats. This is crucial for handling complex, non-perpendicular intersections.
5. **Quality Control**: The process is limited by a maximum number of iterations and an absolute maximum crossing length to prevent infinite loops and unrealistic outputs.

If the ABCDE algorithm fails to produce a valid crossing, a simpler fallback method may be used, which draws a line of a default length perpendicular to the main road at the intersection.

## Kerb Generation

The `generate_kerbs_gdf` function is responsible for creating the final kerb point geometries. It extracts points B and D from each valid ABCDE crossing line, as these represent the precise locations where the kerb should be placed. If a crossing was generated using a simpler method, the start and end points of the crossing line are typically used as the kerb locations.
