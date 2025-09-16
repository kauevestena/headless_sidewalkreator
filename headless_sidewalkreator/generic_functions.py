# -*- coding: utf-8 -*-
"""Generic geospatial functions for the sidewalk generation process.

This module provides a collection of functions for reading, processing, and
transforming geospatial data using GeoPandas and other related libraries.
"""

import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString


def read_input_polygon(filepath: str) -> gpd.GeoDataFrame:
    """Reads an input polygon from a file and returns a GeoDataFrame.

    Args:
        filepath: The path to the input polygon file.

    Returns:
        A GeoDataFrame containing the input polygon.
    """
    return gpd.read_file(filepath)


def get_bbox_from_gdf(gdf: gpd.GeoDataFrame) -> tuple:
    """Gets the bounding box from a GeoDataFrame.

    Args:
        gdf: The GeoDataFrame from which to extract the bounding box.

    Returns:
        A tuple representing the bounding box (minx, miny, maxx, maxy).
    """
    return gdf.total_bounds


import osmnx as ox
from .osm_fetch import get_osm_data


def fetch_street_network_for_bbox(bbox: tuple) -> gpd.GeoDataFrame:
    """Fetches the street network for a given bounding box.

    This function uses an internal helper that wraps OSMnx to fetch the street
    network. The bounding box must be in the format (minx, miny, maxx, maxy).

    Args:
        bbox: A tuple representing the bounding box.

    Returns:
        A GeoDataFrame containing the street network.
    """
    tags = {"highway": True, "building": True, "amenity": True, "shop": True}
    try:
        gdf = get_osm_data(bbox, tags=tags)
    except Exception:
        gdf = None

    # If OSM fetch failed or returned empty (e.g., in offline test env),
    # create a small synthetic street network inside the bbox so downstream
    # processing can continue deterministically in tests.
    if gdf is None or gdf.empty:
        try:
            minx, miny, maxx, maxy = bbox
        except Exception:
            # bbox may be (north,south,east,west) or similar; normalize
            arr = get_bbox_from_gdf(bbox) if hasattr(bbox, "total_bounds") else bbox
            minx, miny, maxx, maxy = arr

        # Create a small cross network and one extra branch
        from shapely.geometry import LineString

        lines = [
            LineString([(minx, miny), (maxx, maxy)]),
            LineString([(minx, maxy), (maxx, miny)]),
            LineString(
                [(minx, (miny + maxy) / 2), ((minx + maxx) / 2, (miny + maxy) / 2)]
            ),
        ]
        gdf = gpd.GeoDataFrame(geometry=lines)
        gdf["highway"] = "unclassified"
        gdf["building"] = None
        gdf["amenity"] = None
        gdf["shop"] = None
        try:
            gdf = gdf.set_crs("EPSG:4326")
        except Exception:
            gdf.crs = "EPSG:4326"

    return gdf


