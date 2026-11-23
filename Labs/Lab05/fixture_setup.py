"""Import captured real acquisition evidence into the existing Lab 3/4 contracts."""
import contextlib
import json
import shutil
import sqlite3
from pathlib import Path
import ndvi_job as job
import processing_store as store
import batch_store
import batch_plan

ROOT=Path(__file__).resolve().parent

def setup(directory,fixtures=None):
    directory=Path(directory).resolve()
    fixtures=Path(fixtures).resolve() if fixtures else ROOT/'fixtures'
    if directory.exists(): raise FileExistsError('Workspace already exists; use run or choose a new directory')
    source=json.loads((fixtures/'manifest.json').read_text())
    if not source.get('complete') or source['collection']!='sentinel-2-c1-l2a' or len(source['members'])<3:
        raise ValueError('Require the documented Collection 1 fixture manifest')
    # Fail on an unfinished student schema before making an exercise workspace.
    with batch_store.connect(':memory:') as trial:
        for schema in ('lab02_base_schema.sql','lab03_reference_schema.sql','lab04_processing_schema.sql'):
            trial.executescript((ROOT/'support'/schema).read_text())
        batch_store.initialize(trial)
    for m in source['members']:
        for entry in m['bands'].values():
            p=fixtures/entry['file']
            if store.file_hash(p)!=entry['sha256'] or p.stat().st_size!=entry['size_bytes']:
                raise ValueError('Captured fixture checksum mismatch: '+str(p))
    directory.mkdir(parents=True);(directory/'inputs').mkdir()
    database=directory/'catalogue.sqlite';stamp=store.now()
    with batch_store.connect(database,create=True) as c:
        for schema in ('lab02_base_schema.sql','lab03_reference_schema.sql'):
            c.executescript((ROOT/'support'/schema).read_text())
        with c:
            c.execute('INSERT INTO streams VALUES (?,?,?)',('lab05-captured',store.canonical({'source':'explicit captured Collection 1 subsets'}),source['downloaded_at']))
            c.execute('''INSERT INTO runs(run_id,stream_key,started_at,finished_at,status,search_until,command,config_json)
                VALUES ('lab05-import','lab05-captured',?,?,'succeeded',?,'import_captured',?)''',
                (stamp,stamp,source['downloaded_at'],store.canonical({'network_bytes':0,'source_manifest_sha256':store.file_hash(fixtures/'manifest.json')})))
            for m in source['members']:
                item=json.loads((fixtures/m['item_file']).read_text())
                c.execute('INSERT OR IGNORE INTO scenes VALUES (?,?,?,?,?,?,?)',
                    (item['collection'],item['id'],item['properties']['datetime'],item['properties'].get('eo:cloud_cover'),store.canonical(item['assets']),stamp,stamp))
                for role,entry in m['bands'].items():
                    local=directory/'inputs'/entry['file'];shutil.copy2(fixtures/entry['file'],local)
                    meta=item['assets'][role];metadata_sha=store.digest(meta)
                    asset=store.digest([item['collection'],item['id'],role,metadata_sha])
                    aoi={'crs':'EPSG:4326','bbox':entry['plan']['aoi_bbox']}
                    aoi_key=store.digest({**aoi,'pixel_rule':'center-inside'})
                    subset=store.digest([asset,aoi_key,entry['plan']['recipe']])
                    artifact=store.digest([subset,entry['sha256']]);attempt='import-'+artifact
                    c.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?)',(asset,item['collection'],item['id'],role,meta['href'],store.canonical(meta),metadata_sha,stamp))
                    c.execute("INSERT INTO subset_requests(subset_id,asset_id,aoi_key,aoi_json,recipe_version,status,updated_at) VALUES (?,?,?,?,?,'pending',?)",(subset,asset,aoi_key,store.canonical(aoi),entry['plan']['recipe'],stamp))
                    c.execute("INSERT INTO download_attempts(attempt_id,subset_id,run_id,status,stage,started_at,network_bytes) VALUES (?,?,'lab05-import','running','register',?,0)",(attempt,subset,stamp))
                    c.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)',(artifact,subset,attempt,entry['sha256'],entry['size_bytes'],store.canonical(entry['plan']),stamp))
                    c.execute("INSERT INTO artifact_locations VALUES (?,?,?,'available',?)",(store.digest([artifact,str(local)]),artifact,str(local),stamp))
                    c.execute("UPDATE download_attempts SET status='succeeded',stage='complete',finished_at=?,artifact_id=? WHERE attempt_id=?",(stamp,artifact,attempt))
                    c.execute("UPDATE subset_requests SET status='ready',latest_artifact_id=? WHERE subset_id=?",(artifact,subset))
    store.initialize(database,ROOT/'support/lab04_processing_schema.sql')
    with batch_store.connect(database) as c:
        batch_store.initialize(c)
        science_list=[]
        for m in source['members']:
            records={}
            for role,e in m['bands'].items():
                records[role]=c.execute('SELECT artifact_id FROM processing_artifacts WHERE sha256=? AND json_extract(lineage_json,\'$.asset_key\')=?',(e['sha256'],role)).fetchone()[0]
            science_list.append((m['member_id'],{**job.DEFAULT_SCIENCE,'inputs':records}))
        members=batch_plan.freeze_members(c,science_list)
        manifest=batch_plan.write_manifest(directory/'batch.json',members,database,directory)
        batch_store.register(c,manifest)
    return {'manifest':str(directory/'batch.json'),'database':str(database),'members':len(members),'source':'Captured real Collection 1 AOI subsets; no live request'}
