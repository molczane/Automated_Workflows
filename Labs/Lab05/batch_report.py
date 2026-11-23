"""A static report is a first usable read interface for the future QC website."""
import html
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import batch_store
import batch_repairs as repairs
import processing_store as store

QUERY_VERSION='lab05_queries_v1'

def read_report(c,manifest):
    rows=[dict(r) for r in c.execute('''SELECT m.member_id,m.planned_request_id,m.request_id,
        o.observation_id,o.state,o.observed_at,o.reason,o.attempt_id,o.evidence_json
        FROM batch_members m LEFT JOIN batch_observations o
          ON o.batch_id=m.batch_id AND o.member_id=m.member_id
        WHERE m.batch_id=? ORDER BY m.member_id,o.observation_id''',(manifest['batch_id'],))]
    # NULL observations still supply one expected row. Order missing observations below real IDs.
    for r in rows:
        if r['observation_id'] is None: r['observation_id']=-1
    summary=repairs.summarize_batch(rows)
    latest={}
    for r in rows:
        if r['member_id'] not in latest or r['observation_id']>latest[r['member_id']]['observation_id']:
            latest[r['member_id']]=r
    now=datetime.now(timezone.utc)
    for r in latest.values():
        r['evidence']=json.loads(r.pop('evidence_json')) if r['evidence_json'] else None
        r['age_seconds']=max(0,(now-datetime.fromisoformat(r['observed_at'].replace('Z','+00:00'))).total_seconds()) if r['observed_at'] else None
    attempts=[dict(r) for r in c.execute('''SELECT a.* FROM processing_attempts a
        WHERE a.request_id IN (SELECT planned_request_id FROM batch_members WHERE batch_id=?)
        ORDER BY a.started_at,a.attempt_id''',(manifest['batch_id'],))]
    for a in attempts:
        # Report provenance, not large duplicate environment/config blobs.
        for key in ('environment_json','original_config','resolved_config_json','receipt_json'):a.pop(key,None)
    return {'batch_id':manifest['batch_id'],'query_version':QUERY_VERSION,'generated_at':store.now(),
            'membership_sha256':store.digest(manifest['frozen']), 'summary':summary,
            'members':list(latest.values()),'attempt_count':len(attempts),
            'production_count':sum(a['status']=='succeeded' for a in attempts),
            'attempts':attempts,'scientific_qc':{'mask_policy':'nodata_only','cloud_suitability':'unassessed'},
            'interpretation':'States describe recorded observations at their timestamps. Use refresh for new file checks.'}

