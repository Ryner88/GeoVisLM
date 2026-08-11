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

Reference rendering:

```text
docs/diagrams/images/system_architecture.png
```

Purpose:

Shows the current staging deployment topology: Cloudflare ingress, optional Cloudflare Access protection, Caddy reverse proxy, first-party dashboard authentication, project collaboration, file-backed jobs, worker polling, optional PostGIS metadata, and shared output storage.

---

### 2. Component Diagram

Source:

```text
docs/diagrams/plantuml/component_diagram.puml
```

Reference rendering:

```text
docs/diagrams/images/component_diagram.png
```

Purpose:

Shows the deployed runtime components and their boundaries for first-party sessions, projects, memberships, comments, audit events, the file-backed job queue, worker polling, PostGIS metadata, shared storage, and public ingress.

---

### 3. Terrain Pipeline Sequence

Source:

```text
docs/diagrams/plantuml/terrain_pipeline_sequence.puml
```

Reference rendering:

```text
docs/diagrams/images/terrain_pipeline_sequence.png
```

Purpose:

Shows the dashboard-driven terrain workflow: authenticated project access, persisted run inputs, queued job record, worker execution, GIS analysis, artifact/report writes, and dashboard output retrieval.

---

### 4. GeoMiniLM Workflow

Source:

```text
docs/diagrams/plantuml/geominilm_workflow.puml
```

Reference rendering:

```text
docs/diagrams/images/geominilm_workflow.png
```

Purpose:

Shows GeoMiniLM prototype inference as TF-IDF retrieval plus handwritten template fallback, with dashboard integration explicitly blocked until a future production gate passes.

---

### 5. GeoMiniLM Evaluation Gate

Source:

```text
docs/diagrams/plantuml/geominilm_evaluation_gate.puml
```

Reference rendering:

```text
docs/diagrams/images/geominilm_evaluation_gate.png
```

Purpose:

Shows the corrected evaluation boundary: grouped development evaluation, versioned retriever plus template code candidate, frozen regression benchmark, future sealed shadow set, manifest/leakage/semantic/category/confidence checks, candidate lock, and dashboard authorization decision.

---

### 6. GeoMiniLM Training Roadmap

Source:

```text
docs/diagrams/plantuml/geominilm_training_roadmap.puml
```

Reference rendering:

```text
docs/diagrams/images/geominilm_training_roadmap.png
```

Purpose:

Shows the next GeoMiniLM development loop: the explicit priorities of language
robustness, multi-step GIS composition, and confidence/abstention; scenario
grouping and grouped holdouts; candidate lock; one-shot frozen production gate;
deployment eligibility conditions; and the currently blocked Prime deployment
and dashboard integration states. Geospatial correctness, artifact contracts,
recovery behavior, and cross-tool routing are modeled as cross-cutting concerns.

## Exporting PlantUML Images

If PlantUML is already installed, export all diagrams with:

```bash
JAVA_TOOL_OPTIONS=-Djava.awt.headless=true plantuml -tpng docs/diagrams/plantuml/*.puml -o ../images
```

If a desktop/headless setting is not needed in your environment, this also works:

```bash
plantuml -tpng docs/diagrams/plantuml/*.puml -o ../images
```

Do not treat missing PlantUML as a project failure. The `.puml` files are the
canonical source of truth and can be exported later. PNG files are reference
renderings generated from those sources.

## Astah Option

If using Astah instead of PlantUML:

1. Use the matching `.puml` source from `docs/diagrams/plantuml/` as the
   canonical reference.
2. Import it if your Astah installation supports PlantUML import, or manually
   recreate the packages, components, dependencies, actors, databases, and notes.
3. Export the diagram as PNG.
4. Save the image under:

```text
docs/diagrams/images/
```

5. Optionally save the Astah project file under:

```text
docs/diagrams/astah/
```

Do not replace the PlantUML files unless the Astah diagram explicitly becomes
the source of truth.

The GeoMiniLM training roadmap is intentionally written with standard UML
packages, components, dependencies, actors, databases, and notes so it can be
used as an Astah recreation reference without relying on PlantUML-only C4
macros. Automatic round-trip conversion is not assumed.
