"""One catalogue writer, serial attempts, verified reuse and atomic publication."""
import json
import os
from pathlib import Path
import traceback
import uuid
import numpy as np
import rasterio
from rasterio.transform import Affine
from . import database as db
from .common import canonical, digest, file_hash, now, write_json
from .planning import load_manifest
from .products import load_product
from .preparation import prepare, validate_result


def verify_layer(path, spec, attempt_id, role):
    with rasterio.open(path) as src:
        grid = spec["grid"]
        if (src.count != 1 or src.dtypes[0] != "float32" or src.crs.to_string() != grid["crs"]
                or list(src.transform)[:6] != grid["transform"] or [src.height,src.width] != grid["shape"]
                or src.nodata is None or not np.isnan(src.nodata) or src.scales != (1.0,) or src.offsets != (0.0,)):
            raise ValueError("Output raster contract failed")
        tags = src.tags()
        if tags.get("REQUEST_ID") != "request-" + digest(spec) or tags.get("ATTEMPT_ID") != attempt_id or tags.get("ROLE") != role:
            raise ValueError("Output provenance contract failed")
        data = src.read(1)
        if np.isinf(data).any():
            raise ValueError("Infinite output values")
    return data


def result_evidence(c, member):
    """Require every declared output, even when the primary image survives."""
    required = {*member["spec"]["product"]["output_roles"], "valid_mask"}
    rejected = []
    attempts = c.execute("SELECT * FROM processing_attempts WHERE request_id=? AND status='succeeded' ORDER BY started_at DESC,attempt_id DESC", (member["request_id"],)).fetchall()
    for row in attempts:
        try:
            receipt = json.loads(row["receipt_json"])
            if receipt.get("contract") != "optical-product-v1":
                continue
            outputs = c.execute("SELECT * FROM processing_outputs WHERE attempt_id=?", (row["attempt_id"],)).fetchall()
            if {o["role"] for o in outputs} != required or set(receipt["layers"]) != required:
                raise ValueError("Declared output set is incomplete")
            paths = {}
            for o in outputs:
                record = db.record(c, o["artifact_id"])
                path = db.location(c, o["artifact_id"])
                entry = receipt["layers"][o["role"]]
                if record["sha256"] != entry["sha256"] or record["size_bytes"] != entry["size_bytes"]:
                    raise ValueError("Output receipt differs from artifact registry")
                verify_layer(path, member["spec"], row["attempt_id"], o["role"])
                paths[o["role"]] = str(path)
            return {"attempt_id": row["attempt_id"], "paths": paths, "receipt": receipt, "checked_at": now()}, rejected
        except (ValueError, KeyError, OSError, rasterio.errors.RasterioError) as exc:
            rejected.append({"attempt_id": row["attempt_id"], "reason": str(exc)})
    return None, rejected


def inspect_member(c, member, budget, retry_failed=False):
    attempts = c.execute("SELECT attempt_id,status,stage,error_code,error_message,log_path FROM processing_attempts WHERE request_id=? ORDER BY started_at,attempt_id", (member["request_id"],)).fetchall()
    result, rejected = result_evidence(c, member)
    active = c.execute("SELECT attempt_id,request_id FROM processing_attempts WHERE status='running'").fetchone()
    state, reason = "ready", "Inputs can be checked for a new attempt"
    used = sum(a["status"] != "reused" for a in attempts)
    if active and active["request_id"] == member["request_id"]:
        state, reason = "unresolved", "Establish whether the process stopped, then reconcile " + active[0]
    elif result:
        state, reason = "complete", "All declared outputs were verified against the producing attempt"
    elif active:
        state, reason = "blocked", "Catalogue has an unresolved execution: " + active[0]
    elif used >= budget:
        state, reason = "failed", "Persistent attempt budget exhausted"
    elif attempts and attempts[-1]["status"] == "failed" and not retry_failed:
        state, reason = "failed", "Inspect the application error; an explicit retry needs a reason"
    else:
        try:
            for role, frozen in member["spec"]["inputs"].items():
                current = db.record(c, frozen["artifact_id"])
                if canonical(current) != canonical(frozen):
                    raise ValueError("Registered input changed: " + role)
                db.location(c, frozen["artifact_id"])
        except FileNotFoundError as exc:
            state, reason = "blocked", str(exc)
        except (ValueError, OSError) as exc:
            state, reason = "failed", str(exc)
    return {"member_id": member["member_id"], "request_id": member["request_id"], "state": state, "reason": reason,
            "attempts_used": used, "attempts": [dict(a) for a in attempts], "result": result, "rejected_results": rejected}


