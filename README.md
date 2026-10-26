# Automated Workflows

Satellite discovery and scientific-input acquisition exercises in `Labs/`.

## Python environment

The project uses uv with Python 3.12, selected by `.python-version`.
Install the locked dependencies and check the interpreter from the repository root:

```bash
uv sync --locked
uv run python --version
uv run python -c "import sys; print(sys.executable)"
```

The shared environment includes Rasterio, NumPy, Matplotlib, JupyterLab and
IPykernel for all three labs. The supplied per-lab requirements files are retained
as course references; `pyproject.toml` and `uv.lock` configure the uv environment.

In PyCharm, select the existing interpreter `.venv/bin/python` in this repository.
The uv executable manages the environment; Python inside `.venv` runs the code.
After an environment rebuild, restart any existing Python consoles or notebook
kernels so they use the new interpreter.

## Checks and notebooks

From the repository root:

```bash
uv run python Labs/Lab02/check_lab02.py
uv run python Labs/Lab03/check_lab03.py
uv run jupyter lab Labs
```

Lab 01's checks are inside `Labs/Lab01_Discovery.ipynb`. Open each notebook from
its own lab folder so its relative paths and working-directory checks agree.
For CLI work, follow the commands in each lab's README. `uv run` can also be used
from a lab folder; uv discovers the root project automatically.

Databases, downloaded images, generated cases, notebook checkpoints and `.venv`
are local runtime files and are excluded from Git. Lab 02's multi-day experiment
continues to use its existing database; installing the environment does not run
discovery or alter its run history.
