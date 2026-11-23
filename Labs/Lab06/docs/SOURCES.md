# Scientific and implementation sources

These are source references for methods and interfaces. The small AOI choices, default mask/coverage policies, assignments and software architecture are course design decisions.

1. Xu, H. (2006). Modification of normalised difference water index (NDWI) to enhance open water features in remotely sensed imagery. International Journal of Remote Sensing, 27(14), 3025–3033. [DOI](https://doi.org/10.1080/01431160600589179). The supplied MNDWI uses green and SWIR1 reflectance. The thresholds 0.0 and 0.15 are teaching comparisons, not universal validated water classifiers.
2. Copernicus [Sentinel-2 processing](https://sentiwiki.copernicus.eu/web/s2-processing) and [products](https://sentiwiki.copernicus.eu/web/s2-products). Source for L2A surface reflectance, native band grids, scene classification and radiometric metadata. SCL is a supplied classification with possible errors; the explicit class exclusions in this course are configurable analysis choices.
3. Element 84 [Earth Search](https://github.com/Element84/earth-search) and [Collection 1 catalogue](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a). The acquisition route is restricted to `sentinel-2-c1-l2a`. It reads actual item/asset metadata and verifies the matching COG header before preserving raw subset values. It does not infer calibration from acquisition date or a legacy offset flag.
4. Rasterio [reprojection](https://rasterio.readthedocs.io/en/stable/topics/reproject.html) and [resampling](https://rasterio.readthedocs.io/en/stable/topics/resampling.html). The implementation uses nearest neighbor for categorical SCL and area averaging for continuous reflectance, after native screening. The strict valid-source fraction is a recorded course policy.
5. USGS [Normalized Difference Moisture Index](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index). A potential extension uses NIR and SWIR1. For Sentinel-2, choose and document the actual NIR band rather than assuming every sensor's bands are interchangeable.
6. SQLite [backup API](https://www.sqlite.org/backup.html) and [table alteration guidance](https://www.sqlite.org/lang_altertable.html). The migration copies the catalogue and validates the table rebuild and foreign keys.

## Delivered observation data

Contains modified Copernicus Sentinel data (2025), accessed through Element 84 Earth Search. The delivered files are actual native-resolution subsets, not generated example scenes.

| Item | Date (UTC) | AOIs |
|---|---|---|
| `S2A_T34UDA_20250604T094637_L2A` | 2025-06-04 | river, east |
| `S2C_T34UDA_20250605T095638_L2A` | 2025-06-05 | river, east |
| `S2B_T34UDA_20250610T095316_L2A` | 2025-06-10 | river, east |

The bboxes are `[19.91,50.04,19.94,50.06]` and `[19.94,50.04,19.97,50.06]`. Each member has red, NIR, green, SWIR1 and SCL. Raw red/NIR came from Lab 05's documented capture; green/SWIR/SCL were acquired for Lab 06. Red/NIR retain the original tight AOI/nodata crop. New bands retain a small native context margin before the final processing mask, so products combining the two capture recipes can have slightly different edge coverage.

`eo_processing/data/fixtures/manifest.json` contains per-file SHA-256, byte sizes, native/subset transforms, calibration, source URLs, capture times and available transfer telemetry. STAC item JSON is included. The resumed mask/band capture has explicitly partial transfer counters; it is not a complete network accounting record. Each delivered raster's checksum and header were independently checked. Reflectance calibration in these delivered C1 files is scale 0.0001 and offset −0.1; SCL is categorical, with scale 1 and offset 0. Processing reads and verifies those recorded values instead of hard-coding them as a rule for every source.
