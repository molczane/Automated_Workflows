"""Supplied job wrapper. Repairs live in repair_functions.py."""
import contextlib
import json
import math
import os
import platform
import sys
import uuid
from pathlib import Path

import numpy as np
import rasterio
import yaml
from rasterio.transform import Affine

import processing_store as store
import repair_functions as repairs

ROOT = Path(__file__).resolve().parent
DEFAULT_SCIENCE = {
    'stage': 'ndvi_v1', 'grid_policy': 'require_match',
    'scaling': 'asset_metadata', 'mask_policy': 'nodata_only',
    'denominator_epsilon': 0.000001, 'min_valid_fraction': 0.1, 'calibration': None,
}

class UniqueLoader(yaml.SafeLoader):
    pass

def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'Duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result

UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)

def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label} needs exactly these keys: {sorted(keys)}')

def load_config(path):
    path = Path(path).resolve()
    original = path.read_text(encoding='utf-8-sig')
    cfg = yaml.load(original, Loader=UniqueLoader)
    exact_keys(cfg, ('database','science','runtime'), 'configuration')
    science = cfg['science']
    exact_keys(science, (*DEFAULT_SCIENCE.keys(), 'inputs'), 'science')
    exact_keys(science['inputs'], ('red','nir'), 'science.inputs')
    for key in ('stage','grid_policy','mask_policy'):
        if science[key] != DEFAULT_SCIENCE[key]:
            raise ValueError(f'Unsupported {key}: {science[key]!r}')
    if science['scaling'] not in ('asset_metadata','reviewed_calibration'):
        raise ValueError('scaling must be asset_metadata or reviewed_calibration')
    if science['scaling'] == 'asset_metadata':
        if science['calibration'] is not None:
            raise ValueError('asset_metadata requires calibration: null')
    else:
        exact_keys(science['calibration'],('red','nir'),'calibration')
        for role,review in science['calibration'].items():
            exact_keys(review,('sha256','scale','offset','evidence'),'calibration.'+role)
            for key in ('scale','offset'):
                if isinstance(review[key],bool) or not isinstance(review[key],(int,float)) or not math.isfinite(review[key]):
                    raise ValueError('Reviewed scale and offset must be finite numbers')
                review[key]=float(review[key])
            if review['scale']<=0 or not isinstance(review['sha256'],str) or len(review['sha256'])!=64 or not isinstance(review['evidence'],str) or not review['evidence'].strip():
                raise ValueError('Reviewed calibration requires a positive scale, exact input hash and evidence')
    for key in ('denominator_epsilon','min_valid_fraction'):
        value = science[key]
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError(f'{key} must be a finite number')
        science[key] = float(value)
    if not 0 < science['denominator_epsilon'] < 1 or not 0 < science['min_valid_fraction'] <= 1:
        raise ValueError('Require 0 < epsilon < 1 and 0 < min_valid_fraction <= 1')
    for role, value in science['inputs'].items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{role} requires one explicit artifact ID')
    exact_keys(cfg['runtime'], ('output_dir','log_dir'), 'runtime')
    for value in (cfg['database'], *cfg['runtime'].values()):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Paths must be nonempty strings')
    cfg['database'] = (path.parent / cfg['database']).resolve()
    cfg['runtime'] = {key: (path.parent / value).resolve() for key,value in cfg['runtime'].items()}
    if not cfg['database'].is_file():
        raise FileNotFoundError(f'Database is absent: {cfg["database"]}; run demo or init first')
    cfg['_original'] = original
    cfg['_config_path'] = path
    return cfg

def environment():
    # Conservative reuse policy: code or runtime version changes change the request.
    code = {name: store.file_hash(ROOT / name) for name in
            ('repair_functions.py','ndvi_job.py','processing_store.py','lab04_cli.py')}
    return {'policy': 'exact_environment_v1', 'python': platform.python_version(),
            'system': platform.system(), 'machine': platform.machine(),
            'numpy': np.__version__, 'rasterio': rasterio.__version__,
            'gdal': rasterio.__gdal_version__, 'proj': rasterio.__proj_version__,
            'pyyaml': yaml.__version__, 'code_sha256': code}

def resolved_public(cfg, inputs):
    return {'database': str(cfg['database']), 'science': cfg['science'],
            'runtime': {k:str(v) for k,v in cfg['runtime'].items()},
            'inputs': inputs}

