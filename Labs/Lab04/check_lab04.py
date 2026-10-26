"""Behavioral checks for the exercises. No answers or new-table DDL here."""
import argparse
import contextlib
import copy
import json
import sqlite3
from pathlib import Path
import numpy as np
import rasterio
import repair_functions as repairs
import processing_store as store

ROOT = Path(__file__).resolve().parent

def records():
    manifest = json.loads((ROOT/'fixtures/aoi_manifest.json').read_text())
    result = {}
    for role in ('red','nir'):
        entry = manifest[role]
        result[role] = {'artifact_id':role+'-'+entry['sha256'],'sha256':entry['sha256'],
            'size_bytes':entry['size_bytes'],'raster':entry['plan'],
            'lineage':{'collection':'sentinel-2-l2a','item_id':'S2C_34UDA_20250605_0_L2A',
                       'asset_key':role,'aoi_key':store.digest(entry['plan']['aoi_bbox']),
                       'aoi':{'crs':'EPSG:4326','bbox':entry['plan']['aoi_bbox']},
                       'recipe_version':entry['plan']['recipe']}}
    return result

def check_identity():
    from ndvi_job import DEFAULT_SCIENCE
    science = {**DEFAULT_SCIENCE,'inputs':{'red':'resolved-by-caller','nir':'resolved-by-caller'}}
    source = records()
    env = {'policy':'exact_environment_v1','python':'recorded-runtime','code_sha256':'recorded-code'}
    runtime = {'output_dir':Path('/first/output'),'log_dir':Path('/first/logs')}
    spec,first = repairs.make_request_spec(science,source,env,runtime)
    assert store.digest(spec)==first, 'Fingerprint must hash canonical normalized JSON'
    assert spec.get('equivalence_policy')=='exact_environment_v1', 'State the equivalence policy explicitly'
    _,moved = repairs.make_request_spec(science,source,env,{'output_dir':Path('/other/output'),'log_dir':Path('/other/logs')})
    assert first==moved, 'Changing storage paths must preserve the request'
    _,reordered = repairs.make_request_spec(dict(reversed(list(science.items()))),dict(reversed(list(source.items()))),dict(reversed(list(env.items()))),runtime)
    assert first==reordered, 'Dictionary insertion order must not change request identity'
    changed = copy.deepcopy(env);changed['code_sha256']='repaired-code'
    assert first != repairs.make_request_spec(science,source,changed,runtime)[1], 'Record the environment/code identity'
    for key in ('denominator_epsilon','min_valid_fraction','mask_policy','stage'):
        changed = copy.deepcopy(science)
        changed[key] = 0.2 if key in ('denominator_epsilon','min_valid_fraction') else 'different-policy-or-version'
        assert first != repairs.make_request_spec(changed,source,env,runtime)[1], f'{key} affects the request'
    for key in ('sha256','raster','lineage'):
        changed = copy.deepcopy(source)
        if key=='sha256': changed['red'][key]='0'*64
        elif key=='raster': changed['red'][key]['offset']-=0.01
        else: changed['red'][key]['aoi_key']='different-aoi'
        assert first != repairs.make_request_spec(science,changed,env,runtime)[1], f'Input {key} affects the request'
    integer = copy.deepcopy(science);integer['min_valid_fraction']=1
    decimal = copy.deepcopy(science);decimal['min_valid_fraction']=1.0
    assert repairs.make_request_spec(integer,source,env,runtime)[1] == repairs.make_request_spec(decimal,source,env,runtime)[1], 'Normalize equivalent numeric parameters'
    reviewed=copy.deepcopy(science);reviewed['scaling']='reviewed_calibration'
    reviewed['calibration']={role:{'sha256':source[role]['sha256'],'scale':0.0001,'offset':0.0,'evidence':'explicit review'} for role in ('red','nir')}
    review_hash=repairs.make_request_spec(reviewed,source,env,runtime)[1]
    revised=copy.deepcopy(reviewed);revised['calibration']['red']['offset']=-0.01
    assert review_hash!=repairs.make_request_spec(revised,source,env,runtime)[1], 'Include the calibration values, not just the policy name'

def must_reject(function, message):
    try: function()
    except (ValueError,KeyError,TypeError): return
    raise AssertionError(message)

def check_pair():
    source = records()
    repairs.validate_pair(source['red'],source['nir'])
    for label in ('transform','crs','item_id','aoi_key','role','scale'):
        changed = copy.deepcopy(source)
        if label=='transform': changed['nir']['raster']['transform'][2]+=10
        elif label=='crs': changed['nir']['raster']['crs']='EPSG:32633'
        elif label in ('item_id','aoi_key'): changed['nir']['lineage'][label]='different'
        elif label=='role': changed['nir']['lineage']['asset_key']='red'
        else: changed['nir']['raster']['scale']=None
        must_reject(lambda:repairs.validate_pair(changed['red'],changed['nir']),f'Reject incompatible {label} even when shapes match')
    must_reject(lambda:repairs.validate_pair(source['nir'],source['red']),'Swapping roles must fail')

