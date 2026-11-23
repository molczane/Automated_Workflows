# Adding a scientific product

Keep the class package under `eo_processing/` unchanged. Put your product in a Python file under `extensions/`. Importing a chosen file is deliberate code execution, so use your own code or code you have reviewed. The configuration names the exact file; the package does not scan arbitrary folders or load products automatically.

The supplied `MNDWI` in `eo_processing/products.py` is a complete example. `extensions/my_product.py` is your starter. A product exports an object named `PRODUCT` with these fields:

| Field | Meaning |
|---|---|
| `name`, `version` | Stable product identifier and your revision |
| `required_bands` | Asset roles such as `blue`, `green`, `red`, `nir`, `swir16`, `swir22`, `rededge1` |
| `output_roles` | Named raster outputs such as `index` and `classification` |
| `primary_role` | Output whose finite pixels define usable product coverage |
| `nominal_range` | Expected range for the primary output, or `None`; this is a QC expectation, not a clipping instruction |
| `default_parameters` | Named numeric scientific parameters; the configuration may override them |
| `calculate(...)` | Function returning a `ProductResult` |

The function receives `bands`, `valid`, `parameters`, and `pixel_area_m2`. Each band is already calibrated reflectance on the declared common grid. `valid` is a Boolean array combining the AOI, source availability, and selected SCL screening. Do not divide input bands by 10,000 or apply another offset. The raw values are preserved in the acquisition bundle, where the original calibration metadata can be inspected.

Return `ProductResult({role: array, ...}, metrics)`. Every array must have the same two-dimensional shape as the prepared inputs. Use float values and NaN for unknown observations, including categorical outputs. A class of 0 is a real class; it must not double as nodata. Keep all finite outputs inside the supplied valid mask. Additional filtering is allowed if your primary output and other outputs consistently record the resulting unknown pixels.

`metrics` must be JSON compatible, with ordinary Python numeric values or `None` when no statistic exists. Convert NumPy scalars using `float()` or `int()`. Empty selections need explicit handling. Save at least one metric that helps answer your scientific question.

The runner writes the arrays, checks the grids and provenance, records artifacts and attempts, creates `valid_mask`, and generates a report. The product code should not open the catalogue, select scenes, download data, create attempts, or write output files.

## Choosing preparation

The default preparation excludes SCL classes 0, 1, 2, 3, 7, 8, 9, 10 and 11. It retains vegetation, nonvegetated ground, and water. This conservative policy is an explicit starting choice.

For a snow product, remove class 11 from `excluded_scl`. For a product restricted to land, you can add class 6 if that restriction is scientifically appropriate. Do not automatically select SCL vegetation alone for vegetation change: changing cover could then disappear from the analysis. Record and justify the actual policy in the configuration.

The common preparation aligns SCL by nearest neighbor, converts native raw observations to reflectance, masks native invalid observations, and uses area averaging for continuous reflectance when aligning grids. It requires at least 0.999 valid source coverage in an output footprint. The AOI uses pixel centers. A 10 m output from a SWIR product still contains 20 m native SWIR information. Use 20 m for the supplied MNDWI.

The package accepts one scene per request and small AOIs contained in one tile. All outputs use one common projected grid. Multi-date algorithms, non-raster outputs, complex parameter objects and another sensor need an expanded contract in a later release. You can still compare separately produced dates after restricting the comparison to common valid coverage.

## Request identity and revisions

The manifest includes product source hash/version, required bands and outputs, parameters, input identities/checksums/calibration, AOI/grid, mask policy and the processing code/runtime. A changed personal product source produces a different request when you plan again. Changing only another person's extension has no effect on your product.

Output directories, log paths, registration timestamps and file copy locations do not define scientific equivalence. Processing hashes are deliberately strict in this teaching release, following Lab 05's exact runtime policy. A Python, GDAL or processing-code change requires a new plan; earlier results remain historical records. Reporting, command routing and scientific assessment code are outside this processing hash, so updating those alone does not change the scientific request. `check-core` separately checks all shared Python/SQL files for classroom consistency.

Scientific QC criteria are separate: changing a coverage acceptance threshold appends an assessment to the same measured product. It does not recalculate reflectance or change its cloud mask.

## Checks to add

Choose a check that could catch a real mistake: band order, sign, missing scaling, denominator behavior, invalid observation handling, or a known location whose behavior should make sense. A second copy of the same implementation is weak evidence. Use independent arithmetic or an independently justified reference. Tiny numeric arrays can test edge cases; scientific maps and reported findings must use actual observations.
