"""Three plausible implementations to investigate and repair. No syntax puzzles."""
import hashlib
import json
import numpy as np

def make_request_spec(science, inputs, environment, runtime):
    """Return (normalized_spec, fingerprint). Read the contract before editing."""
    # It remembers enough to run once. Does it identify the calculation reliably?
    spec = {'stage': science['stage'], 'settings': science,
            'inputs': [inputs[role]['artifact_id'] for role in inputs],
            'output_dir': str(runtime['output_dir'])}
    fingerprint = hashlib.sha256(json.dumps(spec).encode()).hexdigest()
    return spec, fingerprint

def validate_pair(red, nir):
    """Raise ValueError if metadata cannot justify a red/NIR calculation."""
    # Both arrays have the same size, so this seems safe at first glance.
    if red['raster']['shape'] != nir['raster']['shape']:
        raise ValueError('Input shapes differ')

def calculate_ndvi(red, nir, red_meta, nir_meta, epsilon):
    """Return float32 NDVI; invalid pixels must be NaN. Inputs are stored DN."""
    # Shared scaling cancels in a ratio. Is that the whole calibration here?
    with np.errstate(divide='ignore', invalid='ignore'):
        return ((nir - red) / (nir + red)).astype('float32')