def check_ndvi():
    source = records()
    arrays = {}
    for role in ('red','nir'):
        with rasterio.open(ROOT/'fixtures'/('real_'+role+'_aoi.tif')) as src: arrays[role]=src.read(1)
    original = {k:v.copy() for k,v in arrays.items()}
    red,nir = arrays['red'],arrays['nir']
    rm,nm = source['red']['raster'],source['nir']['raster']
    r=red.astype('float64')*rm['scale']+rm['offset'];n=nir.astype('float64')*nm['scale']+nm['offset']
    valid=(red!=rm['nodata'])&(nir!=nm['nodata'])&(np.abs(n+r)>1e-6)
    expected=np.full(red.shape,np.nan,dtype='float64')
    expected[valid]=(n[valid]-r[valid])/(n[valid]+r[valid])
    actual=repairs.calculate_ndvi(red,nir,rm,nm,1e-6)
    assert actual.dtype==np.dtype('float32') and actual.shape==red.shape, 'Keep shape and return float32'
    np.testing.assert_array_equal(np.isnan(actual),~valid,err_msg='Mask original nodata and unusable denominators')
    np.testing.assert_allclose(actual[valid],expected[valid],rtol=1e-6,atol=1e-6,err_msg='Cast before arithmetic and apply both scale and offset')
    assert all(np.array_equal(arrays[k],original[k]) for k in arrays), 'Do not modify the input arrays'
    # A high threshold exercises denominator handling using the same real pixels.
    rejected=repairs.calculate_ndvi(red,nir,rm,nm,100.0)
    assert np.isnan(rejected).all(), 'Apply the denominator threshold; do not divide every pixel'

def check_schema():
    with contextlib.closing(sqlite3.connect(':memory:')) as c:
        c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
        c.executescript((ROOT/'support/lab02_base_schema.sql').read_text())
        c.executescript((ROOT/'support/lab03_reference_schema.sql').read_text())
        c.executescript((ROOT/'student_processing_schema.sql').read_text())
        store.check_shape(c)
        def reject(sql,values,message):
            c.execute('SAVEPOINT invalid_case')
            try:
                c.execute(sql,values)
            except sqlite3.IntegrityError:
                c.execute('ROLLBACK TO invalid_case');c.execute('RELEASE invalid_case');return
            c.execute('ROLLBACK TO invalid_case');c.execute('RELEASE invalid_case')
            raise AssertionError(message)
        request=('r','a'*64,'ndvi_v1','{}','time')
        c.execute('INSERT INTO processing_requests VALUES (?,?,?,?,?)',request)
        reject('INSERT INTO processing_requests VALUES (?,?,?,?,?)',('r2',*request[1:]),'Equivalent fingerprints must be unique')
        reject('INSERT INTO processing_requests VALUES (?,?,?,?,?)',('r3','b'*64,'ndvi_v1','invalid','time'),'Require valid normalized JSON')
        reject('INSERT INTO processing_inputs VALUES (?,?,?)',('r','red','absent'),'Reject an input artifact that does not exist')
        c.execute("INSERT INTO processing_artifacts VALUES ('f',NULL,?,1,'{}','{}','time')",('c'*64,))
        c.execute("INSERT INTO processing_inputs VALUES ('r','red','f')")
        reject('INSERT INTO processing_inputs VALUES (?,?,?)',('r','red','f'),'Only one artifact per input role per request')
        # Different roles and attempts are legitimate, and must not be individually unique.
        c.execute("INSERT INTO processing_inputs VALUES ('r','nir','f')")
        insert='''INSERT INTO processing_attempts (attempt_id,request_id,status,stage,started_at,
            environment_json,original_config,resolved_config_json,temp_path,final_path,log_path)
            VALUES (?,?,'running','validate_inputs','time','{}','yaml','{}',?,?,?)'''
        for number in (1,2): c.execute(insert,(f'a{number}','r',f't{number}',f'f{number}',f'l{number}'))
        reject("UPDATE processing_attempts SET status='invented' WHERE attempt_id='a1'",(),'Constrain lifecycle status')
        reject("UPDATE processing_attempts SET status='failed' WHERE attempt_id='a1'",(),'Terminal attempts require a finish timestamp')
        reject("INSERT INTO processing_outputs VALUES ('absent','ndvi','f')",(),'Output attempt must exist')
        reject("INSERT INTO processing_artifact_locations VALUES ('l','f','path','invented','time')",(),'Constrain location status')
        reject("INSERT INTO processing_artifacts VALUES ('bad',NULL,?,0,'{}','{}','time')",('d'*64,),'Stored byte size must be positive')
        for table in store.TABLES:
            for column in store.TABLES[table]:
                info={row['name']:row for row in c.execute(f'PRAGMA table_info({table})')}
                optional={'source_artifact_id','finished_at','receipt_json','error_code','error_message','reused_from_attempt_id'}
                if column not in optional:
                    assert info[column]['notnull'], f'{table}.{column} must reject NULL'

CHECKS={'schema':check_schema,'identity':check_identity,'pair':check_pair,'ndvi':check_ndvi}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--part',choices=(*CHECKS,'all'),default='all');args=p.parse_args()
    names=list(CHECKS) if args.part=='all' else [args.part]
    failed=[]
    for name in names:
        try: CHECKS[name]();print(f'PASS {name}')
        except Exception as exc: failed.append(name);print(f'FAIL {name}: {type(exc).__name__}: {exc}')
    return int(bool(failed))

if __name__=='__main__': raise SystemExit(main())
