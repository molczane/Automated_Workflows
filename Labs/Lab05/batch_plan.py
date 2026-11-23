"""Frozen scientific membership; storage paths remain a separate runtime concern."""
import copy
import json
from pathlib import Path
import ndvi_job as job
import processing_store as store

VERSION=1

def write_manifest(path,members,database,workspace,label='Krakow optical batch',max_attempts=2):
    frozen={'schema_version':VERSION,'label':label,'members':members,
            'execution':{'max_attempts_per_request':max_attempts}}
    result={'batch_id':'batch-'+store.digest(frozen),'frozen':frozen,
            'runtime':{'database':str(database),'workspace':str(workspace)}}
    path=Path(path)
    if path.exists(): raise FileExistsError('Choose a new manifest path')
    path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    return load(path)

def load(path,check_environment=False):
    path=Path(path).resolve()
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    value=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=unique,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    if set(value)!={'batch_id','frozen','runtime'}: raise ValueError('Unexpected manifest fields')
    frozen=value['frozen']
    if set(frozen)!={'schema_version','label','members','execution'} or frozen['schema_version']!=VERSION:
        raise ValueError('Unsupported batch manifest')
    if value['batch_id']!='batch-'+store.digest(frozen): raise ValueError('Frozen manifest changed; create an explicit new version')
    policy=frozen['execution']
    if set(policy)!={'max_attempts_per_request'} or type(policy['max_attempts_per_request']) is not int or not 1<=policy['max_attempts_per_request']<=5:
        raise ValueError('Attempt budget must be an integer from 1 through 5')
    if not frozen['members']: raise ValueError('An empty batch is not a completion demonstration')
    ids=set();requests=set();env=job.environment() if check_environment else None
    for m in frozen['members']:
        if set(m)!={'member_id','request_id','spec'}: raise ValueError('Unexpected member fields')
        if not isinstance(m['member_id'],str) or not m['member_id'] or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in m['member_id']):
            raise ValueError('Member ID must be a safe nonempty identifier')
        if m['member_id'] in ids or m['request_id'] in requests: raise ValueError('Duplicate member or scientific request')
        ids.add(m['member_id']);requests.add(m['request_id'])
        spec=m['spec']
        if m['request_id']!='request-'+store.digest(spec): raise ValueError('Request fingerprint does not match frozen specification')
        if env is not None and spec['environment']!=env: raise ValueError('Processing code/runtime changed; create a new batch manifest')
    if set(value['runtime'])!={'database','workspace'}: raise ValueError('Runtime needs database and workspace')
    value['_database']=(path.parent/value['runtime']['database']).resolve()
    value['_workspace']=(path.parent/value['runtime']['workspace']).resolve()
    value['_path']=path
    return value

def freeze_members(c,science_list):
    result=[]
    for member_id,science in science_list:
        records={role:store.input_record(c,science['inputs'][role]) for role in ('red','nir')}
        spec,fingerprint=job.repairs.make_request_spec(science,records,job.environment(),{})
        result.append({'member_id':member_id,'request_id':'request-'+fingerprint,'spec':spec})
    return result
