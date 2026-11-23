"""Serial coordination with persistent budgets and explicit recovery boundaries."""
import os
import batch_store
import job_adapter
import processing_store as store

def inspect_all(c,manifest,persist=False):
    rows=[]
    for member in manifest['frozen']['members']:
        result=job_adapter.inspect_member(c,member,manifest['frozen']['execution']['max_attempts_per_request'])
        active=c.execute("SELECT attempt_id FROM processing_attempts WHERE status='running'").fetchone()
        if result['state']=='ready' and active:
            result.update(state='blocked',reason='Catalogue has an unresolved execution: '+active[0])
        if persist: batch_store.observe(c,manifest,member,result)
        rows.append(result)
    return rows

def run(manifest,stop_after=None,simulate_member=None,simulate=None,crash_coordinator=False):
    invocations=[]
    with batch_store.writer_lock(manifest['_database']),batch_store.connect(manifest['_database']) as c:
        batch_store.check_shape(c);batch_store.register(c,manifest)
        for member in manifest['frozen']['members']:
            result=job_adapter.inspect_member(c,member,manifest['frozen']['execution']['max_attempts_per_request'])
            global_active=c.execute("SELECT attempt_id FROM processing_attempts WHERE status='running'").fetchone()
            if result['state']=='ready' and global_active:
                result.update(state='blocked',reason='Catalogue has an unresolved execution: '+global_active[0])
            batch_store.observe(c,manifest,member,result)
            if result['state']!='ready': continue
            batch_store.attach_request(c,manifest,member)
            launched=job_adapter.invoke(manifest,member,simulate if member['member_id']==simulate_member else None)
            result=job_adapter.inspect_member(c,member,manifest['frozen']['execution']['max_attempts_per_request'])
            result['invocation']=launched
            if launched['exit_code'] and result['state']=='ready':
                result.update(state='failed',reason='CLI failed before verified completion; inspect invocation evidence')
            batch_store.observe(c,manifest,member,result)
            invocations.append({'member_id':member['member_id'],**launched})
            if crash_coordinator:
                os._exit(87)  # Isolated exercise only; operating system releases writer lock.
            if stop_after is not None and len(invocations)>=stop_after: break
        observations=inspect_all(c,manifest,persist=True)
    return {'batch_id':manifest['batch_id'],'invocations':invocations,'observations':observations,
            'complete':all(r['state']=='complete' for r in observations)}
