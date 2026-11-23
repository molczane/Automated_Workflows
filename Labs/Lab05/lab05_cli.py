"""Lab 05: plan, execute, inspect and report one fixed serial batch."""
import argparse
import json
import shutil
import sys
from pathlib import Path
import batch_plan
import batch_runner
import batch_report
import batch_store
import fixture_setup
import job_adapter
import ndvi_job as job
import processing_store as store

ROOT=Path(__file__).resolve().parent

def refresh(manifest):
    with batch_store.writer_lock(manifest['_database']),batch_store.connect(manifest['_database']) as c:
        batch_store.check_shape(c);batch_store.register(c,manifest)
        return batch_runner.inspect_all(c,manifest,persist=True)

def create_case(name,directory):
    result=fixture_setup.setup(directory)
    m=batch_plan.load(result['manifest'],check_environment=True)
    note={'case':name,'manifest':str(m['_path'])}
    (m['_workspace']/'case_note.json').write_text(json.dumps(note,indent=2))
    first=m['frozen']['members'][0]
    if name=='missing-input':
        with batch_store.connect(m['_database']) as c:
            paths,_=job_adapter.locations(c,first['spec']['inputs'][0]['artifact_id'])
        original=paths[0];held=original.with_suffix('.held.tif');original.rename(held)
        note.update(original=str(original),held=str(held),member=first['member_id'])
        (m['_workspace']/'case_note.json').write_text(json.dumps(note,indent=2))
        result['run']=batch_runner.run(m)
    elif name=='interrupted-worker':
        result['run']=batch_runner.run(m,simulate_member=first['member_id'],simulate='before-rename')
    elif name=='interrupted-coordinator':
        batch_runner.run(m,crash_coordinator=True)
    elif name=='missing-output':
        batch_runner.run(m)
        with batch_store.connect(m['_database']) as c:
            evidence,_,_=job_adapter.result_evidence(c,first)
        original=Path(evidence['path']);held=original.with_suffix('.held.tif');original.rename(held)
        note.update(original=str(original),held=str(held),member=first['member_id'])
        (m['_workspace']/'case_note.json').write_text(json.dumps(note,indent=2))
        result['observations']=refresh(m)
    result['note']=note
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('setup');s.add_argument('--directory',default='work');s.add_argument('--fixtures')
    f=sub.add_parser('freeze');f.add_argument('--config',action='append',required=True);f.add_argument('--out',required=True);f.add_argument('--workspace',required=True);f.add_argument('--max-attempts',type=int,default=2)
    for command in ('plan','run','refresh','report','reconcile','restore-input'):
        q=sub.add_parser(command);q.add_argument('--manifest',required=True)
        if command=='run':q.add_argument('--stop-after',type=int)
        if command=='report':q.add_argument('--output',required=True)
        if command=='reconcile':
            q.add_argument('--attempt-id',required=True);q.add_argument('--confirm-stopped',action='store_true')
    q=sub.add_parser('case');q.add_argument('--name',choices=('missing-input','interrupted-worker','interrupted-coordinator','missing-output'),required=True);q.add_argument('--directory',required=True)
    args=p.parse_args();code=0
    try:
        if args.command=='setup':result=fixture_setup.setup(args.directory,args.fixtures)
        elif args.command=='case':
            result=create_case(args.name,args.directory)
            if result.get('run',{}).get('complete') is False:code=1
        elif args.command=='freeze':
            configs=[job.load_config(path) for path in args.config]
            if len({str(c['database']) for c in configs})!=1:raise ValueError('All configurations must use the same catalogue')
            database=configs[0]['database']
            with batch_store.writer_lock(database),batch_store.connect(database) as c:
                batch_store.initialize(c)
                members=batch_plan.freeze_members(c,[(Path(path).stem,cfg['science']) for path,cfg in zip(args.config,configs)])
                m=batch_plan.write_manifest(args.out,members,database,Path(args.workspace).resolve(),max_attempts=args.max_attempts)
                batch_store.register(c,m)
            result={'manifest':str(m['_path']),'batch_id':m['batch_id']}
        else:
            m=batch_plan.load(args.manifest,check_environment=args.command=='run')
            if args.command=='plan':
                with batch_store.connect(m['_database']) as c:
                    batch_store.check_shape(c)
                    result={'writes_database':False,'batch_id':m['batch_id'],'members':batch_runner.inspect_all(c,m)}
            elif args.command=='run':
                if args.stop_after is not None and args.stop_after<1:raise ValueError('--stop-after must be positive')
                result=batch_runner.run(m,stop_after=args.stop_after)
                if not result['complete']:code=1
            elif args.command=='refresh':result={'observations':refresh(m)}
            elif args.command=='report':result=batch_report.export(m,args.output)
            elif args.command=='reconcile':
                with batch_store.writer_lock(m['_database']),batch_store.connect(m['_database']) as c:
                    row=c.execute('SELECT request_id FROM processing_attempts WHERE attempt_id=?',(args.attempt_id,)).fetchone()
                    if not row:raise ValueError('Unknown attempt')
                    member=next((x for x in m['frozen']['members'] if x['request_id']==row[0]),None)
                    if not member:raise ValueError('Attempt is outside this manifest')
                    config=job_adapter.config_for(m,member)
                    result=job.reconcile(job.load_config(config),args.attempt_id,args.confirm_stopped)
            else:
                note_path=m['_workspace']/'case_note.json'
                if not note_path.is_file():raise ValueError('Restore is restricted to an isolated exercise case')
                note=json.loads(note_path.read_text());original=Path(note['original']);held=Path(note['held'])
                if original.parent!=m['_workspace']/'inputs' or held.parent!=original.parent or original.exists():raise ValueError('Refusing unsafe or overlapping restoration')
                with batch_store.writer_lock(m['_database']):held.rename(original)
                result={'status':'restored','path':str(original)}
        print(json.dumps(result,indent=2,default=str,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'status':'setup_or_configuration_failed','error_code':type(exc).__name__,'error':str(exc)}));code=2
    return code

if __name__=='__main__':raise SystemExit(main())
