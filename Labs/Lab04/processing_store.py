"""Supplied persistence and Lab 3 adapter. The new DDL is student work."""
import contextlib
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TABLES = {
    'processing_artifacts': {'artifact_id','source_artifact_id','sha256','size_bytes','raster_json','lineage_json','created_at'},
    'processing_artifact_locations': {'location_id','artifact_id','local_path','status','checked_at'},
    'processing_requests': {'request_id','fingerprint','stage','normalized_json','created_at'},
    'processing_inputs': {'request_id','role','artifact_id'},
    'processing_attempts': {'attempt_id','request_id','status','stage','started_at','finished_at','environment_json','original_config','resolved_config_json','temp_path','final_path','log_path','receipt_json','error_code','error_message','reused_from_attempt_id'},
    'processing_outputs': {'attempt_id','role','artifact_id'},
}

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def connect(path):
    path = Path(path).resolve()
    c = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=5000')
    return c

def check_shape(c):
    for table, columns in TABLES.items():
        present = {row['name'] for row in c.execute(f'PRAGMA table_info({table})')}
        missing = columns - present
        if missing:
            raise ValueError(f'Complete student_processing_schema.sql: {table} lacks {sorted(missing)}')
    if c.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('Existing foreign key violations: inspect PRAGMA foreign_key_check')

def initialize(path, schema):
    with contextlib.closing(connect(path)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='artifacts'").fetchone():
            raise ValueError('This is not a completed Lab 3 database')
        present = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")} & TABLES.keys()
        if not present:
            try:
                c.executescript('BEGIN;\n' + Path(schema).read_text(encoding='utf-8-sig'))
                check_shape(c)
                c.commit()
            except Exception:
                c.rollback()
                raise
        check_shape(c)
        import_acquired(c)
    return {'database': str(Path(path).resolve()), 'status': 'initialized'}

def import_acquired(c):
    """Add registry links to acquired subsets; leave all Lab 3 rows intact."""
    rows = c.execute('''SELECT f.*, s.asset_id,s.aoi_key,s.aoi_json,s.recipe_version,
        a.collection,a.item_id,a.asset_key,a.metadata_sha256,a.source_url
        FROM artifacts f JOIN subset_requests s USING(subset_id)
        JOIN assets a USING(asset_id) WHERE a.asset_key IN ('red','nir')''').fetchall()
    with c:
        for row in rows:
            artifact_id = 'input-' + row['artifact_id']
            lineage = {key: row[key] for key in ('asset_id','subset_id','aoi_key','recipe_version','collection','item_id','asset_key','metadata_sha256','source_url')}
            lineage['aoi'] = json.loads(row['aoi_json'])
            c.execute('''INSERT OR IGNORE INTO processing_artifacts
                (artifact_id,source_artifact_id,sha256,size_bytes,raster_json,lineage_json,created_at)
                VALUES (?,?,?,?,?,?,?)''',
                (artifact_id,row['artifact_id'],row['sha256'],row['size_bytes'],row['raster_json'],canonical(lineage),now()))
            for loc in c.execute('SELECT * FROM artifact_locations WHERE artifact_id=?', (row['artifact_id'],)).fetchall():
                c.execute('''INSERT OR IGNORE INTO processing_artifact_locations
                    (location_id,artifact_id,local_path,status,checked_at) VALUES (?,?,?,?,?)''',
                    (digest([artifact_id,loc['local_path']]),artifact_id,loc['local_path'],loc['status'],loc['checked_at']))

def input_record(c, artifact_id):
    row = c.execute('SELECT * FROM processing_artifacts WHERE artifact_id=?', (artifact_id,)).fetchone()
    if row is None:
        raise ValueError(f'Unknown artifact ID: {artifact_id}; run init after finishing Lab 3 acquisition')
    result = dict(row)
    result['raster'] = json.loads(result.pop('raster_json'))
    result['lineage'] = json.loads(result.pop('lineage_json'))
    return result

def verified_location(c, artifact_id):
    row = c.execute('SELECT * FROM processing_artifacts WHERE artifact_id=?', (artifact_id,)).fetchone()
    locations = c.execute('''SELECT * FROM processing_artifact_locations WHERE artifact_id=?
        ORDER BY CASE status WHEN 'available' THEN 0 ELSE 1 END,local_path''', (artifact_id,)).fetchall()
    for loc in locations:
        path = Path(loc['local_path'])
        status = 'missing'
        if path.is_file():
            status = 'available' if path.stat().st_size == row['size_bytes'] and file_hash(path) == row['sha256'] else 'corrupt'
        with c:
            c.execute('UPDATE processing_artifact_locations SET status=?,checked_at=? WHERE location_id=?', (status,now(),loc['location_id']))
        if status == 'available':
            return path
    raise FileNotFoundError(f'No verified location for {artifact_id}; inspect processing_artifact_locations')

def record_request(c, fingerprint, normalized, inputs):
    request_id = 'request-' + fingerprint
    with c:
        c.execute('''INSERT OR IGNORE INTO processing_requests
            (request_id,fingerprint,stage,normalized_json,created_at) VALUES (?,?,?,?,?)''',
            (request_id,fingerprint,normalized['stage'],canonical(normalized),now()))
        for role in ('red', 'nir'):
            c.execute('INSERT OR IGNORE INTO processing_inputs VALUES (?,?,?)', (request_id,role,inputs[role]['artifact_id']))
    return request_id

def event(path, **fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(canonical({'time': now(), **fields}) + '\n')

def stage(c, attempt_id, value):
    with c:
        c.execute('UPDATE processing_attempts SET stage=? WHERE attempt_id=?', (value,attempt_id))

def end_attempt(c, attempt_id, status, code=None, message=None):
    with c:
        c.execute('''UPDATE processing_attempts SET status=?,finished_at=?,error_code=?,error_message=?
            WHERE attempt_id=?''', (status,now(),code,str(message)[:1500] if message else None,attempt_id))

def publish(c, attempt, receipt):
    """One short DB transaction, after the validated file has been renamed."""
    artifact_id = 'output-' + digest([attempt['request_id'],receipt['sha256']])
    with c:
        c.execute('''INSERT OR IGNORE INTO processing_artifacts
            (artifact_id,source_artifact_id,sha256,size_bytes,raster_json,lineage_json,created_at)
            VALUES (?,NULL,?,?,?,'{}',?)''',
            (artifact_id,receipt['sha256'],receipt['size_bytes'],canonical(receipt['validation']),now()))
        c.execute('''INSERT OR IGNORE INTO processing_artifact_locations
            (location_id,artifact_id,local_path,status,checked_at) VALUES (?,?,?,'available',?)''',
            (digest([artifact_id,attempt['final_path']]),artifact_id,attempt['final_path'],now()))
        c.execute('INSERT INTO processing_outputs VALUES (?,?,?)', (attempt['attempt_id'],'ndvi',artifact_id))
        c.execute('''UPDATE processing_attempts SET status='succeeded',stage='complete',finished_at=?,
            error_code=NULL,error_message=NULL WHERE attempt_id=?''', (now(),attempt['attempt_id']))
    return artifact_id
