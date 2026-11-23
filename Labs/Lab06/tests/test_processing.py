"""Behavior checks on captured real imagery; tiny arrays only test numeric edge cases."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import numpy as np
import pytest
import rasterio
from eo_processing import database as db
from eo_processing.cli import demo
from eo_processing.common import file_hash, read_json, write_json
from eo_processing.planning import freeze, load_manifest
from eo_processing.products import normalized_difference
from eo_processing.qc import assess, evaluate
from eo_processing.runner import run, reconcile
from eo_processing.reporting import status


@pytest.fixture
def workspace(tmp_path):
    root=tmp_path/'demo'; demo(root);return root


def test_real_fixtures_integrity():
    root=Path(__file__).parents[1]/'eo_processing/data/fixtures'
    fixture=read_json(root/'manifest.json')
    assert fixture['complete'] and len(fixture['members'])==6
    for m in fixture['members']:
        assert set(m['bands'])=={'red','nir','green','swir16','scl'}
        for e in m['bands'].values():
            p=root/e['file'];assert file_hash(p)==e['sha256'] and p.stat().st_size==e['size_bytes']
            with rasterio.open(p) as src:
                assert list(src.transform)[:6]==e['plan']['transform']
                assert src.scales[0]==e['plan']['scale'] and src.offsets[0]==e['plan']['offset']


def test_numeric_unknown_and_offset():
    # Two DNs with additive offsets: using raw DN would produce a different ratio.
    a=np.array([1500.,0.,np.nan])*0.0001-0.1
    b=np.array([1100.,2000.,1000.])*0.0001-0.1
    values=normalized_difference(a,b,1e-6)
    assert values[0]==pytest.approx(2/3)
    assert np.isnan(values[1]) and np.isnan(values[2])


def test_restart_outputs_and_qc_history(workspace):
    path=workspace/'batch.json'
    first=run(path);assert first['complete'] and len(first['launched_attempts'])==6
    again=run(path);assert again['complete'] and again['launched_attempts']==[]
    manifest=load_manifest(path)
    with db.connect(workspace/'catalogue.sqlite') as c:
        assert c.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0]==6
        assert c.execute('SELECT COUNT(*) FROM processing_outputs').fetchone()[0]==18
    one=assess(path,0.5);two=assess(path,0.95)
    assert len(one['assessments'])==6 and len(two['assessments'])==6
    assert [r['outcome'] for r in one['assessments']].count('rejected')==2
    with db.connect(workspace/'catalogue.sqlite') as c:
        assert c.execute('SELECT COUNT(*) FROM processing_attempts').fetchone()[0]==6
        assert c.execute('SELECT COUNT(*) FROM scientific_qc_assessments').fetchone()[0]==12
        assert c.execute("SELECT COUNT(*) FROM processing_attempts WHERE status='succeeded'").fetchone()[0]==6
    for member in first['members']:
        evidence=member['result'];paths=evidence['paths']
        with rasterio.open(paths['water']) as src:water=src.read(1)
        with rasterio.open(paths['index']) as src:index=src.read(1)
        with rasterio.open(paths['valid_mask']) as src:mask=src.read(1)
        assert np.array_equal(np.isfinite(water),np.isfinite(index))
        assert set(np.unique(water[np.isfinite(water)]))<={0,1}
        assert np.count_nonzero(mask==1)==np.count_nonzero(np.isfinite(index))
        assert evidence['receipt']['metrics']['product_metrics']['candidate_water_area_m2']==np.count_nonzero(water==1)*400
    # All outputs are part of completion; losing the classification invalidates reuse.
    lost=Path(first['members'][0]['result']['paths']['water']);lost.rename(lost.with_suffix('.moved'))
    repaired=run(path);assert repaired['complete'] and len(repaired['launched_attempts'])==1


def test_request_identity_and_runtime_paths(workspace,tmp_path):
    original=load_manifest(workspace/'batch.json')
    config=read_json(workspace/'batch_config.json')
    config['database']=str(workspace/'catalogue.sqlite');config['workspace']=str(tmp_path/'different_output_path')
    p=tmp_path/'same.json';write_json(p,config);freeze(p,tmp_path/'same_manifest.json')
    same=load_manifest(tmp_path/'same_manifest.json')
    assert [m['request_id'] for m in original['frozen']['members']]==[m['request_id'] for m in same['frozen']['members']]
    config['jobs'][0]['parameters']['threshold']=0.15
    write_json(p,config);freeze(p,tmp_path/'changed_manifest.json')
    changed=load_manifest(tmp_path/'changed_manifest.json')
    assert original['frozen']['members'][0]['request_id']!=changed['frozen']['members'][0]['request_id']
    assert original['frozen']['members'][1]['request_id']==changed['frozen']['members'][1]['request_id']


def test_crash_reconciliation_retains_history(workspace):
    manifest=workspace/'batch.json'
    child=subprocess.run([sys.executable,'-m','eo_processing','run','--manifest',str(manifest),'--simulate','crash-before-publish'],capture_output=True,text=True)
    assert child.returncode==87, child.stderr
    before=status(manifest);assert before['counts']['unresolved']==1 and before['counts']['blocked']==5
    with db.connect(workspace/'catalogue.sqlite') as c:
        attempt=c.execute("SELECT attempt_id FROM processing_attempts WHERE status='running'").fetchone()[0]
    reconcile(manifest,attempt,'Controlled child process exited with status 87; OS lock acquired')
    after=run(manifest);assert after['complete']
    with db.connect(workspace/'catalogue.sqlite') as c:
        assert c.execute("SELECT COUNT(*) FROM processing_attempts WHERE status='interrupted'").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM processing_attempts WHERE status='succeeded'").fetchone()[0]==6


def test_missing_input_does_not_create_attempt(workspace):
    for p in (workspace/'inputs').glob('*-green.tif'):p.rename(p.with_suffix('.moved'))
    first=run(workspace/'batch.json');assert not first['complete'] and not first['launched_attempts']
    assert all(m['state']=='blocked' for m in first['members'])


def test_zero_coverage_is_a_scientific_rejection():
    assert evaluate({'valid_pixels':0},0.5)[0]=='rejected'


def test_real_ndvi_matches_earlier_arithmetic(workspace,tmp_path):
    cfg=read_json(workspace/'batch_config.json')
    cfg['database']=str(workspace/'catalogue.sqlite');cfg['workspace']=str(workspace)
    cfg['jobs']=[{**j,'member_id':j['member_id']+'-ndvi','product':'ndvi','parameters':{},'preparation':{'resolution_m':10,'mask_policy':'nodata_only'}} for j in cfg['jobs']]
    write_json(tmp_path/'ndvi.json',cfg);freeze(tmp_path/'ndvi.json',tmp_path/'ndvi_manifest.json')
    result=run(tmp_path/'ndvi_manifest.json');assert result['complete']
    manifest=load_manifest(tmp_path/'ndvi_manifest.json')
    for m,row in zip(manifest['frozen']['members'],result['members']):
        with db.connect(workspace/'catalogue.sqlite') as c:
            paths={k:db.location(c,v['artifact_id']) for k,v in m['spec']['inputs'].items()}
        with rasterio.open(paths['red']) as src:r=src.read(1).astype('float64');rm=(src.scales[0],src.offsets[0]);grid=list(src.transform)[:6]
        with rasterio.open(paths['nir']) as src:n=src.read(1).astype('float64');nm=(src.scales[0],src.offsets[0])
        valid=(r!=0)&(n!=0)
        rr=r*rm[0]+rm[1];nn=n*nm[0]+nm[1]
        valid&=np.abs(rr+nn)>1e-6
        old=np.full(r.shape,np.nan);np.divide(nn-rr,nn+rr,out=old,where=valid)
        with rasterio.open(row['result']['paths']['index']) as src:actual=src.read(1);assert list(src.transform)[:6]==grid
        assert np.array_equal(np.isfinite(old),np.isfinite(actual))
        assert np.nanmax(np.abs(old-actual))<3e-7


def test_real_mndwi_independent_pixel_arithmetic(workspace):
    result=run(workspace/'batch.json')
    row=result['members'][2]  # Clear river acquisition.
    manifest=load_manifest(workspace/'batch.json');m=manifest['frozen']['members'][2]
    with db.connect(workspace/'catalogue.sqlite') as c:
        green_path=db.location(c,m['spec']['inputs']['green']['artifact_id'])
        swir_path=db.location(c,m['spec']['inputs']['swir16']['artifact_id'])
    with rasterio.open(row['result']['paths']['index']) as dst:
        index=dst.read(1);points=np.argwhere(np.isfinite(index))[50:100:10]
        coordinates=[dst.xy(int(r),int(col)) for r,col in points]
    with rasterio.open(green_path) as green,rasterio.open(swir_path) as swir:
        ga=green.read(1);sa=swir.read(1)
        for (r,col),(x,y) in zip(points,coordinates):
            gr,gc=green.index(x-5,y+5);sr,sc=swir.index(x,y)
            g=np.mean(ga[gr:gr+2,gc:gc+2].astype('float64')*green.scales[0]+green.offsets[0])
            s=float(sa[sr,sc])*swir.scales[0]+swir.offsets[0]
            assert index[r,col]==pytest.approx((g-s)/(g+s),abs=3e-7)


def test_all_masked_real_scene_succeeds_then_rejects(workspace,tmp_path):
    cfg=read_json(workspace/'batch_config.json');cfg['database']=str(workspace/'catalogue.sqlite');cfg['workspace']=str(workspace)
    cfg['jobs']=cfg['jobs'][:1];cfg['jobs'][0]['preparation']={'excluded_scl':list(range(12))}
    write_json(tmp_path/'masked.json',cfg);freeze(tmp_path/'masked.json',tmp_path/'masked_manifest.json')
    result=run(tmp_path/'masked_manifest.json');assert result['complete']
    assert result['members'][0]['result']['receipt']['metrics']['valid_pixels']==0
    assert assess(tmp_path/'masked_manifest.json')['assessments'][0]['outcome']=='rejected'


def test_personal_extension_and_changed_source(workspace,tmp_path):
    plugin=tmp_path/'brightness.py'
    plugin.write_text('from eo_processing.products import ProductResult\nclass Brightness:\n name="brightness"\n version="1.0.0"\n required_bands=("green",)\n output_roles=("index",)\n primary_role="index"\n nominal_range=None\n default_parameters={}\n def calculate(self,bands,valid,parameters,pixel_area_m2):\n  return ProductResult({"index":bands["green"].copy()},{"purpose":"spectral brightness diagnostic"})\nPRODUCT=Brightness()\n')
    cfg=read_json(workspace/'batch_config.json');cfg['database']=str(workspace/'catalogue.sqlite');cfg['workspace']=str(workspace)
    cfg['jobs']=cfg['jobs'][2:3];cfg['jobs'][0].update(product='brightness',plugin=str(plugin),parameters={})
    write_json(tmp_path/'plugin.json',cfg);freeze(tmp_path/'plugin.json',tmp_path/'plugin_manifest.json')
    assert run(tmp_path/'plugin_manifest.json')['complete']
    old=load_manifest(tmp_path/'plugin_manifest.json')['frozen']['members'][0]['request_id']
    plugin.write_text(plugin.read_text().replace('copy()','copy()*0.5'))
    with pytest.raises(ValueError,match='Product code changed'):
        run(tmp_path/'plugin_manifest.json')
    freeze(tmp_path/'plugin.json',tmp_path/'plugin_manifest2.json')
    assert load_manifest(tmp_path/'plugin_manifest2.json')['frozen']['members'][0]['request_id']!=old