def observe(c, manifest, member, evidence):
    with c:
        ids=[r["artifact_id"] for r in member["spec"]["inputs"].values()]
        ids += [r[0] for r in c.execute("SELECT o.artifact_id FROM processing_outputs o JOIN processing_attempts a USING(attempt_id) WHERE a.request_id=?",(member["request_id"],))]
        evidence["location_checks"]=db.refresh_locations(c,ids)
        c.execute("INSERT INTO batch_observations(batch_id,member_id,observed_at,state,reason,attempt_id,evidence_json) VALUES (?,?,?,?,?,?,?)",
                  (manifest["batch_id"], member["member_id"], now(), evidence["state"], evidence["reason"],
                   evidence["result"]["attempt_id"] if evidence["result"] else None, canonical(evidence)))


def event(path, **fields):
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(canonical({"time": now(), **fields}) + "\n")


def execute(c, manifest, member, simulate=None, retry_reason=None):
    spec = member["spec"]
    request_id = member["request_id"]
    attempt_id = "attempt-" + uuid.uuid4().hex
    workspace = Path(manifest["runtime"]["workspace"])
    final = workspace / "outputs" / attempt_id
    temp = final.parent / ("." + attempt_id + ".partial")
    log = workspace / "logs" / (attempt_id + ".jsonl")
    temp.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with c:
        c.execute("INSERT OR IGNORE INTO processing_requests VALUES (?,?,?,?,?)", (request_id, digest(spec), spec["stage"], canonical(spec), now()))
        for role, record in spec["inputs"].items():
            c.execute("INSERT OR IGNORE INTO processing_inputs VALUES (?,?,?)", (request_id, role, record["artifact_id"]))
        c.execute("UPDATE batch_members SET request_id=? WHERE batch_id=? AND member_id=?", (request_id, manifest["batch_id"], member["member_id"]))
        c.execute("INSERT INTO processing_attempts(attempt_id,request_id,status,stage,started_at,environment_json,original_config,resolved_config_json,temp_path,final_path,log_path) VALUES (?,?,'running','prepare',?,?,?,?,?,?,?)",
                  (attempt_id, request_id, now(), canonical(spec["environment"]), manifest["runtime"]["original_config"], canonical(spec), str(temp), str(final), str(log)))
    temp.mkdir()
    event(log, attempt_id=attempt_id, stage="prepare", retry_reason=retry_reason)
    try:
        paths = {role: db.location(c, record["artifact_id"]) for role, record in spec["inputs"].items()}
        product, _ = load_product(spec["product"]["name"], manifest["runtime"]["plugins"].get(member["member_id"]))
        bands, valid, inside, grid, metrics = prepare(spec["inputs"], paths, spec["preparation"], product.required_bands)
        if canonical(grid) != canonical(spec["grid"]):
            raise ValueError("Prepared grid differs from the frozen request")
        with c:
            c.execute("UPDATE processing_attempts SET stage='calculate' WHERE attempt_id=?", (attempt_id,))
        event(log, attempt_id=attempt_id, stage="calculate")
        result = product.calculate(bands, valid, spec["parameters"], metrics["pixel_area_m2"])
        usable = validate_result(result, product, valid, inside)
        primary = result.layers[product.primary_role]
        values = primary[usable]
        metrics.update({"valid_pixels": int(usable.sum()), "valid_fraction": float(usable.sum()/inside.sum()),
                        "denominator_or_product_rejected_pixels": int(np.count_nonzero(valid & ~usable)),
                        "minimum": float(values.min()) if values.size else None,
                        "maximum": float(values.max()) if values.size else None,
                        "mean": float(values.mean()) if values.size else None,
                        "outside_nominal_range": int(np.count_nonzero((values < product.nominal_range[0]) | (values > product.nominal_range[1]))) if product.nominal_range else 0,
                        "product_metrics": result.metrics})
        mask = np.full(inside.shape, np.nan, dtype="float32")
        mask[inside] = usable[inside].astype("float32")
        layers = {**result.layers, "valid_mask": mask}
        receipt = {"contract": "optical-product-v1", "request_id": request_id, "attempt_id": attempt_id,
                   "metrics": metrics, "grid": grid, "layers": {}}
        for role, array in layers.items():
            path = temp / (role + ".tif")
            with rasterio.open(path, "w", driver="GTiff", height=grid["shape"][0], width=grid["shape"][1], count=1,
                               dtype="float32", crs=grid["crs"], transform=Affine(*grid["transform"]), nodata=np.nan,
                               compress="deflate", tiled=True, blockxsize=128, blockysize=128) as dst:
                dst.write(array.astype("float32"), 1)
                dst.update_tags(REQUEST_ID=request_id, ATTEMPT_ID=attempt_id, ROLE=role, PRODUCT=product.name,
                                MASK_POLICY=spec["preparation"]["mask_policy"], SOURCE_SPEC_SHA256=digest(spec))
            verify_layer(path, spec, attempt_id, role)
            # Windows fsync requires a writable handle. r+b preserves the file.
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
            receipt["layers"][role] = {"filename": path.name, "sha256": file_hash(path), "size_bytes": path.stat().st_size}
        write_json(temp / "receipt.json", receipt)
        with c:
            c.execute("UPDATE processing_attempts SET stage='publish' WHERE attempt_id=?", (attempt_id,))
        event(log, attempt_id=attempt_id, stage="publish", metrics=metrics)
        if simulate == "crash-before-publish":
            os._exit(87)  # Exercise in an isolated workspace. The OS releases the lock.
        if simulate == "interrupt-before-publish":
            raise InterruptedError("Controlled interruption after real output validation")
        os.replace(temp, final)
        with c:
            for role, entry in receipt["layers"].items():
                artifact = "output-" + digest([request_id, role, entry["sha256"]])
                lineage = {"request_id": request_id, "product": product.name, "role": role}
                c.execute("INSERT OR IGNORE INTO processing_artifacts VALUES (?,NULL,?,?,?,?,?)", (artifact, entry["sha256"], entry["size_bytes"], canonical(grid), canonical(lineage), now()))
                path = str(final / entry["filename"])
                c.execute("INSERT INTO processing_artifact_locations VALUES (?,?,?,'available',?)", (digest([artifact,path]), artifact, path, now()))
                c.execute("INSERT INTO processing_outputs VALUES (?,?,?)", (attempt_id, role, artifact))
            c.execute("UPDATE processing_attempts SET status='succeeded',stage='complete',finished_at=?,receipt_json=? WHERE attempt_id=?", (now(),canonical(receipt),attempt_id))
        event(log, attempt_id=attempt_id, stage="complete")
        return attempt_id
    except BaseException as exc:
        status = "interrupted" if isinstance(exc, (KeyboardInterrupt, InterruptedError)) else "failed"
        with c:
            c.execute("UPDATE processing_attempts SET status=?,finished_at=?,error_code=?,error_message=? WHERE attempt_id=? AND status='running'",
                      (status,now(),type(exc).__name__,str(exc)[:1500],attempt_id))
        event(log, attempt_id=attempt_id, stage=status, error=str(exc), traceback=traceback.format_exc())
        if isinstance(exc, KeyboardInterrupt):
            raise
        return attempt_id