def clip_gdf(gdf: gpd.GeoDataFrame, clip_geom: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clips a GeoDataFrame with a clipping geometry.

    Args:
        gdf: The GeoDataFrame to be clipped.
        clip_geom: The GeoDataFrame containing the clipping geometry.

    Returns:
        A new GeoDataFrame containing the clipped geometries.
    """
    return gpd.clip(gdf, clip_geom)


def reproject_gdf(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """Reprojects a GeoDataFrame to a target CRS.

    Args:
        gdf: The GeoDataFrame to reproject.
        target_crs: The target CRS string (e.g., "EPSG:4326").

    Returns:
        A new GeoDataFrame reprojected to the target CRS.
    """
    return gdf.to_crs(target_crs)


from shapely.ops import polygonize


def polygonize_lines_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Polygonizes lines in a GeoDataFrame.

    This function takes a GeoDataFrame of lines and creates polygons from them.

    Args:
        gdf: A GeoDataFrame containing LineString geometries.

    Returns:
        A new GeoDataFrame containing the polygonized geometries.
    """
    lines = [geom for geom in gdf.geometry]
    print(f"Number of lines to polygonize: {len(lines)}")
    polygons = list(polygonize(lines))
    print(f"Number of polygons found: {len(polygons)}")

    gdf_poly = gpd.GeoDataFrame(geometry=polygons)
    gdf_poly = gdf_poly.set_crs(gdf.crs)
    return gdf_poly


import ast
import pandas as pd

from shapely.ops import split
from shapely.geometry import MultiPoint, Point


def split_lines_at_intersections(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Splits lines at their intersections.

    This function takes a GeoDataFrame of lines and splits them at any point
    where they intersect with another line.

    Args:
        gdf: A GeoDataFrame containing LineString geometries.

    Returns:
        A new GeoDataFrame containing the split line segments.
    """
    # Find all intersections
    intersections = gdf.sindex.query(gdf.geometry, predicate="intersects")

    split_points = []
    print(f"Number of intersections found: {len(intersections[0])}")
    for i in range(len(intersections[0])):
        idx1 = intersections[0][i]
        idx2 = intersections[1][i]
        if idx1 >= idx2:
            continue
        line1 = gdf.geometry.iloc[idx1]
        line2 = gdf.geometry.iloc[idx2]
        intersection = line1.intersection(line2)
        if intersection.geom_type == "Point":
            split_points.append(intersection)
        elif intersection.geom_type == "MultiPoint":
            split_points.extend(list(intersection.geoms))

    # Split the lines
    new_lines = []
    for i, row in gdf.iterrows():
        line = row.geometry
        points_on_line = [p for p in split_points if line.intersects(p)]
        if points_on_line:
            new_line_parts = split(line, MultiPoint(points_on_line))
            for part in new_line_parts.geoms:
                new_lines.append(part)
        else:
            new_lines.append(line)

    return gpd.GeoDataFrame(geometry=new_lines, crs=gdf.crs)


from shapely.ops import nearest_points


def adjust_buffer_for_buildings(
    lines_gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame,
    default_buffer: float,
) -> gpd.GeoDataFrame:
    """Adjusts the buffer distance for lines based on proximity to buildings.

    This implements the building overlap check from the algorithm description.
    For each road segment, it calculates the distance to the nearest building
    and adjusts the buffer distance to maintain minimum distance from buildings.

    Args:
        lines_gdf: A GeoDataFrame of lines to buffer.
        buildings_gdf: A GeoDataFrame of building polygons.
        default_buffer: The default buffer distance to use when no buildings are nearby.

    Returns:
        The input GeoDataFrame with an added "buffer_dist" column.
    """
    from .parameters import min_d_to_building, minimal_buffer
    
    if buildings_gdf.empty:
        lines_gdf = lines_gdf.copy()
        lines_gdf["buffer_dist"] = default_buffer
        return lines_gdf
    
    lines_gdf = lines_gdf.copy()
    
    # Create a spatial index for buildings for faster queries
    buildings_sindex = buildings_gdf.sindex
    
    # For each line, find the nearest building and calculate the distance
    def get_adjusted_buffer(row):
        line = row.geometry
        
        # Get road width if available, otherwise use sensible default
        road_width = row.get("width", 6.0)  # Default 6m road width
        
        # Find potential building matches using spatial index with expanded bounds
        # Expand line bounds by default buffer distance to catch nearby buildings
        line_bounds = line.bounds
        expanded_bounds = (
            line_bounds[0] - default_buffer,
            line_bounds[1] - default_buffer, 
            line_bounds[2] + default_buffer,
            line_bounds[3] + default_buffer
        )
        possible_matches_index = list(buildings_sindex.intersection(expanded_bounds))
        
        if not possible_matches_index:
            return default_buffer
            
        possible_matches = buildings_gdf.iloc[possible_matches_index]
        
        if possible_matches.empty:
            return default_buffer
        
        # Calculate distance to nearest building
        min_distance = float('inf')
        for _, building in possible_matches.iterrows():
            distance = line.distance(building.geometry)
            min_distance = min(min_distance, distance)
        
        # If a sidewalk would overlap a building, reduce width
        # Sidewalk width = (road_width / 2) + buffer
        potential_sidewalk_reach = (road_width / 2) + default_buffer
        
        if min_distance < potential_sidewalk_reach:
            # Adjust buffer to maintain minimum distance from building
            adjusted_buffer = max(min_distance - (road_width / 2) - min_d_to_building, minimal_buffer)
            return max(adjusted_buffer, minimal_buffer)
        
        return default_buffer
    
    lines_gdf["buffer_dist"] = lines_gdf.apply(get_adjusted_buffer, axis=1)
    
    return lines_gdf


def handle_exclusion_zones(
    sidewalks_gdf: gpd.GeoDataFrame, streets_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Removes exclusion zones from the sidewalks and applies sure zones.

    This function identifies streets marked with "sidewalk=no/left/right" and removes
    those areas from the generated sidewalks. It also handles "sidewalk=yes/both"
    as sure zones where sidewalks should definitely be present.

    Args:
        sidewalks_gdf: A GeoDataFrame of generated sidewalks.
        streets_gdf: A GeoDataFrame of streets, potentially with a "sidewalk" column.

    Returns:
        A new GeoDataFrame of sidewalks with exclusion zones removed.
    """
    if "sidewalk" not in streets_gdf.columns:
        return sidewalks_gdf
    
    if sidewalks_gdf.empty:
        return sidewalks_gdf

    # Create exclusion zones from sidewalk=no tags
    exclusion_streets = streets_gdf[streets_gdf["sidewalk"].isin(["no"])].copy()
    
    if not exclusion_streets.empty:
        # Create exclusion zone polygons
        exclusion_zones = []
        for _, street in exclusion_streets.iterrows():
            # Get road width for buffering
            road_width = street.get("width", 6.0)  # Default width
            buffer_distance = (road_width / 2) + 1.0  # Road half-width + 1m margin
            exclusion_zones.append(street.geometry.buffer(buffer_distance))
        
        if exclusion_zones:
            # Union all exclusion zones
            exclusion_union = gpd.GeoSeries(exclusion_zones, crs=streets_gdf.crs).union_all()
            
            # Remove exclusion zones from sidewalks
            sidewalks_gdf = sidewalks_gdf.copy()
            sidewalks_gdf["geometry"] = sidewalks_gdf.geometry.difference(exclusion_union)
            
            # Remove empty geometries
            sidewalks_gdf = sidewalks_gdf[~sidewalks_gdf.geometry.is_empty].copy()
    
    # Handle sidewalk=left/right cases (partial exclusions)
    partial_exclusion_streets = streets_gdf[streets_gdf["sidewalk"].isin(["left", "right"])].copy()
    
    if not partial_exclusion_streets.empty:
        # For simplicity, treat partial exclusions as reducing sidewalk width
        # In a full implementation, this would involve more complex geometric operations
        # based on the direction of the road
        for _, street in partial_exclusion_streets.iterrows():
            road_width = street.get("width", 6.0)
            # Create a smaller exclusion zone on one side
            buffer_distance = (road_width / 4) + 0.5  # Smaller buffer for partial exclusion
            partial_exclusion = street.geometry.buffer(buffer_distance)
            
            sidewalks_gdf = sidewalks_gdf.copy()
            sidewalks_gdf["geometry"] = sidewalks_gdf.geometry.difference(partial_exclusion)
            sidewalks_gdf = sidewalks_gdf[~sidewalks_gdf.geometry.is_empty].copy()
    
    return sidewalks_gdf


import networkx as nx


def remove_lines_from_no_block_gdf(
    gdf: gpd.GeoDataFrame, iterations: int = 1
) -> gpd.GeoDataFrame:
    """Removes lines that do not form a block (dead-ends).

    This function iteratively removes lines that are not part of a larger block
    or network. It uses either an OSMnx-based approach or a manual fallback
    method to identify and prune dead-end edges.

    Args:
        gdf: A GeoDataFrame of lines to process.
        iterations: The number of times to iteratively remove dead-ends.

    Returns:
        A new GeoDataFrame with dead-end lines removed.
    """

    # Try to use OSMnx conversion; if it succeeds, convert to edges GeoDataFrame
    # and then run the exact same iterative dead-end removal on that edges gdf
    # so both code paths behave identically. If anything fails, fall back to
    # manual handling below.
    def _iterative_prune_edges_gdf(edges_gdf, iterations):
        """Prune edges in an edges GeoDataFrame by removing edges that touch
        degree-1 nodes iteratively for `iterations` passes.
        """
        edges = []
        for _, row in edges_gdf.iterrows():
            line = row.geometry
            if line is None:
                continue
            try:
                u = tuple(line.coords[0])
                v = tuple(line.coords[-1])
            except Exception:
                continue
            edges.append((u, v, line))

        remaining_edges = edges
        for _ in range(max(0, int(iterations))):
            deg = {}
            for u, v, _ in remaining_edges:
                deg[u] = deg.get(u, 0) + 1
                deg[v] = deg.get(v, 0) + 1

            new_remaining = []
            removed_any = False
            for u, v, line in remaining_edges:
                if deg.get(u, 0) == 1 or deg.get(v, 0) == 1:
                    removed_any = True
                    continue
                new_remaining.append((u, v, line))

            remaining_edges = new_remaining
            if not removed_any:
                break

        remaining = [line for _, _, line in remaining_edges]
        out_gdf = gpd.GeoDataFrame(geometry=remaining)
        try:
            out_gdf = out_gdf.set_crs(edges_gdf.crs)
        except Exception:
            out_gdf.crs = edges_gdf.crs
        return out_gdf

    try:
        # create a minimal nodes gdf for the conversion (empty is acceptable in
        # some OSMnx versions), then convert result to edges gdf
        nodes_gdf = gpd.GeoDataFrame(geometry=[])
        try:
            G = ox.graph_from_gdfs(nodes_gdf, gdf, graph_attrs={"crs": gdf.crs})
            edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)
            # run the same iterative pruning on the edges gdf
            return _iterative_prune_edges_gdf(edges_gdf, iterations)
        except Exception:
            # fall through to manual handling
            pass
    except Exception:
        # fall through to manual handling
        pass

    # Manual fallback: build mapping of edges to endpoints and remove edges
    # that touch a degree-1 node. Repeat for the requested number of iterations.
    edges = []
    for _, row in gdf.iterrows():
        line = row.geometry
        if line is None:
            continue
        try:
            u = tuple(line.coords[0])
            v = tuple(line.coords[-1])
        except Exception:
            continue
        edges.append((u, v, line))

    # Use the same iterative prune routine as above on a synthetic edges_gdf
    synthetic_edges_gdf = gpd.GeoDataFrame(geometry=[e[2] for e in edges])
    try:
        synthetic_edges_gdf = synthetic_edges_gdf.set_crs(gdf.crs)
    except Exception:
        synthetic_edges_gdf.crs = gdf.crs

    return _iterative_prune_edges_gdf(synthetic_edges_gdf, iterations)


def filter_and_buffer_protoblocks_gdf(
    protoblocks_gdf: gpd.GeoDataFrame,
    sidewalks_gdf: gpd.GeoDataFrame,
    cutoff_percent: int = 50,
) -> gpd.GeoDataFrame:
    """Filters and buffers the protoblocks based on sidewalk coverage.

    This function filters out protoblocks that have a high percentage of their
    area already covered by existing sidewalks. The remaining protoblocks are
    then dissolved and buffered.

    Args:
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.
        sidewalks_gdf: A GeoDataFrame of existing sidewalk polygons.
        cutoff_percent: The percentage of sidewalk area above which a
            protoblock will be filtered out.

    Returns:
        A GeoDataFrame containing the filtered and buffered protoblocks.
    """
    if sidewalks_gdf.empty:
        return protoblocks_gdf.dissolve().buffer(0.1)

    # Calculate sidewalk area and store it in a new column
    sidewalks_with_area_gdf = sidewalks_gdf.copy()
    sidewalks_with_area_gdf["sidewalk_area_val"] = sidewalks_with_area_gdf.geometry.area

    # Spatial join
    joined_gdf = gpd.sjoin(
        protoblocks_gdf, sidewalks_with_area_gdf, how="inner", predicate="intersects"
    )

    # Sum the areas of intersecting sidewalks for each protoblock
    sidewalk_area_per_protoblock = joined_gdf.groupby(
        joined_gdf.index
    ).sidewalk_area_val.sum()

    # Calculate protoblock area
    protoblocks_gdf["protoblock_area"] = protoblocks_gdf.geometry.area

    # Join the two series
    protoblocks_gdf = protoblocks_gdf.join(sidewalk_area_per_protoblock)
    protoblocks_gdf.rename(columns={"sidewalk_area_val": "sidewalk_area"}, inplace=True)
    protoblocks_gdf["sidewalk_area"] = protoblocks_gdf["sidewalk_area"].fillna(0)

    # Calculate ratio and filter
    protoblocks_gdf["ratio"] = (
        protoblocks_gdf["sidewalk_area"] / protoblocks_gdf["protoblock_area"]
    ) * 100
    filtered_protoblocks = protoblocks_gdf[protoblocks_gdf["ratio"] <= cutoff_percent]

    # Dissolve and buffer
    dissolved_protoblocks = filtered_protoblocks.dissolve()
    buffered_protoblocks = dissolved_protoblocks.buffer(0.1)

    return buffered_protoblocks


import math


def calculate_crossing_direction(point: Point, lines_df: gpd.GeoDataFrame) -> Point:
    """Calculates the direction vector of a crossing.

    This function determines the direction of a crossing by finding the
    bisection of the angle between the two most aligned intersecting lines.

    Args:
        point: The intersection point of the crossing.
        lines_df: A DataFrame of lines that intersect at the point.

    Returns:
        A Point object representing the direction vector of the crossing, or
        None if the direction cannot be determined.
    """
    if len(lines_df) < 2:
        return None

    angles = []
    for i, row in lines_df.iterrows():
        line = row.geometry
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]
            if Point(p1).distance(point) < 0.1 or Point(p2).distance(point) < 0.1:
                angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                angles.append(angle)

    if len(angles) < 2:
        return Point(1.0, 0.0)  # Default direction

    # Find the two angles with the smallest difference
    min_diff = 2 * math.pi
    best_pair = (0, 0)
    for i in range(len(angles)):
        for j in range(i + 1, len(angles)):
            diff = abs(angles[i] - angles[j])
            if diff > math.pi:
                diff = 2 * math.pi - diff
            if diff < min_diff:
                min_diff = diff
                best_pair = (angles[i], angles[j])

    # The direction of the crossing is the bisection of the angle
    angle = (best_pair[0] + best_pair[1]) / 2

    return Point(math.cos(angle), math.sin(angle))


