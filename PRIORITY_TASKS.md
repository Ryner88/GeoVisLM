# GeoVisLM Priority Tasks

Status labels:

- `[TODO]` not started
- `[IN-PROGRESS]` actively being worked
- `[BLOCKED]` cannot move without another fix or decision
- `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Build Initial Terrain Analysis Pipeline

Goal: create the first working GIS analysis pipeline for DEM terrain data.

Build:

- DEM raster loader
- Slope calculation
- Hillshade generation
- Terrain risk classification
- GeoTIFF export
- CLI runner

Acceptance criteria:

- User can run terrain analysis from the command line.
- Outputs are saved under `outputs/maps/`.
- Generated rasters can be opened in QGIS.
- Pipeline handles missing file errors cleanly.

Why priority: this proves the geospatial foundation before adding AI.

---

### 2. `[TODO]` Add QGIS Workflow Documentation

Goal: document how generated files are opened and styled in QGIS.

Build:

- QGIS import steps
- Layer styling guide
- Recommended color ramps
- Map export instructions
- Screenshots/images folder

Acceptance criteria:

- A user can open generated slope, hillshade, and risk layers in QGIS.
- Documentation includes enough steps to reproduce the map view.
- At least one exported QGIS map image is stored in `docs/diagrams/images/` or `outputs/maps/`.

Why priority: the project needs visible portfolio outputs early.

---

### 3. `[TODO]` Add ParaView Terrain Visualization Script

Goal: generate a first ParaView-compatible visualization script.

Build:

- Convert DEM/raster output into a visualization-friendly format
- Create `paraview_scene.py`
- Load terrain data
- Apply elevation coloring
- Configure camera
- Export render image

Acceptance criteria:

- ParaView or `pvpython` can run the script.
- A terrain render image is exported under `outputs/renders/`.
- Script is documented in the README.

Why priority: ParaView is a major part of the scientific visualization showcase.

---

### 4. `[TODO]` Create GeoMiniLM Dataset Format

Goal: define the training/evaluation format for the small domain-specific LLM.

Build:

- Prompt format
- Workflow JSON format
- Example QGIS workflows
- Example ParaView workflows
- Dataset folder structure

Acceptance criteria:

- At least 20 starter examples exist.
- Each example maps a user request to structured workflow output.
- Dataset can later be used for tokenizer/model training.

Why priority: the custom LLM needs structured data before training.

---

### 5. `[TODO]` Add UML Diagrams and Exported Images

Goal: document the system architecture visually.

Build:

- System architecture diagram
- Component diagram
- Terrain pipeline sequence diagram
- GeoMiniLM workflow diagram
- Export PNG images from PlantUML or Astah

Acceptance criteria:

- `.puml` source files exist under `docs/diagrams/plantuml/`.
- Exported images exist under `docs/diagrams/images/`.
- `docs/UML_DIAGRAMS.md` references all diagrams.
- README links to the UML documentation.

Why priority: diagrams make the project easier to understand and portfolio-ready.
