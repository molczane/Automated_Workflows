# Lab 04: one configured NDVI job

Version 1.0 · 22 October 2026 · Automated Workflows in Satellite Image Processing

Open `Lab04_Configured_NDVI_v1_20261022.ipynb` from this extracted folder. Keep its
companion files beside it. The notebook is the lab guide; Python files define the
job that a future workflow manager can call.

Use the existing satellite-workflows conda environment. `environment_semester.yml`
is the unchanged semester environment for an optional fresh installation. The
minimal packages needed here can be added with this single command:

```bash
conda install -c conda-forge numpy rasterio pyyaml matplotlib jupyterlab ipykernel
```

Run each command below separately from the folder containing `lab04_cli.py`.
They use ordinary Python arguments and work in PowerShell, Git Bash and Linux.
The application itself was validated on Linux; Windows was not available for a
runtime test. No GPU or cluster is needed.

## What you build

1. Write six table definitions in `student_processing_schema.sql` using the contract.
2. Repair request identity in `repair_functions.py`.
3. Repair input compatibility and NDVI arithmetic in the same file.
4. Run the job and use SQL to explain a missing input and a killed process.

The wrapper, publication and reconciliation code are supplied. Most coding effort
goes into database design and three short logical repairs. Read
`CALIBRATION_REVIEW.md` before computing this particular sample: its original
offset metadata conflict, and the explicit interpretation is part of the request.

Approximate pace: 120 minutes in class, then 45–60 minutes to finish the second
failure case, evidence and explanations. The notebook marks the extension after
rename as optional. All imagery used by the checks and cases is real.

## Check the repairs

The unedited student edition should fail all four groups. That is intentional.
You can run each group independently while working, then run them together.

```bash
python check_lab04.py --part schema
```

```bash
python check_lab04.py --part identity
```

```bash
python check_lab04.py --part pair
```

```bash
python check_lab04.py --part ndvi
```

```bash
python check_lab04.py --part all
```

The schema check is a minimum set of behavioral checks, not a complete proof that
every database constraint is present. Use the full contract when reviewing your SQL.

## Continue from your own Lab 3 work

Copy your completed Lab 3 catalogue and initialize the processing extension:

```bash
python lab04_cli.py init --from-lab3 "C:/path/to/Lab03/state/catalogue.sqlite" --database state/catalogue.sqlite
```

Replace the example source path with your real path. The source database is opened
read only and copied using SQLite backup; its acquired files remain at their
recorded paths. Keep that Lab 3 folder available. Initialization leaves its records
intact and adds the new tables to the copy. On later init calls, omit --from-lab3.

List the imported input IDs:

```bash
python lab04_cli.py inputs --database state/catalogue.sqlite
```

If there is exactly one red and one NIR candidate:

```bash
python lab04_cli.py configure --database state/catalogue.sqlite --out config/ndvi.yml
```

If there are several candidates, select a matching scene/AOI pair explicitly:

```bash
python lab04_cli.py configure --database state/catalogue.sqlite --red YOUR_RED_ARTIFACT_ID --nir YOUR_NIR_ARTIFACT_ID --out config/ndvi.yml
```

Inspect the generated file. The IDs are real records from your catalogue. Runtime
paths resolve relative to the YAML file; the generated configuration uses absolute
paths for clarity. `configure` refuses to overwrite an existing file.

```bash
python lab04_cli.py plan --config config/ndvi.yml
```

```bash
python lab04_cli.py run --config config/ndvi.yml
```

Repeat the last command. With unchanged code/configuration and verified inputs and
output, it records a new invocation with status reused under the same request.
Use --force to execute again deliberately and retain a separate output:

```bash
python lab04_cli.py run --config config/ndvi.yml --force
```

## Preserved real input route

If you need a common class example or your Lab 3 archive is unavailable, use the
actual small AOI subsets bundled with Lab 3. They occupy about 150 kB together.
This is an explicit local import of preserved real data, not a live catalogue or
download operation. It imports the documented source scene/asset/AOI history and
records zero network bytes. It does not replace data during an attempted live read.

After all checks pass:

```bash
python lab04_cli.py demo
```

```bash
python lab04_cli.py plan --config demo/config/ndvi.yml
```

```bash
python lab04_cli.py run --config demo/config/ndvi.yml
```

The demo refuses to overwrite an existing folder. To create an additional independent
workspace, pass a different --directory. The notebook defaults to this shared
example; change its CONFIG variable when using your own catalogue.

## Failure cases

Each command creates a separate workspace under cases/ from the same preserved
real inputs and your current schema. Cases do not alter your main inputs or outputs.
A case name can be created once. Inspect an existing case rather than regenerating
it. Predict the database/file state before recovering it.

Missing red input; the command intentionally exits with code 1:

```bash
python lab04_cli.py case --name missing-input
```

```bash
python lab04_cli.py report --config cases/missing-input/config/ndvi.yml
```

```bash
python lab04_cli.py restore-input --config cases/missing-input/config/ndvi.yml
```

```bash
python lab04_cli.py run --config cases/missing-input/config/ndvi.yml
```

Process death after temporary output validation; expected exit code 86:

```bash
python lab04_cli.py case --name before-rename
```

The child process really exits without running a cleanup handler. Its attempt
remains running and its valid temporary raster remains unpublished. Get the exact
attempt ID from the report or the notebook. The parent case command has waited for
the child to exit, so its stopped state is established for this exercise.

```bash
python lab04_cli.py report --config cases/before-rename/config/ndvi.yml
```

```bash
python lab04_cli.py reconcile --config cases/before-rename/config/ndvi.yml --attempt-id YOUR_ATTEMPT_ID --confirm-stopped
```

```bash
python lab04_cli.py run --config cases/before-rename/config/ndvi.yml
```

Reconciliation quarantines the temporary file, marks the old attempt interrupted
and allows a new attempt of the same request. Retrying before reconciliation is
deliberately blocked. --confirm-stopped is a factual assertion about that process;
it is not a scheduler query. Do not use it to claim an active worker has died.

Optional: repeat with `case --name after-rename`. There the final file exists but
the output transaction is absent. Reconciliation checks the pre-rename receipt,
checksum, grid, statistics and provenance tags, then adopts it into the database.
No recalculation is needed. An unverified final file is quarantined.

## Evidence and limitations

```bash
python lab04_cli.py report --config demo/config/ndvi.yml --out evidence/main_report.json
```

Use your own config path if appropriate. Submit the repaired functions, schema,
completed notebook, diagnostic queries and small reports. Keep data, output rasters,
databases and logs out of Git. Keep your actual files locally so you can demonstrate
the lineage. Reports contain local paths; inspect them before making them public.

The stage requires matching grids and source scene/AOI lineage. It applies
calibration before arithmetic, handles nodata/denominators and records coverage.
It does not mask clouds, resample, mosaic, schedule workers or prove scientific
suitability. Display scaling must never silently clip the saved NDVI raster.

Temporary and final files live on the same filesystem. The rename and SQLite
commit are separate operations, which is why recovery exists. This demonstrates
process interruption recovery on a local filesystem; it does not claim power-loss
durability or safe concurrent operation on a shared network filesystem. Keep one
active process per catalogue. Container/Gaia deployment remains a later step when
the supported runtime and launch settings are known.

Sources: [Rasterio data API](https://rasterio.readthedocs.io/en/stable/api/rasterio.io.html),
[Rasterio masks](https://rasterio.readthedocs.io/en/stable/topics/masks.html),
[Python os.replace](https://docs.python.org/3.11/library/os.html#os.replace), and
[SQLite foreign keys](https://www.sqlite.org/foreignkeys.html).
