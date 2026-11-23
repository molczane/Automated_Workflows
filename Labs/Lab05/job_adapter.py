"""Call the Lab 4 CLI; independently verify catalogue, bytes, grid and provenance."""
import json
import subprocess
import sys
from pathlib import Path
import rasterio
import yaml
import ndvi_job as job
import processing_store as store
import batch_repairs as repairs

ROOT = Path(__file__).resolve().parent

def locations(c, artifact_id):
    """Inspect every known copy. Old catalogue status does not establish current presence."""
    artifact = c.execute('SELECT * FROM processing_artifacts WHERE artifact_id=?',(artifact_id,)).fetchone()
    checks=[]; good=[]
    for loc in c.execute('SELECT * FROM processing_artifact_locations WHERE artifact_id=? ORDER BY local_path',(artifact_id,)):
        path=Path(loc['local_path']); status='missing'; error=None
        try:
            if path.is_file():
                status='available' if path.stat().st_size==artifact['size_bytes'] and store.file_hash(path)==artifact['sha256'] else 'corrupt'
        except OSError as exc:
            status='corrupt'; error=str(exc)
        checks.append({'location_id':loc['location_id'],'artifact_id':artifact_id,
                       'path':str(path),'status':status,'checked_at':store.now(),'error':error})
        if status=='available': good.append(path)
    return good, checks

def result_evidence(c, member):
    checks=[]; rejected=[]
    for row in c.execute('''SELECT a.attempt_id,a.request_id,o.artifact_id,f.sha256,f.size_bytes
        FROM processing_attempts a JOIN processing_outputs o USING(attempt_id)
        JOIN processing_artifacts f USING(artifact_id)
        WHERE a.request_id=? AND a.status='succeeded' AND o.role='ndvi'
        ORDER BY a.started_at DESC,a.attempt_id''',(member['request_id'],)).fetchall():
        record=dict(row)
        paths, inspected=locations(c,record['artifact_id']); checks.extend(inspected)
        for path in paths:
            try:
                expected=member['spec']['inputs'][0]['raster']
                validation=job.validate_output(path,expected,member['request_id'],record['attempt_id'],
                                               member['spec']['settings']['min_valid_fraction'])
                evidence={**record,'path':str(path),'checked_at':store.now(),'validation':validation,
                          'actual_sha256':store.file_hash(path),'actual_size_bytes':path.stat().st_size,
                          'catalogue_link_verified':True,'grid_verified':True,'provenance_verified':True}
                if not repairs.verify_result(member,evidence):
                    raise ValueError('verify_result rejected the output evidence')
                return evidence,checks,rejected
            except (ValueError,OSError,rasterio.errors.RasterioError) as exc:
                rejected.append({'artifact_id':record['artifact_id'],'path':str(path),'reason':str(exc)})
    return None,checks,rejected

def inspect_member(c,member,max_attempts):
    running=c.execute("SELECT attempt_id FROM processing_attempts WHERE request_id=? AND status='running'",(member['request_id'],)).fetchone()
    result,checks,rejected=result_evidence(c,member)
    attempts=[dict(r) for r in c.execute('SELECT attempt_id,status,error_code,error_message FROM processing_attempts WHERE request_id=? ORDER BY started_at,attempt_id',(member['request_id'],))]
    context={'active_attempt':dict(running) if running else None,'verified_result':result,
             'missing_inputs':[],'validation_error':None,'attempts_used':sum(a['status']!='reused' for a in attempts),
             'max_attempts':max_attempts,'last_attempt':attempts[-1] if attempts else None}
    # A valid finished result remains usable even if source files were later moved.
    if result is None and running is None:
        try:
            inputs={r['role']:store.input_record(c,r['artifact_id']) for r in member['spec']['inputs']}
            job.repairs.validate_pair(inputs['red'],inputs['nir'])
            for role,record in inputs.items():
                paths,inspected=locations(c,record['artifact_id']); checks.extend(inspected)
                if not paths: context['missing_inputs'].append(role)
                else: job.inspect_input(paths[0],record)
        except (ValueError,OSError,rasterio.errors.RasterioError) as exc:
            context['validation_error']=str(exc)
    classified=repairs.classify_member(context)
    classified.update(member_id=member['member_id'],request_id=member['request_id'],
                      context=context,location_checks=checks,rejected_results=rejected,
                      inputs=member['spec']['inputs'])
    classified['next_check']={
        'complete':'Review the mask policy and scientific QC before using the result.',
        'blocked':'Inspect the input role/location checks or the catalogue active execution.',
        'unresolved':'Establish whether the process stopped, then use explicit reconciliation.',
        'failed':'Inspect the validation and attempt errors; preserve the history and budget.',
        'ready':'Launch within the remaining budget; inspect old output locations if this is recovery.'
    }[classified['state']]
    if running: classified['attempt_id']=running['attempt_id']
    elif result: classified.update(attempt_id=result['attempt_id'],artifact_id=result['artifact_id'],result=result)
    return classified

def config_for(manifest,member):
    workspace=manifest['_workspace']; database=manifest['_database']; spec=member['spec']
    path=workspace/'config'/(member['member_id']+'.yml')
    path.parent.mkdir(parents=True,exist_ok=True)
    cfg={'database':str(database),'science':{'stage':spec['stage'],**spec['settings'],
         'inputs':{r['role']:r['artifact_id'] for r in spec['inputs']}},
         'runtime':{'output_dir':str(workspace/'outputs'),'log_dir':str(workspace/'logs')}}
    path.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    return path

def invoke(manifest,member,simulate=None):
    config=config_for(manifest,member)
    cfg=job.load_config(config)
    with __import__('contextlib').closing(store.connect(manifest['_database'])) as c:
        current={role:store.input_record(c,artifact) for role,artifact in cfg['science']['inputs'].items()}
        _,fingerprint=job.repairs.make_request_spec(cfg['science'],current,job.environment(),cfg['runtime'])
        if 'request-'+fingerprint!=member['request_id']:
            raise ValueError('Catalogue inputs no longer match the frozen scientific request')
    command=[sys.executable,str(ROOT/'lab04_cli.py'),'run','--config',str(config)]
    if simulate: command += ['--simulate',simulate]
    child=subprocess.run(command,capture_output=True,text=True)
    # Preserve the exit status. Stdout is diagnostic evidence, never sufficient proof.
    try: response=json.loads(child.stdout)
    except json.JSONDecodeError: response={'unparsed_stdout':child.stdout[-4000:]}
    return {'exit_code':child.returncode,'response':response,'stderr':child.stderr[-4000:],
            'config':str(config)}
