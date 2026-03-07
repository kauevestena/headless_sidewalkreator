import re

with open("test/test_generic_functions.py", "r") as f:
    content = f.read()

# Remove the inline import
content = content.replace("from headless_sidewalkreator.generic_functions import calculate_sidewalk_properties\n", "")

# Add it to the top import block
import_block = """from headless_sidewalkreator.generic_functions import (
    fetch_street_network_for_bbox,
    polygonize_lines_gdf,
    split_lines_at_intersections,
    remove_lines_from_no_block_gdf,
    filter_and_buffer_protoblocks_gdf,
    draw_crossings_gdf,
    data_clean_gdf,
    split_sidewalks_by_voronoi,
    split_sidewalks_by_protoblock_corners,
    split_sidewalks_by_max_length,
    split_sidewalks_by_num_segments,
    draw_sidewalks_gdf,
    adjust_buffer_for_buildings,
    handle_sidewalk_tags,
    calculate_crossing_direction,
    generate_kerbs_gdf,
    bbox_to_gdf,
    calculate_tangent_direction,
)"""

new_import_block = """from headless_sidewalkreator.generic_functions import (
    fetch_street_network_for_bbox,
    polygonize_lines_gdf,
    split_lines_at_intersections,
    remove_lines_from_no_block_gdf,
    filter_and_buffer_protoblocks_gdf,
    draw_crossings_gdf,
    data_clean_gdf,
    split_sidewalks_by_voronoi,
    split_sidewalks_by_protoblock_corners,
    split_sidewalks_by_max_length,
    split_sidewalks_by_num_segments,
    draw_sidewalks_gdf,
    adjust_buffer_for_buildings,
    handle_sidewalk_tags,
    calculate_crossing_direction,
    generate_kerbs_gdf,
    bbox_to_gdf,
    calculate_tangent_direction,
    calculate_sidewalk_properties,
)"""

content = content.replace(import_block, new_import_block)

with open("test/test_generic_functions.py", "w") as f:
    f.write(content)
