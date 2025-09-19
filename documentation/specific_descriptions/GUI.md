# QGIS Plugin GUI Workflow

This document describes the user-facing workflow of the OSM SidewalKreator QGIS plugin. The underlying steps are implemented by the headless library, but this describes the process from a user's perspective in the QGIS GUI.

## Step 1: Initial Setup and Data Fetching

1.  **Select Input Area**: The user begins by selecting a polygon layer in QGIS that is currently loaded in the project. From this layer, they select a single polygon feature that defines the desired area of interest for sidewalk generation.

2.  **Fetch OSM Data**: The user clicks a "Get OSM Data" button. This triggers the plugin to:
    *   Calculate the bounding box of the selected polygon.
    *   Construct and send an Overpass API query to fetch all `highway` and `building` features within that area.
    *   The user can set a timeout for the API request in the plugin's settings.

3.  **Populate Highway Widths Table**: Once the data is fetched, the plugin identifies all unique `highway` tag values (e.g., `residential`, `tertiary`, `primary`). It then populates a table in the plugin's dialog window with these values. The user can then manually enter a default width in meters for each type of road. Roads with a width of 0 will be excluded from the sidewalk generation process.

## Step 2: Configure Generation Parameters

The user can configure a variety of parameters in the plugin's dialog to control the sidewalk generation process:

*   **Curve Radius**: Defines the radius for creating smooth, rounded corners at intersections.
*   **Buffer Distance**: An extra distance to add to the road width when creating the initial buffer.
*   **Building Overlap**: The user can enable a check to prevent sidewalks from overlapping existing building polygons.
*   **Dead-end Removal**: The user can specify a number of iterations to remove "dead-end" streets from the road network before processing.

## Step 3: Generate Sidewalks

1.  **Run Processing**: The user clicks the "Run" or "Generate" button to start the main processing task.

2.  **Processing Steps**: The plugin executes the core algorithm in the background, which includes:
    *   Cleaning and preparing the data.
    *   Generating protoblocks.
    *   Drawing sidewalks using the buffering and difference method.
    *   Generating crossings and kerbs.
    *   Splitting the generated sidewalks into segments.

3.  **Live Log**: A log window in the plugin shows the progress of the algorithm, displaying information about each step as it completes.

## Step 4: Review and Output

1.  **Output Layers**: Once the processing is complete, the plugin adds the generated sidewalks, crossings, and kerbs as new layers to the QGIS project. This allows the user to immediately visualize and inspect the results.

2.  **Output Files**: The plugin also saves the generated layers as GeoJSON files in a user-specified output directory. This includes:
    *   Separate files for sidewalks, crossings, and kerbs.
    *   A merged GeoJSON file (`sidewalkreator_output.geojson`) for easy import into JOSM.
    *   Auxiliary files for debugging and reference.
    *   A changeset comment file for OSM uploads.
    *   A JSON file containing all the parameters used for the run.

This GUI-driven workflow allows for an interactive and configurable approach to sidewalk generation, with immediate visual feedback in the QGIS environment.
