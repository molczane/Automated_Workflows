"""Focused feedback on the new schema and the three logical repairs."""
import argparse
import copy
import json
import sqlite3
from pathlib import Path
import batch_repairs as repairs
import batch_store
import processing_store as store

ROOT=Path(__file__).resolve().parent

def schema_check():
    with batch_store.connect(':memory:') as c:
        for name in ('lab02_base_schema.sql','lab03_reference_schema.sql','lab04_processing_schema.sql'):
            c.executescript((ROOT/'support'/name).read_text())
        batch_store.initialize(c)
        c.execute('INSERT INTO batches VALUES (?,?,?)',('batch-test','{}',store.now()))
        c.execute('INSERT INTO batch_members VALUES (?,?,?,NULL,?)',('batch-test','expected','request-test','{}'))
        def rejected(sql,params=()):
            try: c.execute(sql,params)
            except sqlite3.IntegrityError:return
            raise AssertionError('Constraint failed to reject: '+sql)
        rejected("INSERT INTO batch_members VALUES ('batch-test','expected','other',NULL,'{}')")
        rejected("INSERT INTO batch_members VALUES ('batch-test','second','request-test',NULL,'{}')")
        rejected("INSERT INTO batch_members VALUES ('absent','orphan','request-orphan',NULL,'{}')")
        rejected("INSERT INTO batches VALUES ('bad-json','broken','now')")
        rejected("INSERT INTO batch_members VALUES ('batch-test','wrong','request-p','request-q','{}')")
        rejected("INSERT INTO batch_observations(batch_id,member_id,observed_at,state,reason,evidence_json) VALUES ('batch-test','expected','now','green','why','{}')")
        rejected("INSERT INTO batch_observations(batch_id,member_id,observed_at,state,reason,evidence_json) VALUES ('batch-test','absent','now','ready','why','{}')")
        c.execute("INSERT INTO batch_observations(batch_id,member_id,observed_at,state,reason,evidence_json) VALUES ('batch-test','expected','now','blocked','missing input','{}')")
        c.execute("INSERT INTO batch_observations(batch_id,member_id,observed_at,state,reason,evidence_json) VALUES ('batch-test','expected','later','ready','input restored','{}')")
        assert c.execute('SELECT COUNT(*) FROM batch_observations').fetchone()[0]==2

def classify_check():
    base={'active_attempt':None,'verified_result':None,'missing_inputs':[],
          'validation_error':None,'attempts_used':0,'max_attempts':2,'last_attempt':None}
    cases=[({},'ready'),({'missing_inputs':['red']},'blocked'),
           ({'validation_error':'Shifted grid'},'failed'),
           ({'attempts_used':2},'failed'),
           ({'last_attempt':{'status':'failed','error_code':'ValueError'}},'failed'),
           ({'last_attempt':{'status':'interrupted','error_code':'PROCESS_STOPPED_BEFORE_PUBLISH'},'attempts_used':1},'ready'),
           ({'verified_result':{'artifact_id':'verified'},'attempts_used':2,'missing_inputs':['red']},'complete'),
           ({'active_attempt':{'attempt_id':'still-running'},'verified_result':{'artifact_id':'old'}},'unresolved')]
    for changes,expected in cases:
        result=repairs.classify_member({**base,**changes})
        assert result['state']==expected,(changes,expected,result)
        assert result['reason'].strip()

def verify_check():
    fixtures=json.loads((ROOT/'fixtures/manifest.json').read_text())
    real=fixtures['members'][0]['bands']['red']
    member={'request_id':'request-expected'}
    evidence={'request_id':member['request_id'],'attempt_id':'producing-attempt','artifact_id':'verified-output',
        'catalogue_link_verified':True,'grid_verified':True,'provenance_verified':True,
        'sha256':real['sha256'],'actual_sha256':real['sha256'],
        'size_bytes':real['size_bytes'],'actual_size_bytes':real['size_bytes']}
    assert repairs.verify_result(member,evidence)
    for key,value in [('request_id','request-other'),('actual_sha256','0'*64),('actual_size_bytes',1),
                      ('catalogue_link_verified',False),('grid_verified',False),('provenance_verified',False),('attempt_id',None)]:
        assert not repairs.verify_result(member,{**evidence,key:value}),key
    incomplete={k:v for k,v in evidence.items() if k not in ('sha256','actual_sha256')}
    assert not repairs.verify_result(member,incomplete)

def summary_check():
    # Repeated observations model retries/location joins; the NULL row models never observed work.
    rows=[{'member_id':'one','observation_id':1,'state':'failed'},
          {'member_id':'one','observation_id':4,'state':'complete'},
          {'member_id':'one','observation_id':4,'state':'complete'},
          {'member_id':'two','observation_id':3,'state':'blocked'},
          {'member_id':'three','observation_id':-1,'state':None}]
    result=repairs.summarize_batch(list(reversed(rows)))
    assert result['expected']==3,result
    assert result['counts']=={'ready':0,'complete':1,'blocked':1,'unresolved':0,'failed':0,'unobserved':1},result
    assert result['members']['complete']==['one']

CHECKS={'schema':schema_check,'classify':classify_check,'verify':verify_check,'summary':summary_check}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('group',choices=(*CHECKS,'all'),default='all',nargs='?');a=p.parse_args()
    results=[]
    for name,func in CHECKS.items():
        if a.group not in (name,'all'):continue
        try:func();results.append({'check':name,'passed':True})
        except Exception as exc:results.append({'check':name,'passed':False,'reason':str(exc) or type(exc).__name__})
    print(json.dumps(results,indent=2));return 0 if all(x['passed'] for x in results) else 1
if __name__=='__main__':raise SystemExit(main())
