# Lab 05 · A batch we can restart and explain

Lecture 5 discussed evaluating results. This is the separate practical Lab 05. It extends the configured optical job from Lab 4 into six expected requests: three actual Sentinel-2 acquisitions and two small Kraków AOIs.

Start with `Lab05_Restartable_Optical_Batch_v1_20261105.ipynb`. Write the three new tables, repair the three functions in `batch_repairs.py`, and keep the SQL that explains your investigations. The completed earlier modules are supplied so unfinished work from another lab does not prevent this exercise.

The core path uses captured real imagery. It makes no network requests. Inputs are copied into a new workspace; the preserved fixtures remain intact. No cloud mask is applied. Finite NDVI coverage and scientific suitability are separate claims.

## Start

Run these commands from the extracted package directory. Each command is one line. Your existing course environment should already provide NumPy, Rasterio, Matplotlib, PyYAML and JupyterLab. `environment.yml` describes a separate environment for this lab if needed.

`python check_lab05.py all`

`python lab05_cli.py setup --directory work`

`python lab05_cli.py plan --manifest work/batch.json`

`python lab05_cli.py run --manifest work/batch.json`

`python lab05_cli.py report --manifest work/batch.json --output reports/first`

Open `reports/first/index.html` in a browser. It is a static report with links from counts to exact members, verification detail, attempt history, a contact sheet and a consistent catalogue snapshot. Repeating a report uses a new output directory so earlier reports remain available.

Checks fail until your schema and repairs are finished. `setup` refuses to overwrite a workspace. A rerun uses `run`, not another setup. Runtime paths resolve from the manifest; moving a complete workspace requires updating its runtime paths and registered artifact locations. Changing only the output directory does not change scientific identity.

## Core failure drills

`python lab05_cli.py case --name missing-input --directory cases/missing`

`python lab05_cli.py restore-input --manifest cases/missing/batch.json`

`python lab05_cli.py run --manifest cases/missing/batch.json`

`python lab05_cli.py case --name interrupted-worker --directory cases/worker`

Inspect `processing_attempts` to obtain the running attempt ID. The case helper waited for that child process to exit. Record that evidence before the next command. Substitute the actual ID.

`python lab05_cli.py reconcile --manifest cases/worker/batch.json --attempt-id ATTEMPT_ID --confirm-stopped`

`python lab05_cli.py run --manifest cases/worker/batch.json`

The flag records your assertion that the process stopped. It does not contact a scheduler or prove that assertion itself. The two cases return exit code 1 because the batch is incomplete. That is expected evidence, not a reason to reset the database.

## Extensions

`python lab05_cli.py case --name interrupted-coordinator --directory cases/coordinator`

That command exits abruptly with code 87 after the first result. Restart normally:

`python lab05_cli.py run --manifest cases/coordinator/batch.json`

`python lab05_cli.py case --name missing-output --directory cases/output`

`python lab05_cli.py refresh --manifest cases/output/batch.json`

`python lab05_cli.py run --manifest cases/output/batch.json`

`refresh` performs current file checks and appends observations without launching a job. `plan` inspects without writing. `report` exports recorded observations; opening a new report does not itself refresh file evidence.

## Use your own completed Lab 4 catalogue

Use configurations created by the supplied Lab 4 CLI or equivalent completed configurations. All inputs must already be registered; all configurations in a batch must use the same catalogue. The new schema must be completed first.

`python lab05_cli.py freeze --config path/to/scene_a.yml --config path/to/scene_b.yml --out my_batch.json --workspace my_batch_work`

`python lab05_cli.py run --manifest my_batch.json`

The manifest freezes the current scientific specifications, including the exact processing code/runtime identity. A changed code/runtime or scientific setting needs a new manifest. Storage locations and batch bookkeeping code are not scientific inputs. Existing successful products are verified before reuse, even if a previous catalogue observation said available.

## Explicit live acquisition

The regular data route is Earth Search v1, collection `sentinel-2-c1-l2a`. The script uses the pinned scene IDs and AOIs in `acquire_fixtures.py`, bounded range reads and preserved source metadata. It refuses a full tile fallback. Expect about 12 MiB of actual source range responses for the supplied selection, with possible provider changes or failures.

`python acquire_fixtures.py --destination acquired_c1`

`python lab05_cli.py setup --directory live_work --fixtures acquired_c1`

A failed live download exits with code 1. It never substitutes captured data silently. Choose a new destination after investigating a partial download. The separate captured route remains available explicitly.

## Execution limits

Use a local exercise workspace where a file synchronizer will not restore deliberately moved files. Use one processing command at a time for a catalogue. The Lab 05 coordinator uses an operating system lock that is released on exit. The older Lab 4 CLI does not participate in that lock, so do not run it independently alongside the batch. A running application attempt blocks new calculations until it is resolved. This is serial coordination, not a distributed queue or worker ownership protocol.

The budget is two non reused application attempts per scientific request, counted across batches and restarts. A blocked input uses no attempt. An ordinary application failure requires investigation. A reconciled interruption or a missing output can consume the next permitted attempt. Changing scientific settings to evade a retry budget is not a repair.

Exit codes: 0 completed command; 1 incomplete batch or deliberate scientific job failure; 2 setup/configuration problem; 87 the isolated coordinator crash exercise. Worker exit 86 is captured and recorded by the adapter.
