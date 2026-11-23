# Your scientific product and AOIs

Choose a small WGS84 bbox in the order west, south, east, north. A few kilometers across is enough to start. Use an AOI with features relevant to your scientific question and acquisition dates suitable for observing them.

Search for actual Collection 1 scene IDs. This command is a runnable Kraków example; change its bbox and dates for your location:

```bash
python -m eo_processing search --bbox 19.91 50.04 19.94 50.06 --interval 2025-06-01T00:00:00Z/2025-06-15T23:59:59Z --max-items 20 --out work/search_results.json
```

The result records whether the item limit was reached. Search follows pagination until that explicit limit or the end. Tile cloud cover is a screening hint; inspect cloud coverage inside your actual AOI after acquisition. Do not assume two overlapping tile records are two independent dates.

Edit `config/personal_acquisition.json`. Replace the placeholder item IDs, choose your bbox or bboxes, and list every band declared by your extension plus `scl`. Supported reflectance roles are `blue`, `green`, `red`, `nir` (B08), `nir08` (B8A), `rededge1`, `rededge2`, `rededge3`, `swir16`, and `swir22`. The source item must advertise the requested assets.

Each AOI must be contained in each selected tile. If different AOIs need different scenes, create separate acquisition configurations/bundles and register them into the same catalogue. Product requests can then combine the appropriate scene/AOI pairs without creating a Cartesian product accidentally.

```bash
python -m eo_processing acquire --config config/personal_acquisition.json --destination work/personal/inputs
```

```bash
python -m eo_processing init --database work/personal/catalogue.sqlite
```

```bash
python -m eo_processing register --database work/personal/catalogue.sqlite --bundle work/personal/inputs
```

If you already created or migrated the catalogue, skip `init` and use the existing file. `init` refuses to replace it.

Acquisition reads bounded windows from public COGs. It preserves raw stored values, native grids, scale/offset metadata, source URLs, STAC item records, checksums and transfer evidence. It refuses a server that ignores byte ranges and rejects metadata/header calibration disagreement. A small native context margin supports grid alignment during processing. There is no fallback to complete tile downloads or generated imagery.

The limits are one million native pixels per subset, 24 MiB per band/scene range session, 256 MiB overall, up to four AOIs, and twelve selected items. A failed acquisition bundle remains explicitly incomplete. Inspect the error, choose a new destination and retry deliberately. It cannot be registered as successful.

Edit `config/personal_batch.json`. Set your actual product name and plugin file, select only appropriate scene/AOI jobs, and ensure the bbox matches acquisition exactly. Paths in configuration files are relative to that configuration file. Paths in generated manifests are resolved absolute paths for the current machine. Do not hand-edit the frozen science specification.

```bash
python -m eo_processing plan --config config/personal_batch.json --out work/personal/batch.json
```

```bash
python -m eo_processing run --manifest work/personal/batch.json
```

```bash
python -m eo_processing assess --manifest work/personal/batch.json --minimum-valid-fraction 0.5
```

```bash
python -m eo_processing report --manifest work/personal/batch.json --out work/personal/report
```

For a reproducibility handoff, retain the input bundle, editable configuration, extension and frozen manifest. A manifest records the original resolved paths; on another machine, register the same bundle and freeze the same scientific configuration with appropriate local runtime paths. Do not discard the original manifest or claim the new machine has the same exact runtime unless its recorded environment agrees.
