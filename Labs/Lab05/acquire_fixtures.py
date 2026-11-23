"""Explicit live route. Downloads bounded COG windows, never full tiles."""
import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib

from geo_subset import make_plan, matching_pair, write_window
from range_reader import RangeSession

ENDPOINT = 'https://earth-search.aws.element84.com/v1'
COLLECTION = 'sentinel-2-c1-l2a'
ITEMS = ['S2A_T34UDA_20250604T094637_L2A',
         'S2C_T34UDA_20250605T095638_L2A',
         'S2B_T34UDA_20250610T095316_L2A']
AOIS = {'river': [19.91, 50.04, 19.94, 50.06],
        'east': [19.94, 50.04, 19.97, 50.06]}

def download(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Choose a new destination; captured evidence is never overwritten')
    destination.mkdir(parents=True)
    manifest = {'schema_version': 1, 'endpoint': ENDPOINT, 'collection': COLLECTION,
                'source': 'Actual HTTP range reads; no generated imagery', 'complete': False, 'members': []}
    from datetime import datetime, timezone
    manifest['downloaded_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    for item_id in ITEMS:
        url = f'{ENDPOINT}/collections/{COLLECTION}/items/{item_id}'
        with urlopen(Request(url, headers={'User-Agent':'AGH-Lab05/1.0'}), timeout=45) as response:
            item = json.load(response)
        if item['collection'] != COLLECTION or item['id'] != item_id:
            raise ValueError('Catalogue response differs from pinned identity')
        item_file = item_id + '.json'
        (destination/item_file).write_text(json.dumps(item, indent=2), encoding='utf-8')
        sessions = {role: RangeSession(item['assets'][role]['href'], byte_budget=24*1024*1024)
                    for role in ('red','nir')}
        for aoi_name, bbox in AOIS.items():
            plans = [make_plan(item, role, bbox, 100000) for role in ('red','nir')]
            matching_pair(plans)
            member = {'member_id': item_id + '-' + aoi_name, 'item_file': item_file,
                      'aoi_name': aoi_name, 'bands': {}}
            for plan in plans:
                role = plan['asset_key']
                filename = member['member_id'] + '-' + role + '.tif'
                path = destination/filename
                before = sessions[role].network_bytes
                inside, valid = write_window(plan, path, sessions[role])
                member['bands'][role] = {'file':filename,'plan':plan,
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes':path.stat().st_size,
                    'inside_pixels':inside,'non_nodata_pixels':valid,
                    'network_bytes':sessions[role].network_bytes-before}
                print(json.dumps({'member':member['member_id'],'band':role,
                                  'network_bytes':member['bands'][role]['network_bytes']}), flush=True)
            manifest['members'].append(member)
        manifest.setdefault('transfers', []).extend({'item_id':item_id,'band':role,
            'network_bytes':s.network_bytes,'range_requests':s.requests,'etag':s.etag}
            for role,s in sessions.items())
        (destination/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    manifest['complete']=True
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    try:
        result = download(args.destination)
        print(json.dumps({'status':'complete','members':len(result['members'])}))
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)}), file=sys.stderr)
        raise SystemExit(1)
