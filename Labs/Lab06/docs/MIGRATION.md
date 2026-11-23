# Bringing Lab 05 forward

The supplied package is a consolidated successor. It includes the acquisition and processing schema contracts and completed batch behavior. It does not require the old script directories to be on Python's import path.

Run the common Lab 06 demo first. Keep your earlier directory. Do not copy these modules over a running Lab 05 workspace or overwrite its database.

Stop the old coordinator and any directly launched worker. Resolve any running attempts in Lab 05 using the earlier reconciliation procedure. Then create a migrated catalogue copy. Replace the example source path with your actual catalogue path:

```bash
python -m eo_processing migrate --database ../Lab05/work/catalogue.sqlite --destination work/continued/catalogue.sqlite
```

```bash
python -m eo_processing integrity --database work/continued/catalogue.sqlite
```

Migration uses SQLite's backup API, rebuilds only the acquisition `assets` table to broaden its band constraint, adds scientific QC support, and verifies integrity and foreign keys. It preserves rows and identifiers in all earlier tables. The source database remains unchanged. Migration refuses a destination that already exists.

The copied catalogue retains earlier absolute input and output locations. Keep those files where they are, or register another verified bundle/copy deliberately. Copying a database does not copy its imagery. This release does not rewrite earlier file paths automatically.

Earlier requests and batch manifests keep their old scientific definitions. The Version 1 CLI expects new Version 1 manifests and does not rerun old manifests with changed processing code. Freeze a new configuration pointing to the migrated database. New products get new requests. Earlier succeeded attempts stay succeeded and remain inspectable through SQL.

Acquire and register needed green/SWIR/SCL or other bands with the commands in `OWN_AOIS.md`. Acquisition retains one scene identity and the same bbox for every band in a request. If several registered artifacts match a scene/AOI/role, planning asks you to provide explicit `inputs` rather than guessing. `python -m eo_processing inputs --database work/continued/catalogue.sqlite` lists the IDs. An optional `inputs` object in a job maps each required band and `scl` to one artifact ID.

The OS lock uses the same `.lab05.lock` filename as the old coordinator. All Version 1 writers respect it. Older direct Lab 04 worker commands did not use that lock; do not run them against the same catalogue during this transition. Version 1 remains serial. A process pool or concurrent scheduler needs a different execution/ingestion design later.

## Keeping the class core synchronized

Use this directory as the shared release in your existing course repository. Everyone starts with identical `eo_processing/` contents. Put scientific divergence in `extensions/` and personal configurations. Keep the extension path explicit in each configuration.

Before pulling a later release, commit your extension, configurations and report as usual. Resolve an upstream change to shared code once as a class. Do not distribute individually refactored copies of the runner. If you find a core bug, save the minimal failing configuration and discuss a common correction.

The core verification command checks released Python and SQL hashes and reports added core Python/SQL files. It deliberately ignores personal extensions, documentation, configuration and result files.
