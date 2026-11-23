"""Freeze product, inputs, grid and mask settings before an attempt exists."""
import platform
from pathlib import Path
import numpy as np
import rasterio
from . import __version__
from .common import canonical, digest, file_hash, read_json, safe_name, write_json, now
from . import database as db
from .products import load_product, parameters_for
from .preparation import target_grid
from .acquisition import check_bbox

DEFAULT_PREPARATION = {"resolution_m": 20, "mask_policy": "scl", "excluded_scl": [0,1,2,3,7,8,9,10,11]}


def environment():
    root = Path(__file__).parent
    processing_files = ("common.py", "database.py", "planning.py", "products.py", "preparation.py", "runner.py", "acquisition.py",
                        "schemas/03_processing.sql", "schemas/04_batches.sql")
    return {"policy": "exact_environment_v1", "package": __version__, "python": platform.python_version(),
            "system": platform.system(), "machine": platform.machine(), "numpy": np.__version__,
            "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__, "proj": rasterio.__proj_version__,
            "processing_code_sha256": {name:file_hash(root/name) for name in processing_files}}


def preparation_settings(values):
    if set(values) - set(DEFAULT_PREPARATION):
        raise ValueError("Unknown preparation settings")
    result = {**DEFAULT_PREPARATION, **values}
    if type(result["resolution_m"]) is not int or result["resolution_m"] not in (10,20,60):
        raise ValueError("resolution_m must be 10, 20 or 60")
    if result["mask_policy"] not in ("scl", "nodata_only"):
        raise ValueError("mask_policy must be scl or nodata_only")
    classes = result["excluded_scl"]
    if not isinstance(classes, list) or any(type(k) is not int or not 0 <= k <= 11 for k in classes):
        raise ValueError("excluded_scl needs SCL class integers")
    result["excluded_scl"] = sorted(set(classes)) if result["mask_policy"] == "scl" else [0,1]
    if not {0,1} <= set(result["excluded_scl"]):
        raise ValueError("Missing and defective observations must be excluded")
    return result


def find_inputs(c, job, required):
    bbox = check_bbox(job["aoi_bbox"])
    aoi = {"crs": "EPSG:4326", "bbox": bbox}
    aoi_key = digest({**aoi, "pixel_rule": "center-inside"})
    result = {}
    if "inputs" in job and set(job["inputs"]) != set(required):
        raise ValueError("Explicit inputs must supply exactly all required roles including scl")
    for role in required:
        if "inputs" in job:
            r = db.record(c, job["inputs"][role])
        else:
            candidates = c.execute("SELECT artifact_id FROM processing_artifacts WHERE json_extract(lineage_json,'$.item_id')=? AND json_extract(lineage_json,'$.aoi_key')=? AND json_extract(lineage_json,'$.asset_key')=?", (job["item_id"], aoi_key, role)).fetchall()
            if len(candidates) != 1:
                raise ValueError(f"Need exactly one registered {role} for {job['item_id']} and bbox {bbox}; found {len(candidates)}. Acquire/register it, or specify exact inputs in this job.")
            r = db.record(c, candidates[0][0])
        if r["lineage"]["item_id"] != job["item_id"] or r["lineage"]["aoi_key"] != aoi_key or r["lineage"]["asset_key"] != role:
            raise ValueError("Explicit input differs from requested scene/AOI/role")
        result[role] = r
    return result


def freeze(config_path, manifest_path):
    config_path, manifest_path = Path(config_path).resolve(), Path(manifest_path).resolve()
    cfg = read_json(config_path)
    if set(cfg) != {"database", "workspace", "max_attempts", "jobs"}:
        raise ValueError("Batch config needs database, workspace, max_attempts, jobs")
    if type(cfg["max_attempts"]) is not int or not 1 <= cfg["max_attempts"] <= 5 or not cfg["jobs"]:
        raise ValueError("Use a nonempty batch and an attempt budget from 1 to 5")
    if manifest_path.exists():
        raise FileExistsError("Manifest exists; run it or choose a new manifest path")
    database = (config_path.parent / cfg["database"]).resolve()
    workspace = (config_path.parent / cfg["workspace"]).resolve()
    members = []; plugin_paths = {}; seen = set(); requests = set()
    with db.connect(database, readonly=True) as c:
        for job in cfg["jobs"]:
            required = {"member_id", "item_id", "aoi_bbox", "product"}
            if not required <= set(job) or set(job)-required-{"plugin", "parameters", "preparation", "inputs"}:
                raise ValueError("Unexpected or missing job fields")
            name = safe_name(job["member_id"])
            if name in seen:
                raise ValueError("Duplicate member_id")
            seen.add(name)
            plugin_path = (config_path.parent / job["plugin"]).resolve() if job.get("plugin") else None
            product, description = load_product(job["product"], plugin_path)
            settings = preparation_settings(job.get("preparation", {}))
            records = find_inputs(c, job, (*product.required_bands, "scl"))
            spec = {"stage": "optical_product_v1", "product": description, "parameters": parameters_for(product, job.get("parameters", {})),
                    "preparation": settings, "grid": target_grid(records, settings["resolution_m"]),
                    "inputs": {role:records[role] for role in sorted(records)}, "environment": environment()}
            request_id = "request-" + digest(spec)
            if request_id in requests:
                raise ValueError("Batch contains the same scientific request twice")
            requests.add(request_id)
            members.append({"member_id": name, "request_id": request_id, "spec": spec})
            if plugin_path:
                plugin_paths[name] = str(plugin_path)
    frozen = {"schema_version": 1, "max_attempts": cfg["max_attempts"], "members": members}
    manifest = {"batch_id": "batch-" + digest(frozen), "frozen": frozen,
                "runtime": {"database": str(database), "workspace": str(workspace), "plugins": plugin_paths,
                            "original_config": config_path.read_text(encoding="utf-8-sig")}}
    with db.writer_lock(database), db.connect(database) as c, c:
        c.execute("INSERT OR IGNORE INTO batches VALUES (?,?,?)", (manifest["batch_id"], canonical(frozen), now()))
        for m in members:
            c.execute("INSERT OR IGNORE INTO batch_members VALUES (?,?,?,NULL,?)", (manifest["batch_id"], m["member_id"], m["request_id"], canonical(m["spec"])))
    write_json(manifest_path, manifest)
    return {"manifest": str(manifest_path), "members": len(members), "attempts_started": 0, "batch_id": manifest["batch_id"]}


def load_manifest(path, check_runtime=False):
    manifest = read_json(path)
    if set(manifest) != {"batch_id", "frozen", "runtime"} or manifest["batch_id"] != "batch-" + digest(manifest["frozen"]):
        raise ValueError("Frozen manifest changed; create a new plan from the editable config")
    for member in manifest["frozen"]["members"]:
        if member["request_id"] != "request-" + digest(member["spec"]):
            raise ValueError("Request fingerprint mismatch")
        if check_runtime:
            if environment() != member["spec"]["environment"]:
                raise ValueError("Core code or processing runtime changed; freeze a new manifest")
            plugin = manifest["runtime"]["plugins"].get(member["member_id"])
            _, description = load_product(member["spec"]["product"]["name"], plugin)
            if canonical(description) != canonical(member["spec"]["product"]):
                raise ValueError("Product code changed; freeze a new manifest")
    return manifest
