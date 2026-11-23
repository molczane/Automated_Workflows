"""The batch extension records expected work and append only observations."""
import contextlib
import json
import os
import sqlite3
from pathlib import Path
import processing_store as store

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT/'student_batch_schema.sql'
STATES = ('ready','complete','blocked','unresolved','failed')

@contextlib.contextmanager
def connect(database,create=False):
    if str(database)==':memory:' or create:
        c=sqlite3.connect(database)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
    else:
        c = store.connect(database)
    try:
        yield c
    finally:
        c.close()

@contextlib.contextmanager
def writer_lock(database):
    """OS releases this advisory lock on process exit, including abrupt exit."""
    path = Path(database).with_suffix('.lab05.lock')
    with path.open('a+b') as stream:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Another Lab 05 writer holds this catalogue; wait for it to stop') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

def initialize(c):
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = tables & {'batches','batch_members','batch_observations'}
    if not present:
        try:
            c.executescript('BEGIN;\n'+SCHEMA.read_text(encoding='utf-8-sig'))
            check_shape(c)
            c.commit()
        except Exception:
            c.rollback(); raise
    check_shape(c)

def check_shape(c):
    required = {'batches': {'batch_id','manifest_json','created_at'},
                'batch_members': {'batch_id','member_id','planned_request_id','request_id','spec_json'},
                'batch_observations': {'observation_id','batch_id','member_id','observed_at','state','reason','attempt_id','evidence_json'}}
    for table, fields in required.items():
        actual = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
        if not fields <= actual:
            raise ValueError(f'Complete student_batch_schema.sql: {table} needs {sorted(fields-actual)}')

def register(c, manifest):
    frozen = manifest['frozen']
    key = manifest['batch_id']
    existing = c.execute('SELECT manifest_json FROM batches WHERE batch_id=?',(key,)).fetchone()
    if existing and existing[0] != store.canonical(frozen):
        raise ValueError('Batch identity collision or changed frozen manifest')
    with c:
        c.execute('INSERT OR IGNORE INTO batches VALUES (?,?,?)',(key,store.canonical(frozen),store.now()))
        for m in frozen['members']:
            c.execute('''INSERT OR IGNORE INTO batch_members
                (batch_id,member_id,planned_request_id,request_id,spec_json) VALUES (?,?,?,NULL,?)''',
                (key,m['member_id'],m['request_id'],store.canonical(m['spec'])))

def observe(c, manifest, member, result):
    with c:
        cur = c.execute('''INSERT INTO batch_observations
            (batch_id,member_id,observed_at,state,reason,attempt_id,evidence_json)
            VALUES (?,?,?,?,?,?,?)''', (manifest['batch_id'],member['member_id'],store.now(),
            result['state'],result['reason'],result.get('attempt_id'),store.canonical(result)))
        for loc in result.get('location_checks',[]):
            c.execute('UPDATE processing_artifact_locations SET status=?,checked_at=? WHERE location_id=?',
                      (loc['status'],loc['checked_at'],loc['location_id']))
    return cur.lastrowid

def attach_request(c, manifest, member):
    spec = member['spec']
    inputs = {r['role']: r for r in spec['inputs']}
    fingerprint = member['request_id'].removeprefix('request-')
    actual = store.record_request(c,fingerprint,spec,inputs)
    with c:
        c.execute('UPDATE batch_members SET request_id=? WHERE batch_id=? AND member_id=?',
                  (actual,manifest['batch_id'],member['member_id']))
