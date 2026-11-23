# Adding the supplied package to your course repository

Extract `Lab06_Processing_v1` into the appropriate lab directory in your existing course repository. The archive contains no Git history. Run the commands below from inside `Lab06_Processing_v1` so `git add .` stages only this package directory.

The shared processor includes the 16 November correction. The intentionally faulty function belongs only to the clearly marked `exercises/file_flush/` directory.

## What belongs in Git

Keep the shared Python modules, schema files, handouts, configurations, extension starter, tests and small captured input bundle. The supplied real `.tif` subsets are part of the reproducible lab reference and are small enough for ordinary Git. They are deliberately included.

The `.gitignore` excludes generated `work/` outputs, local SQLite catalogues and journals, Python caches, editable installation metadata, notebook checkpoints, build outputs, local environments and common credential files. Save personal downloads and processing outputs under `work/`. Do not add them with `git add -f`.

The `.gitattributes` keeps text files at LF line endings on every platform and marks raster/image files as binary. This matters because `check-core` and frozen requests use exact source hashes. Include it in the same commit as the package. Preserve existing repository attributes outside this directory.

## Review, commit and push

```bash
git status --short
```

```bash
git add .
```

```bash
git diff --cached --stat
```

Inspect the staged summary. It should contain the package source, teaching material and bundled real observations. If your repository already had unrelated staged changes, review those before making the commit.

```bash
git commit -m "Add Lab 06 processing package and file flush exercise"
```

```bash
git push
```

The last command assumes your existing course repository already has its upstream branch configured. It publishes the commit to that configured repository.

After cloning or pulling, use the normal installation and demo commands in `README.md`. Editable installs and generated files are created locally rather than committed. The standalone debugging clinic needs only Python, so it can run before installing the processing dependencies.