def resolve(c, cfg):
    inputs = {role: store.input_record(c, cfg['science']['inputs'][role]) for role in ('red','nir')}
    env = environment()
    spec, fingerprint = repairs.make_request_spec(cfg['science'], inputs, env, cfg['runtime'])
    request_id = store.record_request(c, fingerprint, spec, inputs)
    return inputs, env, spec, request_id

def inspect_input(path, record):
    meta = record['raster']
    with rasterio.open(path) as src:
        if src.crs is None or src.count != 1 or src.dtypes[0] != 'uint16':
            raise ValueError('Input must be a single uint16 band with a CRS')
        actual = {'shape': [src.height, src.width], 'crs': src.crs.to_string(),
                  'transform': list(src.transform)[:6], 'nodata': src.nodata,
                  'scale': src.scales[0], 'offset': src.offsets[0]}
        for key in actual:
            if actual[key] != meta[key]:
                raise ValueError(f'Raster header disagrees with registered {key}')
        return src.read(1)

def effective_calibration(cfg, records):
    """Keep original headers intact; a reviewed interpretation is a request parameter."""
    known = json.loads((ROOT/'fixtures/aoi_manifest.json').read_text())
    result = {}
    for role,record in records.items():
        meta = dict(record['raster'])
        if cfg['science']['scaling'] == 'reviewed_calibration':
            review = cfg['science']['calibration'][role]
            if review['sha256'] != record['sha256']:
                raise ValueError(f'Reviewed {role} calibration applies to a different file hash')
            meta.update(scale=review['scale'],offset=review['offset'])
        elif record['sha256'] == known[role]['sha256'] and meta['offset'] != 0:
            raise ValueError('Known Lab 3 calibration conflict: read CALIBRATION_REVIEW.md and use the explicitly reviewed configuration')
        result[role]=meta
    return result

def validate_output(path, expected, request_id, attempt_id, minimum):
    with rasterio.open(path) as src:
        if src.count != 1 or src.dtypes[0] != 'float32' or src.crs is None:
            raise ValueError('Output must be one float32 raster band with a CRS')
        if [src.height,src.width] != expected['shape'] or src.crs.to_string() != expected['crs'] or list(src.transform)[:6] != expected['transform']:
            raise ValueError('Output grid differs from the requested grid')
        if src.nodata is None or not math.isnan(src.nodata) or src.scales != (1.0,) or src.offsets != (0.0,):
            raise ValueError('NDVI requires NaN nodata, scale 1 and offset 0')
        tags = src.tags()
        if tags.get('REQUEST_ID') != request_id or tags.get('ATTEMPT_ID') != attempt_id or tags.get('MASK_POLICY') != 'nodata_only':
            raise ValueError('Output provenance tags do not match this attempt')
        data = src.read(1)
        if np.isinf(data).any():
            raise ValueError('Infinite NDVI values are invalid')
        valid = np.isfinite(data)
        fraction = float(valid.mean())
        if not valid.any() or fraction < minimum:
            raise ValueError(f'Valid pixel fraction {fraction:.6f} is below {minimum}')
        return {'shape': [src.height,src.width], 'crs': src.crs.to_string(),
                'transform': list(src.transform)[:6], 'dtype': 'float32',
                'nodata': 'NaN', 'scale': 1.0, 'offset': 0.0,
                'valid_pixels': int(valid.sum()), 'total_pixels': int(data.size),
                'valid_fraction': fraction, 'minimum': float(data[valid].min()),
                'maximum': float(data[valid].max()), 'mean': float(data[valid].mean()),
                'outside_nominal_range': int(np.count_nonzero(valid & ((data < -1) | (data > 1)))),
                'mask_policy': 'nodata_only', 'cloud_screened': False}

def find_reuse(c, request_id, cfg, expected):
    rows = c.execute('''SELECT a.attempt_id,o.artifact_id FROM processing_attempts a
        JOIN processing_outputs o USING(attempt_id)
        WHERE a.request_id=? AND a.status='succeeded' AND o.role='ndvi'
        ORDER BY a.started_at DESC,a.attempt_id''', (request_id,)).fetchall()
    for row in rows:
        try:
            path = store.verified_location(c, row['artifact_id'])
            validate_output(path, expected, request_id, row['attempt_id'], cfg['science']['min_valid_fraction'])
            return dict(row), path
        except (FileNotFoundError, ValueError, rasterio.errors.RasterioIOError):
            continue
    return None

