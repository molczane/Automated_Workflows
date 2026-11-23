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
SCHEMA = ROOT / 'support/lab04_processing_schema.sql'

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
    if path.exists():
        raise FileExistsError(f'Configuration exists: {path}; edit it explicitly or choose --out')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
    return {'config':str(path), 'inputs':chosen,'scaling':cfg['science']['scaling']}

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

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='command',required=True)
    init = commands.add_parser('init',help='Copy/extend your completed Lab 3 catalogue')
    init.add_argument('--database',default='state/catalogue.sqlite')
    init.add_argument('--from-lab3')
    ls = commands.add_parser('inputs'); ls.add_argument('--database',required=True)
    conf = commands.add_parser('configure'); conf.add_argument('--database',required=True)
    conf.add_argument('--out',default='config/ndvi.yml'); conf.add_argument('--red'); conf.add_argument('--nir')
    for name in ('plan','run','report','reconcile'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--config',required=True)
        if name == 'run':
            cmd.add_argument('--force',action='store_true')
            cmd.add_argument('--simulate',choices=('before-rename','after-rename'))
        if name == 'report': cmd.add_argument('--out')
        if name == 'reconcile':
            cmd.add_argument('--attempt-id',required=True)
            cmd.add_argument('--confirm-stopped',action='store_true')
    return p

def main():
    args = parser().parse_args()
    code = 0
    try:
        if args.command == 'init':
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
        print(json.dumps(result,indent=2,default=str,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'status':'configuration_or_setup_failed','error_code':type(exc).__name__,'error':str(exc)},indent=2))
        code = 2
    return code

if __name__ == '__main__':
    raise SystemExit(main())
