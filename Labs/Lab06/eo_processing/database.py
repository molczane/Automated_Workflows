"""Original request/attempt/artifact contracts, generalized to named products."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import uuid
from .common import canonical, digest, file_hash, now

SCHEMAS = Path(__file__).parent / "schemas"


@contextmanager
def connect(database, create=False, readonly=False):
    path = Path(database).resolve()
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rwc" if create else "?mode=rw"), uri=True)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=5000")
    try:
        yield c
    finally:
        c.close()


@contextmanager
def writer_lock(database):
    """Same advisory lock name as Lab 05. All Version 1 writers use it."""
    path = Path(database).with_suffix(".lab05.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt
                stream.seek(0)
                stream.write(b"0")
                stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another writer holds this catalogue") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def initialize(database):
    if Path(database).exists():
        raise FileExistsError("Database exists; use it or migrate a copy")
    with writer_lock(database), connect(database, create=True) as c:
        for path in sorted(SCHEMAS.glob("*.sql")):
            c.executescript(path.read_text())
        with c:
            c.execute("INSERT INTO processing_schema_migrations VALUES (1,?,?)", (now(), "Named input assets and independent scientific QC"))
    return str(Path(database).resolve())


def migrate_copy(source, destination):
    """Back up through SQLite, broaden assets, retain every historical identifier."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination:
        raise FileExistsError("Choose a new destination for the migrated copy")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with writer_lock(source), connect(source, readonly=True) as old:
        if old.execute("SELECT 1 FROM processing_attempts WHERE status='running'").fetchone():
            raise ValueError("Resolve running attempts in the original Lab 05 workspace before migration")
        with connect(destination, create=True) as new:
            old.backup(new)
    try:
        with connect(destination) as c:
            if c.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Source catalogue has foreign key violations")
            # Disable FK enforcement only outside a transaction for SQLite's documented table rebuild.
            c.execute("PRAGMA foreign_keys=OFF")
            c.execute("BEGIN IMMEDIATE")
            try:
                schema = (SCHEMAS / "02_subsets.sql").read_text().split("CREATE TABLE subset_requests")[0]
                c.execute(schema.replace("CREATE TABLE assets (", "CREATE TABLE assets_v1_new ("))
                c.execute("INSERT INTO assets_v1_new SELECT * FROM assets")
                c.execute("DROP TABLE assets")
                c.execute("ALTER TABLE assets_v1_new RENAME TO assets")
                if c.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Migration foreign key validation failed")
                c.commit()
            except Exception:
                c.rollback()
                raise
            c.execute("PRAGMA foreign_keys=ON")
            c.executescript((SCHEMAS / "05_scientific_qc.sql").read_text())
            with c:
                c.execute("INSERT OR IGNORE INTO processing_schema_migrations VALUES (1,?,?)", (now(), "Copied from " + str(source)))
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or c.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Migrated catalogue validation failed")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"source": str(source), "database": str(destination), "history": "preserved", "paths": "Original input/output locations retained"}