def new_attempt(c, cfg, request_id, inputs, env):
    attempt_id = 'attempt-' + uuid.uuid4().hex
    output_dir = cfg['runtime']['output_dir']
    log_dir = cfg['runtime']['log_dir']
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    temp = output_dir / ('.' + attempt_id + '.partial.tif')
    final = output_dir / (attempt_id + '.ndvi.tif')
    log = log_dir / (attempt_id + '.jsonl')
    if cfg['database'] in (temp,final,log):
        raise ValueError('Output paths overlap the database')
    # This lab permits one active process per local database. Lab 5 adds ownership.
    c.execute('BEGIN IMMEDIATE')
    try:
        if c.execute("SELECT 1 FROM processing_attempts WHERE status='running'").fetchone():
            raise ValueError('An unresolved running attempt exists; inspect and reconcile it before retrying')
        c.execute('''INSERT INTO processing_attempts
            (attempt_id,request_id,status,stage,started_at,environment_json,original_config,
             resolved_config_json,temp_path,final_path,log_path)
            VALUES (?,?,'running','validate_inputs',?,?,?,?,?,?,?)''',
            (attempt_id,request_id,store.now(),store.canonical(env),cfg['_original'],
             store.canonical(resolved_public(cfg,inputs)),str(temp),str(final),str(log)))
        c.commit()
    except Exception:
        c.rollback()
        raise
    result = dict(c.execute('SELECT * FROM processing_attempts WHERE attempt_id=?', (attempt_id,)).fetchone())
    store.event(log, attempt_id=attempt_id, request_id=request_id, stage='validate_inputs', status='running')
    return result

def run(cfg, force=False, simulate=None):
    with contextlib.closing(store.connect(cfg['database'])) as c:
        store.check_shape(c)
        inputs, env, spec, request_id = resolve(c, cfg)
        attempt = new_attempt(c, cfg, request_id, inputs, env)
        attempt_id = attempt['attempt_id']
        temp, final = Path(attempt['temp_path']), Path(attempt['final_path'])
        try:
            repairs.validate_pair(inputs['red'], inputs['nir'])
            paths = {role: store.verified_location(c, inputs[role]['artifact_id']) for role in ('red','nir')}
            if any(path.resolve() in (temp,final) for path in paths.values()):
                raise ValueError('An output must never overwrite an input')
            arrays = {role: inspect_input(paths[role], inputs[role]) for role in ('red','nir')}
            calibration = effective_calibration(cfg, inputs)
            if not force and (reuse := find_reuse(c, request_id, cfg, inputs['red']['raster'])):
                previous, path = reuse
                with c:
                    c.execute('INSERT INTO processing_outputs VALUES (?,?,?)', (attempt_id,'ndvi',previous['artifact_id']))
                    c.execute('''UPDATE processing_attempts SET status='reused',stage='complete',finished_at=?,
                        reused_from_attempt_id=? WHERE attempt_id=?''', (store.now(),previous['attempt_id'],attempt_id))
                store.event(attempt['log_path'], attempt_id=attempt_id, status='reused', artifact_id=previous['artifact_id'])
                return {'status':'reused','request_id':request_id,'attempt_id':attempt_id,
                        'artifact_id':previous['artifact_id'],'path':str(path)}
            store.stage(c, attempt_id, 'calculate')
            data = repairs.calculate_ndvi(arrays['red'],arrays['nir'],calibration['red'],calibration['nir'],cfg['science']['denominator_epsilon'])
            expected = inputs['red']['raster']
            if data.shape != tuple(expected['shape']) or data.dtype != np.dtype('float32'):
                raise ValueError('calculate_ndvi must return a float32 array on the input grid')
            store.stage(c, attempt_id, 'write_temporary')
            profile = dict(driver='GTiff',height=data.shape[0],width=data.shape[1],count=1,
                           dtype='float32',crs=expected['crs'],transform=Affine(*expected['transform']),
                           nodata=float('nan'),compress='deflate',predictor=3)
            with rasterio.open(temp, 'w', **profile) as dst:
                dst.write(data,1)
                dst.update_tags(REQUEST_ID=request_id,ATTEMPT_ID=attempt_id,MASK_POLICY='nodata_only',
                                CLOUD_SCREENED='false',STAGE=cfg['science']['stage'])
            with temp.open('r+b') as stream:
                os.fsync(stream.fileno())
            store.stage(c, attempt_id, 'validate_temporary')
            validation = validate_output(temp,expected,request_id,attempt_id,cfg['science']['min_valid_fraction'])
            receipt = {'sha256':store.file_hash(temp),'size_bytes':temp.stat().st_size,
                       'expected_grid':expected,'validation':validation}
            with c:
                c.execute("UPDATE processing_attempts SET stage='before_rename',receipt_json=? WHERE attempt_id=?", (store.canonical(receipt),attempt_id))
            store.event(attempt['log_path'], attempt_id=attempt_id, stage='before_rename', sha256=receipt['sha256'])
            if simulate == 'before-rename':
                os._exit(86)  # Deliberate process death: no exception handler or cleanup.
            if final.exists():
                raise FileExistsError('Refusing to overwrite an existing product')
            os.replace(temp, final)  # Same directory, therefore same filesystem.
            if simulate == 'after-rename':
                os._exit(86)
            store.stage(c, attempt_id, 'register_output')
            artifact_id = store.publish(c, attempt, receipt)
            store.event(attempt['log_path'], attempt_id=attempt_id, status='succeeded', artifact_id=artifact_id)
            return {'status':'succeeded','request_id':request_id,'attempt_id':attempt_id,
                    'artifact_id':artifact_id,'path':str(final),'validation':validation}
        except Exception as exc:
            # If rename has happened, reconciliation must decide whether to adopt.
            if final.exists():
                store.event(attempt['log_path'], attempt_id=attempt_id, status='needs_reconciliation',error=str(exc))
                return {'status':'needs_reconciliation','attempt_id':attempt_id,'request_id':request_id,'error':str(exc)}
            store.end_attempt(c,attempt_id,'failed',type(exc).__name__,exc)
            store.event(attempt['log_path'], attempt_id=attempt_id, status='failed',error_code=type(exc).__name__,error=str(exc))
            return {'status':'failed','request_id':request_id,'attempt_id':attempt_id,
                    'error_code':type(exc).__name__,'error':str(exc)}

