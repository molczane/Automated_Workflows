"""One CLI for the notebook, terminal and later workflow manager."""
import argparse
import contextlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import yaml
import ndvi_job as job
import processing_store as store

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / 'student_processing_schema.sql'

def write_config(database, path, red=None, nir=None):
    path = Path(path).resolve()
    selected_records = {}
    with contextlib.closing(store.connect(database)) as c:
        rows = c.execute('SELECT artifact_id,lineage_json FROM processing_artifacts WHERE source_artifact_id IS NOT NULL').fetchall()
        options = {'red': [], 'nir': []}
        for row in rows:
            options[json.loads(row['lineage_json'])['asset_key']].append(row['artifact_id'])
        chosen = {'red':red, 'nir':nir}
        for role in chosen:
            if chosen[role] is None:
                if len(options[role]) != 1:
                    raise ValueError(f'{role} has {len(options[role])} candidates; use inputs, then pass explicit --red and --nir IDs')
                chosen[role] = options[role][0]
            selected_records[role] = store.input_record(c, chosen[role])
    cfg = {'database': str(Path(database).resolve()),
           'science': {**job.DEFAULT_SCIENCE, 'inputs': chosen},
           'runtime': {'output_dir': str(path.parent.parent / 'outputs'),
                       'log_dir': str(path.parent.parent / 'logs')}}
    manifest = json.loads((ROOT/'fixtures/aoi_manifest.json').read_text())
    if all(selected_records[role]['sha256']==manifest[role]['sha256'] for role in ('red','nir')):
        cfg['science']['scaling']='reviewed_calibration'
        cfg['science']['calibration']={role:{'sha256':selected_records[role]['sha256'],'scale':0.0001,'offset':0.0,
            'evidence':'Lab04 CALIBRATION_REVIEW.md: exact captured COG subsets; provider boa_offset_applied=true and DN distributions support offset 0. Teaching interpretation; no independent JP2 radiometric comparison.'} for role in ('red','nir')}
    if path.exists():
        raise FileExistsError(f'Configuration exists: {path}; edit it explicitly or choose --out')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
    return {'config':str(path), 'inputs':chosen,'scaling':cfg['science']['scaling'],
            'calibration_review':'Read CALIBRATION_REVIEW.md before running this sample'}

