"""Inspect NDVI from local red/NIR subsets. Source files are opened read only."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def read_pair(red_path, nir_path):
    bands, metadata = {}, {}
    for role, path in (('red', red_path), ('nir', nir_path)):
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f'Local {role} file does not exist: {path}')
        with rasterio.open(path) as src:
            if src.count != 1 or src.crs is None:
                raise ValueError('Each input must be one band with a CRS')
            if src.width * src.height > 1_000_000:
                raise ValueError('Use small AOI subsets, at most 1,000,000 pixels per band')
            if not np.isfinite([src.scales[0], src.offsets[0]]).all() or src.scales[0] <= 0:
                raise ValueError('Require finite scale/offset and a positive scale')
            bands[role] = src.read(1, masked=True)
            metadata[role] = {
                'path': str(path), 'sha256': sha256(path),
                'shape': [src.height, src.width], 'crs': src.crs.to_string(),
                'transform': list(src.transform)[:6], 'dtype': src.dtypes[0],
                'nodata': src.nodata, 'scale': src.scales[0],
                'offset': src.offsets[0], 'tags': src.tags(),
            }
    for key in ('shape', 'crs', 'transform'):
        if metadata['red'][key] != metadata['nir'][key]:
            raise ValueError(f'Band grids differ: {key}; no resampling is performed')
    return bands, metadata

def calculate(bands, calibration, epsilon=0.0):
    """Use Lab 03 arithmetic and its positive-denominator masking policy."""
    reflectance = {}
    source_valid = np.ones(bands['red'].shape, dtype=bool)
    for role in ('red', 'nir'):
        raw = bands[role]
        source_valid &= ~np.ma.getmaskarray(raw) & np.isfinite(raw.data)
        reflectance[role] = (raw.astype('float32') * calibration[role]['scale']
                             + calibration[role]['offset'])
    red, nir = reflectance['red'], reflectance['nir']
    denominator = nir + red
    # Preserve the original MaskedArray expression, including NumPy promotion rules.
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = np.ma.masked_where((denominator <= epsilon) | ~source_valid,
                                 (nir - red) / denominator)
    return {'ndvi': ndvi.filled(np.nan), 'denominator': denominator.data,
            'source_valid': source_valid,
            'red_reflectance': red.data, 'nir_reflectance': nir.data}

def statistics(result):
    data = result['ndvi']
    valid = np.isfinite(data)
    values = data[valid]
    source = result['source_valid']
    count = int(valid.sum())
    outside = int(np.count_nonzero(valid & ((data < -1) | (data > 1))))
    return {
        'total_pixels': int(data.size), 'ndvi_dtype': str(data.dtype),
        'source_valid_pixels': int(source.sum()),
        'ndvi_valid_pixels': count,
        'source_pixels_rejected_by_denominator': int(np.count_nonzero(source & ~valid)),
        'minimum': float(values.min()) if count else None,
        'maximum': float(values.max()) if count else None,
        'median': float(np.median(values)) if count else None,
        'outside_minus1_plus1': outside,
        'outside_percent_of_valid': 100 * outside / count if count else None,
        'negative_red_reflectance_pixels': int(np.count_nonzero(source & (result['red_reflectance'] < 0))),
        'negative_nir_reflectance_pixels': int(np.count_nonzero(source & (result['nir_reflectance'] < 0))),
    }

def histogram_edges(results):
    largest = max((float(np.max(np.abs(r['ndvi'][np.isfinite(r['ndvi'])])))
                   for r in results if np.isfinite(r['ndvi']).any()), default=1.0)
    positive = np.geomspace(1, max(1.000001, largest * 1.001), 80)
    return np.unique(np.concatenate((-positive[::-1], np.linspace(-1, 1, 81), positive)))

def map_panel(ax, data, title):
    import matplotlib.pyplot as plt
    cmap = plt.get_cmap('RdYlGn').copy()
    cmap.set_bad('#dddddd')
    cmap.set_under('#1764c0')
    cmap.set_over('#d000ad')
    image = ax.imshow(np.ma.masked_invalid(data), vmin=-1, vmax=1, cmap=cmap)
    ax.set(title=title, xlabel='Column', ylabel='Row')
    return image

def histogram_panel(ax, results, labels):
    edges = histogram_edges(results)
    for result, label in zip(results, labels):
        values = result['ndvi'][np.isfinite(result['ndvi'])]
        counts, _ = np.histogram(values, bins=edges)
        ax.stairs(counts, edges, label=f'{label}: {values.size:,} valid', linewidth=1.6)
    ax.set_xscale('symlog', linthresh=1)
    ax.set_yscale('log')
    ax.axvline(-1, color='gray', linestyle=':', linewidth=1)
    ax.axvline(1, color='gray', linestyle=':', linewidth=1)
    ax.set(xlabel='NDVI (linear between -1 and 1; logarithmic outside)',
           ylabel='Pixel count (log scale)', title='Full value distribution; no outliers discarded')
    ax.legend(fontsize=9)

def write_examples(path, bands, result, limit=12):
    valid = np.flatnonzero(np.isfinite(result['ndvi']))
    order = valid[np.argsort(np.abs(result['ndvi'].ravel()[valid]))[-limit:][::-1]]
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['row', 'column', 'red_dn', 'nir_dn', 'red_reflectance',
                         'nir_reflectance', 'denominator', 'ndvi'])
        for flat in order:
            row, col = np.unravel_index(flat, result['ndvi'].shape)
            writer.writerow([row, col, bands['red'].data[row, col], bands['nir'].data[row, col],
                result['red_reflectance'][row, col], result['nir_reflectance'][row, col],
                result['denominator'][row, col], result['ndvi'][row, col]])

def base_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--red', type=Path, default=ROOT / 'data/real_red_aoi.tif')
    parser.add_argument('--nir', type=Path, default=ROOT / 'data/real_nir_aoi.tif')
    parser.add_argument('--out-dir', type=Path, default=Path('visual_check_output'))
    parser.add_argument('--show', action='store_true', help='Also open the figure interactively')
    return parser

def main():
    args = base_parser(__doc__).parse_args()
    import matplotlib
    if not args.show:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bands, metadata = read_pair(args.red, args.nir)
    result = calculate(bands, metadata)
    summary = statistics(result)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout='constrained')
    image = map_panel(axes[0], result['ndvi'], 'NDVI produced by the supplied calculation')
    fig.colorbar(image, ax=axes[0], extend='both', label='NDVI')
    histogram_panel(axes[1], [result], ['Supplied calculation'])
    fig.suptitle('Inspect the result before trusting it', fontsize=16)
    fig.supxlabel('Gray = masked; blue < -1; magenta > 1. Map limits affect display only.', fontsize=10)
    fig.savefig(args.out_dir / 'ndvi_visual_check.png', dpi=160)
    report = {'inputs': metadata, 'statistics': summary,
              'mask_policy': 'Source nodata plus denominator <= 0; no cloud screening',
              'display': 'Map uses -1 to 1, with distinct colors outside; histogram includes all finite values'}
    (args.out_dir / 'ndvi_visual_check.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    write_examples(args.out_dir / 'pixels_to_investigate.csv', bands, result)
    print(json.dumps(summary, indent=2))
    print('Saved figure, input metadata/statistics, and pixel examples in', args.out_dir.resolve())
    if args.show:
        plt.show()
    plt.close(fig)

if __name__ == '__main__':
    main()