def render(report):
    esc=lambda x:html.escape(str(x))
    cards=''.join(f'<a class="card" href="#state-{esc(s)}">{esc(s)}<strong>{n}</strong></a>' for s,n in report['summary']['counts'].items())
    groups=''
    for state,ids in report['summary']['members'].items():
        links=', '.join(f'<a href="#{esc(m)}">{esc(m)}</a>' for m in ids) or 'None'
        groups+=f'<p id="state-{esc(state)}"><b>{esc(state)}</b>: {links}</p>'
    details=''
    for m in report['members']:
        ev=m['evidence'] or {};result=ev.get('result',{})
        validation=result.get('validation',{})
        coverage=(str(validation.get('valid_pixels','?'))+' / '+str(validation.get('total_pixels','?'))+' finite pixels') if validation else 'No verified NDVI evidence'
        details+=f'''<article id="{esc(m['member_id'])}"><h2>{esc(m['member_id'])}</h2>
        <p>{esc(m['state'] or 'unobserved')}: {esc(m['reason'] or 'No observation yet')}</p>
        <p>Next check: {esc(ev.get('next_check','Inspect this member; no readiness evidence is recorded.'))}</p>
        <p>Request: <code>{esc(m['planned_request_id'])}</code></p>
        <p>Observed: {esc(m['observed_at'])}; evidence age at export: {esc(m['age_seconds'])} seconds.</p>
        <p>{esc(coverage)}. Cloud suitability: unassessed.</p>
        <details><summary>Verification and next check</summary><pre>{esc(json.dumps(ev,indent=2))}</pre></details></article>'''
    history='<pre>'+esc(json.dumps(report['attempts'],indent=2))+'</pre>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Lab 05 batch report</title><style>body{{font:16px system-ui;max-width:1120px;margin:35px auto;padding:0 24px;color:#172a3a;background:#f4f7f8}}h1{{font-size:32px}}a{{color:#11617c}}.cards{{display:flex;flex-wrap:wrap;gap:12px}}.card,article{{background:white;border:1px solid #ccd9df;border-radius:7px;padding:18px}}.card{{min-width:100px;text-decoration:none}}strong{{display:block;font-size:29px}}article{{margin:20px 0;scroll-margin-top:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}code{{overflow-wrap:anywhere}}.note{{padding:15px;background:#fff0c9}}h2{{font-size:19px}}</style>
    <h1>Can we explain this batch?</h1><p>Expected members: {report['summary']['expected']}. Application attempts: {report['attempt_count']}. Producing attempts: {report['production_count']}.</p>
    <p>Generated {esc(report['generated_at'])}. Query version {esc(report['query_version'])}.</p><p class="note">This is a saved report. File checks have their own times. Finite NDVI coverage does not establish clear sky coverage.</p>
    <div class="cards">{cards}</div>{groups}<p><a href="preview.png">Open the real NDVI contact sheet</a></p>{details}<h2>Application attempt history</h2>{history}<details><summary>Report identity and snapshot</summary><pre>{esc(json.dumps({k:v for k,v in report.items() if k not in ('members','attempts')},indent=2))}</pre></details></html>'''

def export(manifest,directory):
    directory=Path(directory).resolve()
    if directory.exists(): raise FileExistsError('Report destination exists; use a new report directory')
    directory.mkdir(parents=True)
    snapshot=directory/'catalogue.sqlite'
    # The backup API yields a consistent snapshot even if another process writes.
    with batch_store.connect(manifest['_database']) as source,batch_store.connect(snapshot,create=True) as target:
        source.backup(target)
    with batch_store.connect(snapshot) as c:report=read_report(c,manifest)
    report['snapshot']={'file':'catalogue.sqlite','sha256':store.file_hash(snapshot),'captured_at':store.now(),'cutoff_note':'Consistent database backup; observation times remain explicit'}
    (directory/'manifest.json').write_text(json.dumps({k:v for k,v in manifest.items() if not k.startswith('_')},indent=2),encoding='utf-8')
    try:
        preview(report,directory/'preview.png')
        report['preview']='preview.png'
    except (ImportError,OSError,ValueError) as exc:
        report['preview_error']=str(exc)
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    markup=render(report)
    if 'preview' not in report:
        markup=markup.replace('<p><a href="preview.png">Open the real NDVI contact sheet</a></p>', '<p>No contact sheet was available; inspect the verification evidence.</p>')
    (directory/'index.html').write_text(markup,encoding='utf-8')
    return {'report':str(directory/'index.html'),'json':str(directory/'report.json'),**report['summary']}

def preview(report,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio
    cmap=plt.get_cmap('RdYlGn').copy();cmap.set_bad('#d9e1e5');cmap.set_over('#d625bd');cmap.set_under('#2367da')
    n=len(report['members']);fig,axes=plt.subplots((n+1)//2,2,figsize=(10,3.5*((n+1)//2)),squeeze=False,layout='constrained')
    image=None
    for ax,m in zip(axes.flat,report['members']):
        ev=(m['evidence'] or {}).get('result',{})
        p=Path(ev.get('path','__absent__'))
        if m['state']=='complete' and p.is_file() and store.file_hash(p)==ev.get('sha256'):
            with rasterio.open(p) as src:data=src.read(1,masked=True)
            image=ax.imshow(data,cmap=cmap,vmin=-1,vmax=1)
            ax.set_title(m['member_id'].replace('_L2A-','\n'),fontsize=9)
        else:
            ax.text(.5,.5,m['state'] or 'unobserved',ha='center',va='center',transform=ax.transAxes)
            ax.set_title(m['member_id'],fontsize=8)
        ax.set_axis_off()
    if image is not None:fig.colorbar(image,ax=axes.ravel().tolist(),shrink=.6,label='NDVI; blue < -1, magenta > 1',extend='both')
    fig.suptitle('Real Sentinel-2 AOIs · nodata only · clouds not screened')
    fig.savefig(path,dpi=140);plt.close(fig)