def run(manifest_path, retry_failed=False, reason=None, simulate=None):
    if retry_failed and not reason:
        raise ValueError("An explicit failed retry requires --reason")
    manifest = load_manifest(manifest_path, check_runtime=True)
    database = manifest["runtime"]["database"]
    launched = []
    with db.writer_lock(database), db.connect(database) as c:
        stored = c.execute("SELECT manifest_json FROM batches WHERE batch_id=?", (manifest["batch_id"],)).fetchone()
        if not stored or stored[0] != canonical(manifest["frozen"]):
            raise ValueError("Frozen batch is absent or differs from catalogue")
        for member in manifest["frozen"]["members"]:
            evidence = inspect_member(c, member, manifest["frozen"]["max_attempts"], retry_failed)
            observe(c, manifest, member, evidence)
            if evidence["state"] == "ready":
                launched.append(execute(c, manifest, member, simulate=simulate, retry_reason=reason))
                observe(c, manifest, member, inspect_member(c, member, manifest["frozen"]["max_attempts"]))
        rows = [inspect_member(c, m, manifest["frozen"]["max_attempts"]) for m in manifest["frozen"]["members"]]
    return {"batch_id": manifest["batch_id"], "launched_attempts": launched,
            "complete": all(r["state"] == "complete" for r in rows), "members": rows}


def reconcile(manifest_path, attempt_id, reason):
    if not reason.strip():
        raise ValueError("Record why you concluded the old process stopped")
    manifest = load_manifest(manifest_path)
    with db.writer_lock(manifest["runtime"]["database"]), db.connect(manifest["runtime"]["database"]) as c, c:
        row = c.execute("SELECT * FROM processing_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if not row or row["status"] != "running" or row["request_id"] not in {m["request_id"] for m in manifest["frozen"]["members"]}:
            raise ValueError("Choose a running attempt from this batch")
        c.execute("UPDATE processing_attempts SET status='interrupted',finished_at=?,error_code='explicit_reconciliation',error_message=? WHERE attempt_id=?", (now(),reason,attempt_id))
        event(row["log_path"], attempt_id=attempt_id, stage="reconciled", reason=reason)
    return {"attempt_id":attempt_id,"status":"interrupted","reason":reason}
