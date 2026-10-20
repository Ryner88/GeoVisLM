# Data Sources and Licensing Register

Status: planning. Selection here does not mean a connector or ingestion job is
implemented. Review provider terms and coverage again when each source is
activated. The roadmap uses integer phases: its Phase 5 was discussed as
Phase 4, and its Phase 6 as Phase 4.5.

| Source | Roadmap use | Access | Selection and provenance requirement |
| --- | --- | --- | --- |
| [USGS 3DEP / The National Map](https://www.usgs.gov/faqs/what-types-elevation-datasets-are-available-what-formats-do-they-come-and-where-can-i-download) | Phase 1 | No account or API key for National Map downloads | Primary U.S. [bare-earth DEM](https://data.usgs.gov/datacatalog/data/USGS%3A35f9c4d4-b113-4c8d-8691-47c428c29a5b). Record product ID, resolution, acquisition or publication date, vertical datum, download URL, and checksum. Distinguish DEMs from surface models. |
| [Geofabrik / OpenStreetMap](https://download.geofabrik.de/) | Phase 1 | No API key for extracts | Primary U.S. buildings and roads. Record extract region and date, OSM data timestamp if supplied, feature filters, and source attribution. |
| [Microsoft U.S. Building Footprints](https://github.com/microsoft/USBuildingFootprints) | Phase 1 | No API key for published downloads | Supplemental building coverage. Record release, footprint vintage where available, and duplicate-resolution rule before combining with OSM. |
| [OpenTopography Global Datasets API](https://opentopography.org/developers) | Optional Phase 1; later global elevation | API key required for API | Optional where 3DEP is unsuitable or unavailable. It is not a Phase 1 blocker. Check dataset-specific terrain versus surface semantics and API-key terms before use. |
| [Census Data API](https://www.census.gov/data/developers/guidance/api-user-guide/query-components.html) and [TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Later population exposure slice | API key recommended for production traffic; TIGER downloads are separate | Join estimates to matching geography and vintage; record dataset, variables, margin of error where provided, boundary vintage, and allocation method. TIGER boundaries alone contain no demographic estimates. |
| [NOAA / NWS API](https://www.weather.gov/documentation/services-web-API) | Phase 5, formerly 4 | No API key currently; configured User-Agent required | Record observation or forecast issue and valid times, source endpoint, and application contact. |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/map_key/) | Phase 5, formerly 4 | Free MAP_KEY required | Record sensor, detection time, retrieval time, and product; treat detections as observations, not confirmed fire perimeters. |
| [USGS Water Data APIs](https://api.waterdata.usgs.gov/docs/ogcapi/keys/) | Phase 5, formerly 4 | Key optional; higher limits with key | Record station, parameter, observation time, units, provisional status when supplied, and retrieval time. |
| [Google Open Buildings](https://sites.research.google/gr/open-buildings/) | Phase 6, formerly 4.5 | No API key for published data | Consider for international building coverage. Published V3 coverage spans Africa, South and Southeast Asia, Latin America, and the Caribbean; it is not a source for the first U.S. footprint milestone. Record version, geography, confidence threshold, and attribution. |

## First U.S. exposure-analysis input set

Use a bare-earth USGS 3DEP DEM and a dated Geofabrik OSM extract for buildings
and roads. Use Microsoft U.S. footprints only as supplemental building coverage
after inspecting local quality and deduplicating overlaps. Pin the exact files
and checksums in the evidence record. Check that the DEM, hazard raster, and
vector features share an explicit coordinate reference and that units used for
area and length are appropriate. Do not treat footprint completeness as known;
report missing coverage and source disagreement as uncertainty.

OpenTopography, Census, FIRMS, Hugging Face, and hosted LLM credentials are not
required to start this milestone. Phase 1 implementation begins only when the
AI roadmap work is authorized; the source choices and registry can be prepared
before then.

## Census key and traffic rule

The Census API permits up to 500 queries per IP address per day without a key.
Its [user guide](https://www.census.gov/content/dam/Census/data/developers/api-user-guide/api-user-guide.pdf)
also treats application-wide requests cumulatively, including requests from
users on different IP addresses. A Census API key is not strictly required for
initial testing. Obtain a free key before production-scale population analysis
to accommodate aggregate application traffic. Cache by dataset, geography,
vintage, and variable set; budget and monitor total requests.

## Licensing register and publication gate

| Dataset | Published terms to record | Release check |
| --- | --- | --- |
| USGS 3DEP | U.S. government source and product citation/metadata | Preserve product attribution and download metadata. |
| OSM via Geofabrik | [ODbL 1.0 and OSM attribution](https://www.openstreetmap.org/copyright/en) | Review attribution and database-sharing obligations for the intended output and any combined dataset before publication. |
| Microsoft U.S. footprints | [ODbL](https://github.com/microsoft/USBuildingFootprints) for the named U.S. release | Record exact release and review obligations before combining or redistributing. |
| Google Open Buildings V3 | [CC BY 4.0 or ODbL 1.0](https://sites.research.google/gr/open-buildings/), at the user's choice | Record selected license and attribution for any later use. |
| All other sources | Provider-specific access and reuse terms | Add exact dataset/version terms before use or redistribution. |

The register is a review checklist, not a blanket conclusion that mixed-source
derived data may be redistributed. Keep the original source and license for
each layer so published maps and reports can show the required attribution.

## Minimum source-record fields

For every acquired layer, record provider, dataset/product ID, version or
vintage, source URL, retrieval time, geographic bounds, CRS and vertical datum
where relevant, units, resolution or feature scale, file hash, access method,
license/attribution, transformation history, quality checks, and known gaps.
The Phase 1 evidence schema should reference these immutable source records.
