# GeoVisLM Priority Tasks

Status labels:

- `[TODO]` not started
- `[IN-PROGRESS]` actively being worked
- `[BLOCKED]` cannot move without another fix or decision
- `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add UML Diagrams and Exported Images

Goal: document the system architecture visually.

Build:

- system architecture PlantUML diagram
- component diagram
- terrain pipeline sequence diagram
- GeoMiniLM workflow diagram
- exported PNG images under `docs/diagrams/images/`

Acceptance criteria:

- `.puml` files exist under `docs/diagrams/plantuml/`
- exported images exist under `docs/diagrams/images/`
- `docs/UML_DIAGRAMS.md` references every diagram
- README links to `docs/UML_DIAGRAMS.md`

Why priority: diagrams make the project easier to understand and portfolio-ready.

---

### 2. `[TODO]` Add QGIS Workflow Documentation

Goal: document how generated GeoTIFF outputs should be opened and styled in QGIS.

Build:

- QGIS import steps
- slope layer styling guide
- hillshade layer styling guide
- terrain risk layer styling guide
- map export instructions
- screenshot/export placeholder locations

Acceptance criteria:

- A user can open `slope_degrees.tif`, `hillshade.tif`, and `terrain_risk.tif` in QGIS.
- Documentation explains layer order and styling.
- README links to the QGIS workflow document.

Why priority: the project needs visible portfolio outputs early.

---

### 3. `[TODO]` Add ParaView Terrain Visualization Script

Goal: create the first ParaView-compatible terrain visualization script.

Build:

- script placeholder under `geovis_lm/viz/`
- documented input/output expectations
- output location under `outputs/renders/`
- future support for `pvpython` or ParaView GUI execution

Acceptance criteria:

- Script exists and is documented.
- README explains how ParaView will be used.
- Priority task notes current limitation if ParaView is not installed.

Why priority: ParaView is a major part of the scientific visualization showcase.

---

### 4. `[TODO]` Create GeoMiniLM Dataset Format

Goal: define the dataset format for the custom geospatial/scientific visualization LLM.

Build:

- dataset folder structure
- starter JSONL format
- prompt-to-workflow examples
- QGIS workflow examples
- ParaView workflow examples

Acceptance criteria:

- At least 10 starter examples exist.
- Each example has an instruction, inputs, expected workflow, and explanation.
- Format is documented.

Why priority: the custom LLM needs structured data before training.