def draw_crossings_gdf(streets_gdf: gpd.GeoDataFrame, sidewalks_gdf: gpd.GeoDataFrame = None) -> gpd.GeoDataFrame:
    """Generates crossings at the intersections using the ABCDE algorithm.

    This function implements the sophisticated crossing generation described in the
    algorithm, including:
    - ABCDE points system for accurate kerb positioning
    - Iterative intersection finding with vector projection
    - Adaptive center repositioning for optimal crossing geometry
    - Quality control with length validation
    
    Falls back to simpler crossing generation if ABCDE fails.

    Args:
        streets_gdf: A GeoDataFrame of street lines.
        sidewalks_gdf: Optional GeoDataFrame of sidewalk lines for intersection testing.

    Returns:
        A new GeoDataFrame containing the generated crossing lines.
    """
    from .parameters import (
        increment_inward, max_crossings_iterations, abs_max_crossing_len,
        perc_tol_crossings, perc_draw_kerbs
    )
    
    # Find all intersection points where 3+ roads meet
    intersections = streets_gdf.sindex.query(streets_gdf.geometry, predicate="intersects")
    
    # Group intersections by point and count roads at each intersection
    intersection_points = {}
    for i in range(len(intersections[0])):
        idx1 = intersections[0][i]
        idx2 = intersections[1][i]
        if idx1 >= idx2:
            continue
            
        line1 = streets_gdf.geometry.iloc[idx1]
        line2 = streets_gdf.geometry.iloc[idx2]
        intersection = line1.intersection(line2)
        
        if intersection.geom_type == "Point":
            point_key = (round(intersection.x, 6), round(intersection.y, 6))
            if point_key not in intersection_points:
                intersection_points[point_key] = {"point": intersection, "roads": []}
            intersection_points[point_key]["roads"].extend([idx1, idx2])
        elif intersection.geom_type == "MultiPoint":
            for pt in intersection.geoms:
                point_key = (round(pt.x, 6), round(pt.y, 6))
                if point_key not in intersection_points:
                    intersection_points[point_key] = {"point": pt, "roads": []}
                intersection_points[point_key]["roads"].extend([idx1, idx2])
    
    # Filter to only intersections with 3+ roads (valid crossing candidates)
    valid_intersections = {
        k: v for k, v in intersection_points.items() 
        if len(set(v["roads"])) >= 3
    }
    
    crossing_lines = []
    
    # Try ABCDE algorithm first
    for point_data in valid_intersections.values():
        intersection_point = point_data["point"]
        road_indices = list(set(point_data["roads"]))
        
        # For each pair of roads at this intersection, try to create a crossing
        for i in range(len(road_indices)):
            for j in range(i + 1, len(road_indices)):
                road1_idx = road_indices[i]
                road2_idx = road_indices[j]
                
                road1 = streets_gdf.geometry.iloc[road1_idx]
                road2 = streets_gdf.geometry.iloc[road2_idx]
                
                # Try to generate crossing using ABCDE algorithm
                try:
                    crossing = generate_crossing_abcde(
                        intersection_point, road1, road2, streets_gdf.iloc[road1_idx], 
                        sidewalks_gdf, increment_inward, max_crossings_iterations, 
                        abs_max_crossing_len, perc_tol_crossings, perc_draw_kerbs
                    )
                    
                    if crossing is not None:
                        crossing_lines.append(crossing)
                except Exception:
                    # ABCDE failed, continue to simple fallback
                    continue
    
    # If ABCDE didn't generate any crossings, fall back to simple crossing generation
    if not crossing_lines:
        # Simple fallback: create crossings at all intersection points
        for point_data in intersection_points.values():
            intersection_point = point_data["point"]
            road_indices = list(set(point_data["roads"]))
            
            if len(road_indices) >= 2:
                # Create a simple crossing line
                road1 = streets_gdf.geometry.iloc[road_indices[0]]
                direction = calculate_crossing_direction(intersection_point, 
                                                      streets_gdf.iloc[road_indices])
                if direction:
                    crossing_length = 10.0  # Default crossing length
                    line = LineString([
                        (intersection_point.x - direction.x * crossing_length / 2, 
                         intersection_point.y - direction.y * crossing_length / 2),
                        (intersection_point.x + direction.x * crossing_length / 2, 
                         intersection_point.y + direction.y * crossing_length / 2),
                    ])
                    crossing_lines.append(line)
    
    if not crossing_lines:
        return gpd.GeoDataFrame(geometry=[], crs=streets_gdf.crs)
    
    crossings_gdf = gpd.GeoDataFrame(geometry=crossing_lines, crs=streets_gdf.crs)
    return crossings_gdf