def register_bundle(database, directory):
    """Import real subsets, with acquisition history and source-artifact links."""
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if not manifest.get("complete") or manifest["collection"] != "sentinel-2-c1-l2a":
        raise ValueError("Require a complete Collection 1 input bundle")
    for member in manifest["members"]:
        for e in member["bands"].values():
            path = directory / e["file"]
            if path.stat().st_size != e["size_bytes"] or file_hash(path) != e["sha256"]:
                raise ValueError("Input bundle checksum failed: " + str(path))
    stamp = now()
    run_id = "bundle-" + uuid.uuid4().hex
    with writer_lock(database), connect(database) as c, c:
        if not c.execute("SELECT 1 FROM processing_schema_migrations WHERE version=1").fetchone():
            raise ValueError("Use a Version 1 catalogue or migrate first")
        stream = "lab06-captured-" + digest(manifest)[:16]
        c.execute("INSERT OR IGNORE INTO streams VALUES (?,?,?)", (stream, canonical({"manifest": manifest}), stamp))
        c.execute("INSERT INTO runs(run_id,stream_key,started_at,finished_at,status,search_until,command,config_json) VALUES (?,?,?,?,'succeeded',?,'register_bundle',?)",
                  (run_id, stream, stamp, stamp, manifest["downloaded_at"], canonical({"manifest_sha256": file_hash(directory / "manifest.json"), "registration_network_bytes": 0})))
        for member in manifest["members"]:
            item = json.loads((directory / member["item_file"]).read_text())
            c.execute("INSERT OR IGNORE INTO scenes VALUES (?,?,?,?,?,?,?)", (item["collection"], item["id"], item["properties"]["datetime"], item["properties"].get("eo:cloud_cover"), canonical(item["assets"]), stamp, stamp))
            for role, e in member["bands"].items():
                meta = item["assets"][role]
                asset = digest([item["collection"], item["id"], role, digest(meta)])
                aoi = {"crs": "EPSG:4326", "bbox": e["plan"]["aoi_bbox"]}
                aoi_key = digest({**aoi, "pixel_rule": "center-inside"})
                subset = digest([asset, aoi_key, e["plan"]["recipe"]])
                artifact = digest([subset, e["sha256"]])
                acq_attempt = "import-" + artifact
                c.execute("INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?)", (asset, item["collection"], item["id"], role, meta["href"], canonical(meta), digest(meta), stamp))
                c.execute("INSERT OR IGNORE INTO subset_requests(subset_id,asset_id,aoi_key,aoi_json,recipe_version,status,updated_at) VALUES (?,?,?,?,?,'pending',?)", (subset, asset, aoi_key, canonical(aoi), e["plan"]["recipe"], stamp))
                c.execute("INSERT OR IGNORE INTO download_attempts(attempt_id,subset_id,run_id,status,stage,started_at,network_bytes) VALUES (?,?,?,'running','register',?,0)", (acq_attempt, subset, run_id, stamp))
                c.execute("INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?,?)", (artifact, subset, acq_attempt, e["sha256"], e["size_bytes"], canonical(e["plan"]), stamp))
                local = str(directory / e["file"])
                c.execute("INSERT OR IGNORE INTO artifact_locations VALUES (?,?,?,'available',?)", (digest([artifact, local]), artifact, local, stamp))
                c.execute("UPDATE download_attempts SET status='succeeded',stage='complete',finished_at=?,artifact_id=? WHERE attempt_id=? AND status='running'", (stamp, artifact, acq_attempt))
                c.execute("UPDATE subset_requests SET status='ready',latest_artifact_id=? WHERE subset_id=?", (artifact, subset))
                pid = "input-" + artifact
                lineage = {"collection": item["collection"], "item_id": item["id"], "asset_key": role, "aoi_key": aoi_key, "aoi": aoi, "recipe_version": e["plan"]["recipe"], "source_url": meta["href"], "metadata_sha256": digest(meta)}
                c.execute("INSERT OR IGNORE INTO processing_artifacts VALUES (?,?,?,?,?,?,?)", (pid, artifact, e["sha256"], e["size_bytes"], canonical(e["plan"]), canonical(lineage), stamp))
                c.execute("INSERT OR IGNORE INTO processing_artifact_locations VALUES (?,?,?,'available',?)", (digest([pid, local]), pid, local, stamp))
    return {"registered_members": len(manifest["members"]), "database": str(database)}


def record(c, artifact_id):
    row = c.execute("SELECT * FROM processing_artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()
    if not row:
        raise ValueError("Unknown artifact: " + artifact_id)
    value = dict(row)
    value.pop("created_at")  # Registration time does not change scientific identity.
    value["raster"] = json.loads(value.pop("raster_json"))
    value["lineage"] = json.loads(value.pop("lineage_json"))
    return value


def location(c, artifact_id):
    artifact = record(c, artifact_id)
    for row in c.execute("SELECT * FROM processing_artifact_locations WHERE artifact_id=? ORDER BY local_path", (artifact_id,)):
        p = Path(row["local_path"])
        if p.is_file() and p.stat().st_size == artifact["size_bytes"] and file_hash(p) == artifact["sha256"]:
            return p
    raise FileNotFoundError("No verified copy for " + artifact_id)


def refresh_locations(c, artifact_ids):
    """Refresh file availability without changing historical attempt outcomes."""
    checks=[]
    for artifact_id in sorted(set(artifact_ids)):
        artifact=record(c,artifact_id)
        for row in c.execute("SELECT * FROM processing_artifact_locations WHERE artifact_id=?",(artifact_id,)).fetchall():
            p=Path(row["local_path"])
            try:
                status="missing" if not p.is_file() else "available" if p.stat().st_size==artifact["size_bytes"] and file_hash(p)==artifact["sha256"] else "corrupt"
            except OSError:
                status="corrupt"
            stamp=now()
            c.execute("UPDATE processing_artifact_locations SET status=?,checked_at=? WHERE location_id=?",(status,stamp,row["location_id"]))
            checks.append({"artifact_id":artifact_id,"path":str(p),"status":status,"checked_at":stamp})
    return checks
