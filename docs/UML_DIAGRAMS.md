# GeoVisLM UML Diagrams

This document tracks architecture and workflow diagrams for GeoVisLM.

## Diagram Source

PlantUML source files are stored in:

```text
docs/diagrams/plantuml/
```

Exported images are stored in:

```text
docs/diagrams/images/
```

Optional Astah project files are stored in:

```text
docs/diagrams/astah/
```

## Diagrams

### 1. System Architecture

Source:

```text
docs/diagrams/plantuml/system_architecture.puml
```

Image:

```text
docs/diagrams/images/system_architecture.png
```

Purpose:

Shows the high-level GeoVisLM architecture: dashboard, GIS engine, ParaView engine, GeoMiniLM, reporting, and storage.

---

### 2. Component Diagram

Source:

```text
docs/diagrams/plantuml/component_diagram.puml
```

Image:

```text
docs/diagrams/images/component_diagram.png
```

Purpose:

Shows the internal software modules and how they communicate.

---

### 3. Terrain Pipeline Sequence

Source:

```text
docs/diagrams/plantuml/terrain_pipeline_sequence.puml
```

Image:

```text
docs/diagrams/images/terrain_pipeline_sequence.png
```

Purpose:

Shows the first MVP flow from DEM upload to terrain outputs.

---

### 4. GeoMiniLM Workflow

Source:

```text
docs/diagrams/plantuml/geominilm_workflow.puml
```

Image:

```text
docs/diagrams/images/geominilm_workflow.png
```

Purpose:

Shows how the domain-specific LLM converts user requests into structured GIS and visualization workflows.

## Exporting PlantUML Images

If PlantUML is already installed, export all diagrams with:

```bash
JAVA_TOOL_OPTIONS=-Djava.awt.headless=true plantuml -tpng docs/diagrams/plantuml/*.puml -o ../images
```

If a desktop/headless setting is not needed in your environment, this also works:

```bash
plantuml -tpng docs/diagrams/plantuml/*.puml -o ../images
```

Do not treat missing PlantUML as a project failure. The `.puml` files are the source of truth and can be exported later.

## Astah Option

If using Astah instead of PlantUML:

1. Create the UML diagram in Astah.
2. Export the diagram as PNG.
3. Save the image under:

```text
docs/diagrams/images/
```

4. Optionally save the Astah project file under:

```text
docs/diagrams/astah/
```

Do not replace the PlantUML files unless the Astah diagram becomes the source of truth.