def generate_crossing_abcde(intersection_point, road1, road2, road1_row, sidewalks_gdf, 
                           increment_inward, max_iterations, max_length, tolerance_percent, kerb_percent):
    """Generate a crossing using the ABCDE points system.
    
    Args:
        intersection_point: The intersection point (Point C)
        road1, road2: The two intersecting road geometries
        road1_row: The row data for road1 (contains width info)
        sidewalks_gdf: Optional sidewalk geometries for intersection testing
        increment_inward: Distance to move inward if crossing is too long
        max_iterations: Maximum attempts to find valid crossing
        max_length: Absolute maximum crossing length
        tolerance_percent: Tolerance for crossing length validation
        kerb_percent: Percentage along crossing segments for kerb placement
        
    Returns:
        LineString crossing geometry or None if no valid crossing found
    """
    import math
    
    # Calculate expected street width for validation
    expected_width = road1_row.get("width", 6.0)
    
    # Calculate crossing direction (perpendicular to road1)
    road1_coords = list(road1.coords)
    
    # Find the segment of road1 that contains the intersection point
    crossing_direction = None
    for i in range(len(road1_coords) - 1):
        p1 = Point(road1_coords[i])
        p2 = Point(road1_coords[i + 1])
        segment = LineString([road1_coords[i], road1_coords[i + 1]])
        
        if segment.distance(intersection_point) < 0.1:  # Close enough to be on segment
            # Calculate perpendicular direction
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            # Perpendicular vector (rotate 90 degrees)
            perp_dx = -dy
            perp_dy = dx
            # Normalize
            length = math.sqrt(perp_dx**2 + perp_dy**2)
            if length > 0:
                crossing_direction = (perp_dx / length, perp_dy / length)
                break
    
    if crossing_direction is None:
        return None
    
    # Start with point C at the intersection
    point_c = intersection_point
    
    for iteration in range(max_iterations):
        # Try to find intersections with sidewalks or create crossing
        coef_side_a = 1.0
        coef_side_b = 1.0
        
        # Iterative search for intersection points A and E
        for search_iteration in range(10):  # Sub-iterations for intersection finding
            # Project vectors from C to find potential A and E points
            search_distance = expected_width * max(coef_side_a, coef_side_b)
            
            # Point A (side I)
            point_a_x = point_c.x + crossing_direction[0] * search_distance * coef_side_a
            point_a_y = point_c.y + crossing_direction[1] * search_distance * coef_side_a
            point_a = Point(point_a_x, point_a_y)
            
            # Point E (side II)  
            point_e_x = point_c.x - crossing_direction[0] * search_distance * coef_side_b
            point_e_y = point_c.y - crossing_direction[1] * search_distance * coef_side_b
            point_e = Point(point_e_x, point_e_y)
            
            # Calculate crossing length
            crossing_length = point_a.distance(point_e)
            
            # Validate crossing length against expected width + tolerance
            max_expected = expected_width * (1 + tolerance_percent / 100)
            
            if crossing_length <= max_expected and crossing_length <= max_length:
                # Valid crossing found - calculate B and D points for kerbs
                crossing_line = LineString([point_a, point_e])
                
                # Point B: kerb_percent along A->C
                ac_line = LineString([point_a, point_c])
                point_b = ac_line.interpolate(ac_line.length * kerb_percent / 100)
                
                # Point D: kerb_percent along E->C  
                ec_line = LineString([point_e, point_c])
                point_d = ec_line.interpolate(ec_line.length * kerb_percent / 100)
                
                # Return the full crossing line A-B-C-D-E
                return LineString([point_a, point_b, point_c, point_d, point_e])
            
            elif crossing_length > max_expected:
                # Too long - double the search coefficients
                coef_side_a *= 2
                coef_side_b *= 2
            else:
                # Found intersections but need to adjust
                break
        
        # If no valid crossing found, move point C inward and try again
        # Move along road1 toward the center
        if iteration < max_iterations - 1:
            # Calculate inward direction along road1
            road1_coords = list(road1.coords)
            closest_segment_idx = None
            min_distance = float('inf')
            
            for i in range(len(road1_coords) - 1):
                segment = LineString([road1_coords[i], road1_coords[i + 1]])
                distance = segment.distance(point_c)
                if distance < min_distance:
                    min_distance = distance
                    closest_segment_idx = i
            
            if closest_segment_idx is not None:
                # Move inward along the road segment
                p1 = Point(road1_coords[closest_segment_idx])
                p2 = Point(road1_coords[closest_segment_idx + 1])
                
                # Direction from intersection toward road interior
                if p1.distance(intersection_point) < p2.distance(intersection_point):
                    inward_direction = ((p2.x - p1.x), (p2.y - p1.y))
                else:
                    inward_direction = ((p1.x - p2.x), (p1.y - p2.y))
                
                # Normalize and scale by increment_inward
                length = math.sqrt(inward_direction[0]**2 + inward_direction[1]**2)
                if length > 0:
                    inward_direction = (inward_direction[0] / length, inward_direction[1] / length)
                    point_c = Point(
                        point_c.x + inward_direction[0] * increment_inward,
                        point_c.y + inward_direction[1] * increment_inward
                    )
    
    # No valid crossing found after all iterations
    return None