def setup_demo(directory):
    """Recreate a documented Lab 3 snapshot using actual preserved subset bytes."""
    directory = Path(directory).resolve()
    if directory.exists():
        raise FileExistsError(f'Case/workspace already exists: {directory}')
    # Validate that all requested tables exist before leaving a partially built demo.
    with contextlib.closing(sqlite3.connect(':memory:')) as trial:
        trial.row_factory = sqlite3.Row
        trial.execute('PRAGMA foreign_keys=ON')
        trial.executescript((ROOT/'support/lab02_base_schema.sql').read_text())
        trial.executescript((ROOT/'support/lab03_reference_schema.sql').read_text())
        trial.executescript(SCHEMA.read_text())
        store.check_shape(trial)
    directory.mkdir(parents=True)
    (directory/'inputs').mkdir()
    database = directory / 'catalogue.sqlite'
    manifest = json.loads((ROOT/'fixtures/aoi_manifest.json').read_text())
    snapshot = json.loads((ROOT/'fixtures/real_catalogue.json').read_text())
    item = next(item for page in snapshot['pages'] for item in page['features'] if item['id']=='S2C_34UDA_20250605_0_L2A')
    stamp = store.now()
    with contextlib.closing(sqlite3.connect(database)) as c:
        c.execute('PRAGMA foreign_keys=ON')
        c.executescript((ROOT/'support/lab02_base_schema.sql').read_text())
        c.executescript((ROOT/'support/lab03_reference_schema.sql').read_text())
        with c:
            c.execute('INSERT INTO scenes VALUES (?,?,?,?,?,?,?)',
                      (item['collection'],item['id'],item['properties']['datetime'],item['properties'].get('eo:cloud_cover'),store.canonical(item['assets']),stamp,stamp))
            c.execute('INSERT INTO streams VALUES (?,?,?)', ('captured-inputs',store.canonical({'source':'Lab 3 actual captured imagery; no live search'}),item['properties']['datetime']))
            c.execute('''INSERT INTO runs (run_id,stream_key,started_at,finished_at,status,search_until,command,config_json)
                VALUES ('fixture-import','captured-inputs',?,?,'succeeded',?,'import_captured_lab03',?)''',
                (stamp,stamp,item['properties']['datetime'],store.canonical({'source':'Lab 3 bundled actual AOI subsets','network_bytes':0})))
            for role in ('red','nir'):
                entry = manifest[role]
                original = ROOT/'fixtures'/entry['file']
                if store.file_hash(original) != entry['sha256']:
                    raise ValueError('Bundled real imagery checksum differs from the source manifest')
                local = directory/'inputs'/(role+'.tif')
                shutil.copy2(original,local)
                meta = item['assets'][role]
                metadata_sha = store.digest(meta)
                asset_id = store.digest([item['collection'],item['id'],role,metadata_sha])
                aoi = {'crs':'EPSG:4326','bbox':entry['plan']['aoi_bbox']}
                aoi_key = store.digest({**aoi,'pixel_rule':'center-inside'})
                subset_id = store.digest([asset_id,aoi_key,entry['plan']['recipe']])
                artifact_id = store.digest([subset_id,entry['sha256']])
                attempt_id = 'import-'+role
                c.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?,?)', (asset_id,item['collection'],item['id'],role,meta['href'],store.canonical(meta),metadata_sha,stamp))
                c.execute('''INSERT INTO subset_requests
                    (subset_id,asset_id,aoi_key,aoi_json,recipe_version,status,updated_at)
                    VALUES (?,?,?,?,?,'pending',?)''', (subset_id,asset_id,aoi_key,store.canonical(aoi),entry['plan']['recipe'],stamp))
                c.execute('''INSERT INTO download_attempts
                    (attempt_id,subset_id,run_id,status,stage,started_at,network_bytes)
                    VALUES (?,?,'fixture-import','running','register',?,0)''', (attempt_id,subset_id,stamp))
                c.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)',
                          (artifact_id,subset_id,attempt_id,entry['sha256'],entry['size_bytes'],store.canonical(entry['plan']),stamp))
                c.execute("INSERT INTO artifact_locations VALUES (?,?,?,'available',?)", (store.digest([artifact_id,str(local)]),artifact_id,str(local),stamp))
                c.execute("UPDATE download_attempts SET status='succeeded',stage='complete',finished_at=?,artifact_id=? WHERE attempt_id=?", (stamp,artifact_id,attempt_id))
                c.execute("UPDATE subset_requests SET status='ready',latest_artifact_id=? WHERE subset_id=?", (artifact_id,subset_id))
    store.initialize(database,SCHEMA)
    config = directory/'config'/'ndvi.yml'
    write_config(database,config)
    return {'database':str(database),'config':str(config),'source':'Real Sentinel-2 AOI subsets preserved in Lab 3; no new downloads'}

def inputs(database):
    with contextlib.closing(store.connect(database)) as c:
        return [dict(row) for row in c.execute('''SELECT f.artifact_id,f.sha256,
            json_extract(f.lineage_json,'$.item_id') AS item_id,
            json_extract(f.lineage_json,'$.asset_key') AS band,
            json_extract(f.lineage_json,'$.aoi_key') AS aoi_key,l.local_path,l.status
            FROM processing_artifacts f LEFT JOIN processing_artifact_locations l USING(artifact_id)
            WHERE f.source_artifact_id IS NOT NULL ORDER BY item_id,aoi_key,band''')]

def report(cfg):
    with contextlib.closing(store.connect(cfg['database'])) as c:
        return {'database':str(cfg['database']), 'generated_at':store.now(),
                **{name:[dict(row) for row in c.execute(f'SELECT * FROM {name}')] for name in store.TABLES}}

def create_case(name):
    directory = ROOT/'cases'/name
    result = setup_demo(directory)
    note = {'case':name,'config':result['config']}
    if name == 'missing-input':
        original = directory/'inputs'/'red.tif'
        held = original.with_suffix('.held.tif')
        original.rename(held)
        note.update(original=str(original),held=str(held))
    (directory/'case_note.json').write_text(store.canonical(note),encoding='utf-8')
    command = [sys.executable,str(ROOT/'lab04_cli.py'),'run','--config',result['config'],'--force']
    if name != 'missing-input':
        command += ['--simulate',name]
    child = subprocess.run(command,capture_output=True,text=True)
    result.update(case=name,exit_code=child.returncode,child_stdout=child.stdout.strip(),child_stderr=child.stderr.strip())
    cfg = job.load_config(result['config'])
    result['attempts'] = report(cfg)['processing_attempts']
    return result,child.returncode

