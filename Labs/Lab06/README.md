# Lab 06 · A processing package we can extend

Automated Workflows in Satellite Image Processing · Processing Version 1.0.0

Start with [LAB06.md](LAB06.md). It is the main lab handout. Routine work now runs from the terminal. The optional notebook only inspects saved results.

The shared package is supplied complete. Keep `eo_processing/` unchanged. Your own scientific product belongs in `extensions/`, with its configurations in `config/`. Everyone can update the same classroom core while developing different scientific work.

The 16 November file flush correction is included. There is also a short [debugging exercise](exercises/file_flush/README.md) based on that real bug. It reproduces the relevant Windows requirement on any operating system and lets you fix a separate extracted function while keeping the shared core identical.

For adding this clean package to the course repository, see [docs/GIT.md](docs/GIT.md). The archive contains source, small real input subsets and teaching material. Local installation metadata, generated results and catalogues are excluded.

## Quick start

Extract this archive into a new directory inside your course repository and open a terminal there. Use your existing course environment. Install this local package without replacing its dependencies:

```bash
python -m pip install -e . --no-deps --no-build-isolation
```

```bash
python -m eo_processing doctor
```

If a dependency is missing, update the existing environment with `conda env update -f environment.yml`. For a new environment, use `conda env create -f environment.yml`. The environment file retains Jupyter for earlier labs; Lab 06 does not require it to run processing. `requirements.txt` is an alternative for an existing pip environment.

```bash
python -m eo_processing demo --workspace work/demo
```

```bash
python -m eo_processing run --manifest work/demo/batch.json
```

```bash
python -m eo_processing assess --manifest work/demo/batch.json --minimum-valid-fraction 0.5
```

```bash
python -m eo_processing report --manifest work/demo/batch.json --out work/demo/report
```

Open `work/demo/report/index.html`. The demo uses six real requests: three Sentinel-2 dates and two small AOIs near Kraków. All inputs are included. No account, live network connection, or previous lab archive is needed after installing dependencies. Rerun `run` to verify reuse; `demo` deliberately refuses to overwrite a workspace.

## What is here

| Location | Purpose |
|---|---|
| `eo_processing/` | Complete shared processing, acquisition, storage, batch and QC modules |
| `eo_processing/products.py` | Complete MNDWI example and retained NDVI processor |
| `eo_processing/data/fixtures/` | Real raw band/SCL subsets, source STAC records and checksums |
| `extensions/my_product.py` | Starter for your chosen scientific product |
| `config/` | Runnable comparison examples and personal configuration starters |
| `docs/` | Product contract, schema, migration, sources and troubleshooting |
| `queries.sql` | Useful diagnostic SQL; add your own investigations |
| `submission/` | Short report and scientific design templates |
| `tests/` | Shared behavior checks and an optional extension test starter |
| `exercises/file_flush/` | Optional 10–15 minute debugging clinic with a deliberately faulty extracted function |
| `Lab06_Inspect_Results.ipynb` | Optional short viewer; processing works without opening it |

Commands may also use the installed `eo-process` entry point. Examples use `python -m eo_processing` so the active Python environment is explicit. Each terminal instruction is written on one line.

The Version 1 scope is small AOIs, one source tile per request, one optical acquisition per product, and serial processing against a local SQLite catalogue. Multi-date comparisons can be made from completed products with common valid coverage. A processor that directly consumes several dates is a later dependency exercise.

## Continuing earlier work

Keep your Lab 05 directory and database. Follow [docs/MIGRATION.md](docs/MIGRATION.md) to make a migrated copy. The old requests, attempts, artifacts, batch membership and observations remain historical evidence. The supplied demo is a separate working example, not a replacement for that history.

Run `python -m eo_processing check-core` before submitting. The check permits changes in your extension and configurations. It reports changes to the shared Python and SQL files.

The file flush clinic uses only Python's standard library. You can complete it before setting up the processing environment. Edit only `exercises/file_flush/publication.py` for that exercise.