def reconcile(cfg, attempt_id, confirm_stopped):
    if not confirm_stopped:
        raise ValueError('Establish that the process has stopped, then pass --confirm-stopped')
    with contextlib.closing(store.connect(cfg['database'])) as c:
        row = c.execute('SELECT * FROM processing_attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown attempt ID')
        attempt = dict(row)
        if attempt['status'] != 'running':
            return {'status':'unchanged','attempt_id':attempt_id,'attempt_status':attempt['status']}
        temp,final = Path(attempt['temp_path']),Path(attempt['final_path'])
        receipt = json.loads(attempt['receipt_json']) if attempt['receipt_json'] else None
        try:
            if final.exists():
                if not receipt or store.file_hash(final) != receipt['sha256'] or final.stat().st_size != receipt['size_bytes']:
                    raise ValueError('Final file does not match the pre-rename receipt')
                original_cfg = json.loads(attempt['resolved_config_json'])
                validation = validate_output(final,receipt['expected_grid'],attempt['request_id'],attempt_id,
                                             original_cfg['science']['min_valid_fraction'])
                if validation != receipt['validation']:
                    raise ValueError('Reopened raster differs from its validation receipt')
                artifact_id = store.publish(c,attempt,receipt)
                store.event(attempt['log_path'],attempt_id=attempt_id,status='adopted',artifact_id=artifact_id)
                return {'status':'adopted','attempt_id':attempt_id,'artifact_id':artifact_id,'path':str(final)}
            if temp.exists():
                quarantine = temp.parent / 'quarantine'
                quarantine.mkdir(exist_ok=True)
                destination = quarantine / (attempt_id + '.partial.tif')
                if destination.exists():
                    raise FileExistsError('Quarantine destination already exists')
                os.replace(temp,destination)
            store.end_attempt(c,attempt_id,'interrupted','PROCESS_STOPPED_BEFORE_PUBLISH','No published output; temporary file quarantined if present')
            store.event(attempt['log_path'],attempt_id=attempt_id,status='interrupted')
            return {'status':'interrupted','attempt_id':attempt_id,'retry':'same request, new attempt'}
        except (ValueError, rasterio.errors.RasterioIOError) as exc:
            if final.exists():
                destination = final.with_suffix('.quarantined.tif')
                if destination.exists():
                    raise FileExistsError('Quarantine destination already exists')
                os.replace(final,destination)
            store.end_attempt(c,attempt_id,'interrupted','UNVERIFIED_OUTPUT',exc)
            store.event(attempt['log_path'],attempt_id=attempt_id,status='quarantined',error=str(exc))
            return {'status':'quarantined','attempt_id':attempt_id,'error':str(exc)}