def restore_input(cfg):
    directory = cfg['_config_path'].parent.parent
    note = json.loads((directory/'case_note.json').read_text())
    original,held = Path(note['original']),Path(note['held'])
    if original.parent != directory/'inputs' or held.parent != directory/'inputs' or original.exists():
        raise ValueError('Refusing to overwrite a file or restore outside this isolated case')
    held.rename(original)
    return {'status':'restored','path':str(original)}

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command',required=True)
    d = commands.add_parser('demo',help='Bootstrap real preserved Lab 3 subsets after writing the new schema')
    d.add_argument('--directory',default='demo')
    init = commands.add_parser('init',help='Copy/extend your completed Lab 3 catalogue')
    init.add_argument('--database',default='state/catalogue.sqlite')
    init.add_argument('--from-lab3')
    ls = commands.add_parser('inputs'); ls.add_argument('--database',required=True)
    conf = commands.add_parser('configure'); conf.add_argument('--database',required=True)
    conf.add_argument('--out',default='config/ndvi.yml'); conf.add_argument('--red'); conf.add_argument('--nir')
    for name in ('plan','run','report','reconcile','restore-input'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--config',required=True)
        if name == 'run':
            cmd.add_argument('--force',action='store_true')
            cmd.add_argument('--simulate',choices=('before-rename','after-rename'))
        if name == 'report': cmd.add_argument('--out')
        if name == 'reconcile':
            cmd.add_argument('--attempt-id',required=True)
            cmd.add_argument('--confirm-stopped',action='store_true')
    case = commands.add_parser('case');case.add_argument('--name',required=True,choices=('missing-input','before-rename','after-rename'))
    return p

def main():
    args = parser().parse_args()
    code = 0
    try:
        if args.command == 'demo': result = setup_demo(args.directory)
        elif args.command == 'init':
            target = Path(args.database).resolve()
            if args.from_lab3:
                source = Path(args.from_lab3).resolve()
                if target.exists(): raise FileExistsError('Destination exists; omit --from-lab3 on later init calls')
                target.parent.mkdir(parents=True,exist_ok=True)
                with contextlib.closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old:
                    with contextlib.closing(sqlite3.connect(target)) as new: old.backup(new)
            result = store.initialize(target,SCHEMA)
        elif args.command == 'inputs': result = inputs(args.database)
        elif args.command == 'configure': result = write_config(args.database,args.out,args.red,args.nir)
        elif args.command == 'case': result,code = create_case(args.name)
        else:
            cfg = job.load_config(args.config)
            if args.command == 'run':
                if args.simulate and not (cfg['_config_path'].parent.parent/'case_note.json').is_file():
                    raise ValueError('Crash simulation is restricted to generated case folders')
                result = job.run(cfg,force=args.force,simulate=args.simulate)
                if result['status'] in ('failed','needs_reconciliation'): code = 1
            elif args.command == 'plan':
                with contextlib.closing(store.connect(cfg['database'])) as c:
                    records = {role:store.input_record(c,artifact) for role,artifact in cfg['science']['inputs'].items()}
                    spec,fingerprint = job.repairs.make_request_spec(cfg['science'],records,job.environment(),cfg['runtime'])
                    result = {'request_id':'request-'+fingerprint,'normalized_spec':spec,'writes_database':False}
            elif args.command == 'report':
                result = report(cfg)
                if args.out:
                    path = Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
            elif args.command == 'reconcile': result = job.reconcile(cfg,args.attempt_id,args.confirm_stopped)
            else: result = restore_input(cfg)
        print(json.dumps(result,indent=2,default=str,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'status':'configuration_or_setup_failed','error_code':type(exc).__name__,'error':str(exc)},indent=2))
        code = 2
    return code

if __name__ == '__main__':
    raise SystemExit(main())
