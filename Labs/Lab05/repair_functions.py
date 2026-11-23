"""Instructor reference implementations for the three repair exercises."""
import hashlib
import json
import math
import numpy as np

def make_request_spec(science, inputs, environment, runtime):
    settings = {key: science[key] for key in
                ('grid_policy','scaling','mask_policy','denominator_epsilon','min_valid_fraction','calibration')}
    settings['denominator_epsilon'] = float(settings['denominator_epsilon'])
    settings['min_valid_fraction'] = float(settings['min_valid_fraction'])
    ordered = []
    for role in ('red','nir'):
        record = inputs[role]
        ordered.append({'role':role, **{key:record[key] for key in
                       ('artifact_id','sha256','size_bytes','raster','lineage')}})
    spec = {'stage':science['stage'], 'settings':settings, 'inputs':ordered,
            'environment':environment, 'equivalence_policy':'exact_environment_v1'}
    text = json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False)
    return spec,hashlib.sha256(text.encode()).hexdigest()

def validate_pair(red, nir):
    if red['artifact_id'] == nir['artifact_id']:
        raise ValueError('Red and NIR must be different artifacts')
    for role, record in (('red',red),('nir',nir)):
        meta,lineage = record['raster'],record['lineage']
        if meta['asset_key'] != role or lineage['asset_key'] != role:
            raise ValueError(f'Artifact does not supply the {role} role')
        if meta['dtype'] != 'uint16' or not meta['crs']:
            raise ValueError('Require a native uint16 band and explicit CRS')
        if len(meta['shape']) != 2 or any(isinstance(v,bool) or not isinstance(v,int) or v<=0 for v in meta['shape']):
            raise ValueError('Invalid grid shape')
        transform = meta['transform']
        if len(transform)!=6 or not all(math.isfinite(v) for v in transform) or transform[0]*transform[4]-transform[1]*transform[3]==0:
            raise ValueError('Invalid pixel transform')
        if not math.isfinite(meta['scale']) or meta['scale']<=0 or not math.isfinite(meta['offset']) or not math.isfinite(meta['nodata']):
            raise ValueError('Missing or invalid radiometric metadata')
    for key in ('shape','crs','transform'):
        if red['raster'][key] != nir['raster'][key]:
            raise ValueError(f'Band grids disagree: {key}')
    for key in ('collection','item_id','aoi_key','aoi','recipe_version'):
        if red['lineage'][key] != nir['lineage'][key]:
            raise ValueError(f'Band lineage differs: {key}')

def calculate_ndvi(red, nir, red_meta, nir_meta, epsilon):
    raw_red = np.asarray(red)
    raw_nir = np.asarray(nir)
    red_reflectance = raw_red.astype('float64') * red_meta['scale'] + red_meta['offset']
    nir_reflectance = raw_nir.astype('float64') * nir_meta['scale'] + nir_meta['offset']
    denominator = nir_reflectance + red_reflectance
    valid = ((raw_red != red_meta['nodata']) & (raw_nir != nir_meta['nodata']) &
             np.isfinite(red_reflectance) & np.isfinite(nir_reflectance) &
             (np.abs(denominator) > epsilon))
    output = np.full(raw_red.shape,np.nan,dtype='float32')
    np.divide(nir_reflectance-red_reflectance,denominator,out=output,where=valid)
    return output