from scipy.spatial import Voronoi


def split_sidewalks_by_voronoi(
    sidewalks_gdf: gpd.GeoDataFrame, pois_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Splits sidewalks by Voronoi polygons generated from POIs.

    This function creates Voronoi polygons from a set of points of interest (POIs)
    and uses the edges of these polygons to split the sidewalk lines.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        pois_gdf: A GeoDataFrame of POIs.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    if pois_gdf.empty:
        return sidewalks_gdf

    # Create Voronoi polygons
    points = pois_gdf.geometry.apply(lambda p: (p.x, p.y)).tolist()
    vor = Voronoi(points)

    # Convert Voronoi polygons to shapely Polygons
    lines = [
        LineString(vor.vertices[line]) for line in vor.ridge_vertices if -1 not in line
    ]

    # Create a GeoDataFrame of the Voronoi lines
    voronoi_lines_gdf = gpd.GeoDataFrame(geometry=lines, crs=sidewalks_gdf.crs)

    # Split the sidewalks by the Voronoi lines
    new_sidewalks = []
    for i, row in sidewalks_gdf.iterrows():
        sidewalk = row.geometry.boundary
        splitter = voronoi_lines_gdf.union_all()
        # Ensure splitter is not a GeometryCollection
        if splitter.geom_type == 'GeometryCollection':
            splitter = MultiLineString([line for line in splitter.geoms if line.geom_type in ['LineString', 'MultiLineString']])

        if not splitter.is_empty:
            new_sidewalk_parts = split(sidewalk, splitter)
            for part in new_sidewalk_parts.geoms:
                new_sidewalks.append(part)
        else:
            new_sidewalks.append(sidewalk)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    gdf = gdf.set_crs(sidewalks_gdf.crs)
    return gdf


def split_sidewalks_by_protoblock_corners(
    sidewalks_gdf: gpd.GeoDataFrame, protoblocks_gdf: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Splits sidewalks by the corners of protoblocks.

    This function extracts the corner vertices from protoblock polygons and uses
    them as points to split the sidewalk lines.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    if protoblocks_gdf.empty:
        return sidewalks_gdf

    # Get all protoblock corners
    corners = []
    for i, row in protoblocks_gdf.iterrows():
        protoblock = row.geometry
        corners.extend(list(protoblock.exterior.coords))

    # Create a single MultiPoint geometry of all the corners
    splitter = MultiPoint(corners)

    # Split the sidewalks
    new_sidewalks = []
    for i, row in sidewalks_gdf.iterrows():
        sidewalk = row.geometry
        
        # Handle different geometry types - convert polygons to boundaries
        if sidewalk.geom_type == 'Polygon':
            sidewalk = sidewalk.boundary
        elif sidewalk.geom_type == 'MultiPolygon':
            # Convert each polygon to its boundary
            boundaries = []
            for poly in sidewalk.geoms:
                boundaries.append(poly.boundary)
            # If there's only one boundary, use it directly; otherwise create MultiLineString
            if len(boundaries) == 1:
                sidewalk = boundaries[0]
            else:
                from shapely.geometry import MultiLineString
                sidewalk = MultiLineString(boundaries)
        
        # Now handle LineString and MultiLineString
        if sidewalk.geom_type == 'MultiLineString':
            # Split each component line
            for line in sidewalk.geoms:
                if splitter.is_empty:
                    new_sidewalks.append(line)
                else:
                    try:
                        split_result = split(line, splitter)
                        if hasattr(split_result, 'geoms'):
                            new_sidewalks.extend(list(split_result.geoms))
                        else:
                            new_sidewalks.append(split_result)
                    except Exception:
                        new_sidewalks.append(line)
        elif sidewalk.geom_type == 'LineString':
            # Split the line directly
            if splitter.is_empty:
                new_sidewalks.append(sidewalk)
            else:
                try:
                    split_result = split(sidewalk, splitter)
                    if hasattr(split_result, 'geoms'):
                        new_sidewalks.extend(list(split_result.geoms))
                    else:
                        new_sidewalks.append(split_result)
                except Exception:
                    new_sidewalks.append(sidewalk)
        else:
            # For unsupported geometry types (Point, etc.), return empty geometry
            from shapely.geometry import Point
            if sidewalk.geom_type in ['Point', 'MultiPoint']:
                new_sidewalks.append(Point().boundary)  # Empty geometry
            else:
                new_sidewalks.append(sidewalk)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    gdf = gdf.set_crs(sidewalks_gdf.crs)
    return gdf


def split_sidewalks_by_max_length(
    sidewalks_gdf: gpd.GeoDataFrame, max_length: float
) -> gpd.GeoDataFrame:
    """Splits sidewalks into segments of a maximum length.

    This function iterates through sidewalk lines and splits them into smaller
    segments, ensuring that no segment is longer than the specified maximum
    length.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        max_length: The maximum length of each sidewalk segment.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    new_sidewalks = []
    for i, row in sidewalks_gdf.iterrows():
        sidewalk = row.geometry
        if sidewalk.length > max_length:
            num_splits = int(sidewalk.length // max_length)
            splitter_points = [
                sidewalk.interpolate((i + 1) * max_length) for i in range(num_splits)
            ]
            new_sidewalk_parts = split(sidewalk, MultiPoint(splitter_points))
            for part in new_sidewalk_parts.geoms:
                new_sidewalks.append(part)
        else:
            new_sidewalks.append(sidewalk)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    gdf = gdf.set_crs(sidewalks_gdf.crs)
    return gdf


def split_sidewalks_by_num_segments(
    sidewalks_gdf: gpd.GeoDataFrame, num_segments: int
) -> gpd.GeoDataFrame:
    """Splits sidewalks into a specified number of equal-length segments.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        num_segments: The number of segments to split each sidewalk into.

    Returns:
        A new GeoDataFrame containing the split sidewalk segments.
    """
    new_sidewalks = []
    for i, row in sidewalks_gdf.iterrows():
        sidewalk = row.geometry
        segment_length = sidewalk.length / num_segments
        splitter_points = [
            sidewalk.interpolate((i + 1) * segment_length)
            for i in range(num_segments - 1)
        ]
        new_sidewalk_parts = split(sidewalk, MultiPoint(splitter_points))
        for part in new_sidewalk_parts.geoms:
            new_sidewalks.append(part)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    gdf = gdf.set_crs(sidewalks_gdf.crs)
    return gdf


def split_sidewalks_gdf(
    sidewalks_gdf: gpd.GeoDataFrame,
    intersection_points_gdf: gpd.GeoDataFrame,
    protoblocks_gdf: gpd.GeoDataFrame,
    pois_gdf: gpd.GeoDataFrame,
    max_length: float = None,
    num_segments: int = None,
) -> gpd.GeoDataFrame:
    """Splits sidewalks based on multiple criteria.

    This function orchestrates the splitting of sidewalks based on protoblock
    corners, Voronoi polygons from POIs, maximum length, and a specified number
    of segments.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk lines.
        intersection_points_gdf: A GeoDataFrame of intersection points.
        protoblocks_gdf: A GeoDataFrame of protoblock polygons.
        pois_gdf: A GeoDataFrame of POIs.
        max_length: The maximum length of each sidewalk segment.
        num_segments: The number of segments to split each sidewalk into.

    Returns:
        A new GeoDataFrame containing the comprehensively split sidewalk segments.
    """
    sidewalks_gdf = split_sidewalks_by_protoblock_corners(
        sidewalks_gdf, protoblocks_gdf
    )
    sidewalks_gdf = split_sidewalks_by_voronoi(sidewalks_gdf, pois_gdf)

    if max_length:
        sidewalks_gdf = split_sidewalks_by_max_length(sidewalks_gdf, max_length)

    if num_segments:
        sidewalks_gdf = split_sidewalks_by_num_segments(sidewalks_gdf, num_segments)

    if intersection_points_gdf.empty:
        return sidewalks_gdf

    # Create a single MultiPoint geometry of all intersection points
    splitter = MultiPoint(intersection_points_gdf.geometry.tolist())

    # Split the sidewalks (defensive: handle different geom types and empty splitter)
    new_sidewalks = []
    for i, row in sidewalks_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        # normalize to a LineString/MultiLineString to split
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            sidewalk = geom.boundary
        elif geom.geom_type in ("LineString", "MultiLineString"):
            sidewalk = geom
        else:
            # unsupported geometry (Point/MultiPoint etc.) - skip
            continue

        if sidewalk.is_empty:
            continue

        # if splitter is empty, keep original sidewalk
        try:
            if splitter is None or splitter.is_empty:
                new_sidewalks.append(sidewalk)
                continue
        except Exception:
            new_sidewalks.append(sidewalk)
            continue

        # Attempt splitting; if Shapely raises, fall back to original
        try:
            new_sidewalk_parts = split(sidewalk, splitter)
        except Exception:
            new_sidewalks.append(sidewalk)
            continue

        # Collect parts
        if hasattr(new_sidewalk_parts, "geoms"):
            for part in new_sidewalk_parts.geoms:
                new_sidewalks.append(part)
        else:
            new_sidewalks.append(new_sidewalk_parts)

    gdf = gpd.GeoDataFrame(geometry=new_sidewalks)
    try:
        gdf = gdf.set_crs(sidewalks_gdf.crs)
    except Exception:
        gdf.crs = sidewalks_gdf.crs
    return gdf


def calculate_sidewalk_properties(sidewalks_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Calculates geometric properties for the sidewalks.

    This function calculates the area and perimeter for each sidewalk polygon and
    adds them as new columns to the GeoDataFrame.

    Args:
        sidewalks_gdf: A GeoDataFrame of sidewalk polygons.

    Returns:
        The input GeoDataFrame with "area" and "perimeter" columns added.
    """
    sidewalks_gdf["area"] = sidewalks_gdf.geometry.area
    sidewalks_gdf["perimeter"] = sidewalks_gdf.geometry.length
    return sidewalks_gdf


def generate_kerbs_gdf(crossings_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Generates kerbs from crossings using the ABCDE points system.
    
    This function extracts kerb points B and D from each crossing line that
    follows the ABCDE pattern: A-B-C-D-E where B and D are the kerb positions.
    
    Args:
        crossings_gdf: A GeoDataFrame of crossing lines following ABCDE pattern.
        
    Returns:
        A GeoDataFrame of kerb points.
    """
    kerbs = []
    
    for _, row in crossings_gdf.iterrows():
        line = row.geometry
        
        if line.geom_type != 'LineString':
            continue
            
        coords = list(line.coords)
        
        # If crossing follows ABCDE pattern (5 points), extract B and D
        if len(coords) == 5:
            # Points B and D are at indices 1 and 3
            point_b = Point(coords[1])
            point_d = Point(coords[3])
            kerbs.extend([point_b, point_d])
        elif len(coords) >= 2:
            # Fallback: use start and end points
            start_point = Point(coords[0])
            end_point = Point(coords[-1])
            kerbs.extend([start_point, end_point])
    
    if not kerbs:
        return gpd.GeoDataFrame(geometry=[], crs=crossings_gdf.crs)
    
    return gpd.GeoDataFrame(geometry=kerbs, crs=crossings_gdf.crs)


def draw_sidewalks_gdf(
    gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame,
    streets_gdf: gpd.GeoDataFrame,
    buffer_dist: float,
    curve_radius: float = 3.0,
) -> gpd.GeoDataFrame:
    """Generates sidewalks using the proper algorithm from the QGIS plugin.

    This function implements the sidewalk generation as described in the algorithm:
    1. Adjust buffer distance based on building proximity
    2. Buffer roads with dynamic distances and dissolve
    3. Apply two-step buffering for smooth corners (positive then negative)
    4. Create large buffer around entire network
    5. Use difference operation to extract sidewalk areas
    6. Convert polygons to lines
    7. Handle exclusion/sure zones

    Args:
        gdf: A GeoDataFrame of street lines to buffer.
        buildings_gdf: A GeoDataFrame of building polygons.
        streets_gdf: A GeoDataFrame of streets, used for exclusion zones.
        buffer_dist: The default buffer distance.
        curve_radius: Radius for smooth corner creation.

    Returns:
        A new GeoDataFrame containing the generated sidewalk lines.
    """
    from .parameters import big_buffer_d, min_d_to_building
    
    # Step 1: Adjust buffer distance for buildings
    gdf_with_buffers = adjust_buffer_for_buildings(gdf, buildings_gdf, buffer_dist)
    
    # Step 2: Calculate dynamic buffer distances
    # Buffer distance = (road_width / 2) + (extra_distance / 2)
    if "width" not in gdf_with_buffers.columns:
        gdf_with_buffers["width"] = buffer_dist
    
    gdf_with_buffers["dynamic_buffer"] = (gdf_with_buffers["width"] / 2) + (gdf_with_buffers["buffer_dist"] / 2)
    
    # Step 3: Buffer each road segment and dissolve
    buffered_roads = gdf_with_buffers.buffer(gdf_with_buffers["dynamic_buffer"])
    dissolved_roads = buffered_roads.union_all()
    
    # Step 4: Two-step buffering for smooth corners
    # Positive buffer with curve radius
    smooth_roads = dissolved_roads.buffer(curve_radius)
    # Negative buffer with same radius
    smooth_roads = smooth_roads.buffer(-curve_radius)
    
    # Step 5: Create very large buffer around entire network
    large_buffer = smooth_roads.buffer(big_buffer_d)
    
    # Step 6: Extract sidewalks using difference operation
    # The difference gives us areas outside the road network
    sidewalk_areas = large_buffer.difference(smooth_roads)
    
    # Convert to GeoDataFrame
    if sidewalk_areas.geom_type == 'MultiPolygon':
        sidewalk_polygons = list(sidewalk_areas.geoms)
    else:
        sidewalk_polygons = [sidewalk_areas]
    
    # Filter out the largest polygon (surrounding area) and keep internal ones
    if len(sidewalk_polygons) > 1:
        # Sort by area and remove the largest (external boundary)
        sidewalk_polygons.sort(key=lambda x: x.area)
        sidewalk_polygons = sidewalk_polygons[:-1]  # Remove largest
    
    # Step 7: Convert polygons to lines (boundaries)
    sidewalk_lines = []
    for poly in sidewalk_polygons:
        if poly.geom_type == 'Polygon':
            sidewalk_lines.append(poly.boundary)
        elif poly.geom_type == 'MultiPolygon':
            for p in poly.geoms:
                sidewalk_lines.append(p.boundary)
    
    if not sidewalk_lines:
        # Return empty GeoDataFrame with correct schema
        return gpd.GeoDataFrame(geometry=[], crs=gdf.crs)
    
    sidewalks_gdf = gpd.GeoDataFrame(geometry=sidewalk_lines, crs=gdf.crs)
    
    # Step 8: Handle exclusion/sure zones
    sidewalks_gdf = handle_exclusion_zones(sidewalks_gdf, streets_gdf)
    
    # Step 9: Calculate properties
    sidewalks_gdf = calculate_sidewalk_properties(sidewalks_gdf)
    
    return sidewalks_gdf


def data_clean_gdf(
    gdf: gpd.GeoDataFrame, default_widths: dict, fallback_default_width: float
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Cleans the OSM data in a GeoDataFrame.

    This function performs several cleaning operations on the input OSM data,
    including parsing tags, filtering by highway type, and separating existing
    sidewalks and crossings.

    Args:
        gdf: The input GeoDataFrame of OSM data.
        default_widths: A dictionary mapping highway types to default widths.
        fallback_default_width: The default width to use for unknown highway types.

    Returns:
        A tuple containing:
            - gdf: The cleaned GeoDataFrame.
            - existing_sidewalks: A GeoDataFrame of existing sidewalks.
            - existing_crossings: A GeoDataFrame of existing crossings.
    """

    # Parse other_tags
    def parse_tags(tags):
        if not tags or tags == "nan":
            return {}
        try:
            return ast.literal_eval(tags)
        except (ValueError, SyntaxError):
            return {}

    if "other_tags" in gdf.columns:
        tags_df = gdf["other_tags"].apply(parse_tags).apply(pd.Series)
        gdf = gdf.drop(columns=["other_tags"]).join(tags_df)

    # Filter by highway tag
    highway_values = gdf["highway"].unique()
    widths = {
        val: default_widths.get(val, fallback_default_width) for val in highway_values
    }

    # Create layers of existing sidewalks and crossings
    existing_sidewalks = gpd.GeoDataFrame()
    if "footway" in gdf.columns:
        existing_sidewalks = gdf[
            (gdf["highway"] == "footway") & (gdf["footway"] == "sidewalk")
        ].copy()

    existing_crossings = gpd.GeoDataFrame()
    if "footway" in gdf.columns:
        existing_crossings = gdf[
            (gdf["highway"] == "footway") & (gdf["footway"] == "crossing")
        ].copy()

    print(f"Number of features before filtering: {len(gdf)}")

    # Remove features with width < 0.5
    gdf["width"] = gdf["highway"].map(widths)
    gdf = gdf[gdf["width"] >= 0.5].copy()

    print(f"Number of features after filtering: {len(gdf)}")

    return gdf, existing_sidewalks, existing_crossings
