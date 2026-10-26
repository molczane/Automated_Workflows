"""Request identity, input compatibility and calibrated NDVI for Lab 04."""
import hashlib
import json
import math
import numpy as np


def _normalize_json(value):
    """Copy JSON data while giving equivalent numeric values one representation."""
    if isinstance(value, dict):
        return {key: _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Request identity cannot contain nonfinite numbers')
        return int(value) if value.is_integer() else value
    return value


def make_request_spec(science, inputs, environment, runtime):
    """Return the complete calculation identity and its canonical JSON SHA-256."""
    if environment.get('policy') != 'exact_environment_v1':
        raise ValueError('Require the exact_environment_v1 equivalence policy')
    if set(inputs) != {'red', 'nir'}:
        raise ValueError('Require exactly the red and nir input roles')
    # Runtime paths and registration times do not describe the calculation.
    # Resolved input records, rather than the config's input references, identify
    # the bytes, interpretation and lineage used in each explicit role.
    spec = _normalize_json({
        'equivalence_policy': 'exact_environment_v1',
        'stage': science['stage'],
        'settings': {key: value for key, value in science.items() if key != 'inputs'},
        'inputs': [
            {'role': role, **{key: inputs[role][key] for key in
                             ('artifact_id', 'sha256', 'size_bytes', 'raster', 'lineage')}}
            for role in ('red', 'nir')
        ],
        'environment': environment,
    })
    encoded = json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return spec, hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _calibration(meta, role):
    """Require finite radiometric metadata without assuming a zero offset."""
    values = []
    for key in ('scale', 'offset', 'nodata'):
        value = meta.get(key)
        if (isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.integer, np.floating))
                or not math.isfinite(float(value))):
            raise ValueError(f'{role} {key} must be a finite number')
        values.append(float(value))
    if values[0] <= 0:
        raise ValueError(f'{role} scale must be positive')
    return values


def validate_pair(red, nir):
    """Reject incompatible lineage, grids, band roles or radiometric metadata."""
    for role, record in (('red', red), ('nir', nir)):
        required = {
            'lineage': {'asset_key', 'collection', 'item_id', 'aoi_key', 'aoi', 'recipe_version'},
            'raster': {'asset_key', 'crs', 'shape', 'transform', 'recipe', 'aoi_bbox'},
        }
        for section, keys in required.items():
            if (not isinstance(record, dict) or not isinstance(record.get(section), dict)
                    or not keys.issubset(record[section])):
                raise ValueError(f'{role} requires complete {section} metadata')
        lineage, raster = record['lineage'], record['raster']
        if lineage['asset_key'] != role or raster['asset_key'] != role:
            raise ValueError(f'Expected the {role} source band in the {role} role')
        _calibration(raster, role)
        if not isinstance(raster['crs'], str) or not raster['crs'].strip():
            raise ValueError(f'{role} requires a CRS')
        shape = np.asarray(raster['shape'], dtype='float64')
        transform = np.asarray(raster['transform'], dtype='float64')
        if (shape.shape != (2,) or not np.isfinite(shape).all()
                or np.any(shape <= 0) or np.any(shape != np.floor(shape))):
            raise ValueError(f'{role} requires a positive integer raster shape')
        if transform.shape != (6,) or not np.isfinite(transform).all():
            raise ValueError(f'{role} requires a finite six-value pixel transform')
        if (not isinstance(lineage['aoi'], dict)
                or not {'crs', 'bbox'}.issubset(lineage['aoi'])):
            raise ValueError(f'{role} requires AOI geometry')
        if (raster.get('recipe') != lineage['recipe_version']
                or raster.get('aoi_bbox') != lineage['aoi'].get('bbox')):
            raise ValueError(f'{role} raster plan disagrees with its extraction lineage')
    for key in ('collection', 'item_id', 'aoi_key', 'recipe_version', 'aoi'):
        value = red['lineage'][key]
        if value is None or value == '' or value != nir['lineage'][key]:
            raise ValueError(f'Input lineage differs or is missing: {key}')
    for key in ('crs', 'shape', 'transform'):
        if red['raster'][key] != nir['raster'][key]:
            raise ValueError(f'Input grids differ: {key}')


def calculate_ndvi(red, nir, red_meta, nir_meta, epsilon):
    """Return unclipped float32 NDVI with NaN for nodata/invalid calculations."""
    red_scale, red_offset, red_nodata = _calibration(red_meta, 'red')
    nir_scale, nir_offset, nir_nodata = _calibration(nir_meta, 'nir')
    if (isinstance(epsilon, (bool, np.bool_)) or not np.isscalar(epsilon)
            or not math.isfinite(float(epsilon)) or float(epsilon) < 0):
        raise ValueError('Denominator epsilon must be finite and nonnegative')
    # Casting before either sum or difference prevents uint16 wraparound. Honor
    # an existing array mask as well as the original DN nodata sentinel.
    red_dn = np.ma.asarray(red, dtype='float64').filled(np.nan)
    nir_dn = np.ma.asarray(nir, dtype='float64').filled(np.nan)
    if red_dn.shape != nir_dn.shape:
        raise ValueError('Input arrays must have matching shapes')
    valid = (np.isfinite(red_dn) & np.isfinite(nir_dn)
             & (red_dn != red_nodata) & (nir_dn != nir_nodata))
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        red_reflectance = red_dn * red_scale + red_offset
        nir_reflectance = nir_dn * nir_scale + nir_offset
        denominator = nir_reflectance + red_reflectance
        valid &= (np.isfinite(red_reflectance) & np.isfinite(nir_reflectance)
                  & np.isfinite(denominator) & (np.abs(denominator) > float(epsilon)))
        result = np.full(red_dn.shape, np.nan, dtype='float32')
        result[valid] = ((nir_reflectance[valid] - red_reflectance[valid])
                         / denominator[valid]).astype('float32')
    result[~np.isfinite(result)] = np.nan
    return result
