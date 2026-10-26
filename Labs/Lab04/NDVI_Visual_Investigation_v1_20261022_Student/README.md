# Extra credit: the program finished, but can you trust the map?

This folder contains actual downloaded Sentinel-2 red and NIR subsets from Lab 3,
the captured catalogue metadata, and a short diagnostic script. It performs no
network requests and never changes the input rasters.

Use the environment from the labs. The script needs NumPy, Rasterio and Matplotlib.
If these are missing:

```bash
conda install -c conda-forge numpy rasterio matplotlib
```

From this extracted folder:

```bash
python ndvi_visual_check.py --show
```

Omit --show when you only want saved files. The script saves a map and full value
distribution in visual_check_output/ndvi_visual_check.png, input metadata and
statistics in ndvi_visual_check.json, and twelve actual pixels to investigate
in pixels_to_investigate.csv. The printed row and column indices start at zero.

To inspect your own downloaded, matching red/NIR AOI subsets:

```bash
python ndvi_visual_check.py --red "path/to/red_subset.tif" --nir "path/to/nir_subset.tif" --out-dir my_visual_check --show
```

## Your investigation

The program finishes, and its input files are readable. Decide whether the output
is scientifically credible. Use both the map and the distribution. The map uses a
fixed display range; distinct colors expose values outside it. The histogram
includes all finite results and uses logarithmic tails so large outliers remain
visible. A display limit never changes the calculated values.

1. Identify two specific observations that merit investigation. Quantify them.
   A green or attractive map is not sufficient evidence of a correct product.
2. Trace at least one unusual output pixel from its source integer values through
   every arithmetic step. Use the CSV, and verify the calculation independently.
3. Inspect the script, the GeoTIFF metadata and the captured provider metadata.
   Develop competing explanations and show which evidence supports each one.
4. Propose one controlled change. Retain the original files, change one assumption
   at a time, and compare maps, value distributions and valid pixel counts. Explain
   why the change addresses a cause rather than hiding a symptom.
5. Distinguish what you have demonstrated from what still requires independent
   evidence. Describe a useful further check against a source product or authoritative
   description of its pixel representation.

For nonnegative red and NIR reflectances, NDVI lies between -1 and 1. Negative
calibrated reflectances can complicate that expectation, so values outside that
interval are a reason to investigate, not a universal proof of a particular bug.
The script does not screen clouds. It deliberately retains Lab 3's masking rule
so that you can inspect the original behavior.

Submit a short bug report, your comparison figures, the modified script or code
diff, and a worked example using an actual pixel. Include input checksums so
someone else can repeat your investigation. Explain why clipping values or hiding
outliers would not establish that the underlying calculation is correct.

Suggested length: 400–700 words plus figures and code. Evidence and a clear
explanation matter more than guessing a particular fix.

Data: Sentinel-2 L2A item S2C_34UDA_20250605_0_L2A; B04 and B08; AOI
[19.91, 50.04, 19.94, 50.06], EPSG:4326, extracted to the native 10 m grid.
Source URLs, extraction plans and hashes are in data/aoi_manifest.json.
The image files were actually downloaded for Lab 3 and preserved unchanged.
