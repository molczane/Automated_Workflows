"""Calibrate once, screen native observations, align, then apply the AOI."""
import math
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject, transform_bounds
from .acquisition import polygon_in_crs


def inspect(path, record):
    meta = record["raster"]
    with rasterio.open(path) as src:
        actual = {"shape": [src.height,src.width], "crs": src.crs.to_string() if src.crs else None,
                  "transform": list(src.transform)[:6], "dtype": src.dtypes[0], "nodata": src.nodata,
                  "scale": src.scales[0], "offset": src.offsets[0]}
        if src.count != 1 or any(actual[k] != meta[k] for k in actual):
            raise ValueError("Input header differs from the registered artifact")
        data = src.read(1)
        mask = src.read_masks(1) > 0
    return data, mask


def target_grid(records, resolution):
    first = next(iter(records.values()))
    crs = rasterio.crs.CRS.from_string(first["raster"]["crs"])
    if not crs.is_projected or crs.linear_units not in ("metre", "meter"):
        raise ValueError("Use a projected grid with meter units for area calculations")
    for role, record in records.items():
        for field in ("collection", "item_id", "aoi_key", "aoi"):
            if record["lineage"][field] != first["lineage"][field]:
                raise ValueError("Input scene/AOI lineage differs for " + role)
        if record["raster"]["crs"] != crs.to_string() or record["lineage"]["asset_key"] != role:
            raise ValueError("Require matching source CRS and correct spectral roles")
    bbox = first["lineage"]["aoi"]["bbox"]
    w, s, e, n = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
    w, s = math.floor(w/resolution)*resolution, math.floor(s/resolution)*resolution
    e, n = math.ceil(e/resolution)*resolution, math.ceil(n/resolution)*resolution
    height, width = round((n-s)/resolution), round((e-w)/resolution)
    if height*width > 1000000 or height < 1 or width < 1:
        raise ValueError("Target grid exceeds one million pixels or is empty")
    return {"crs": crs.to_string(), "transform": [resolution,0,w,0,-resolution,n], "shape": [height,width], "aoi_bbox": bbox}


def warp(data, source_meta, target, categorical=False):
    out = np.zeros(target["shape"], dtype="uint8" if categorical else "float32")
    reproject(data, out, src_transform=Affine(*source_meta["transform"]), src_crs=source_meta["crs"],
              dst_transform=Affine(*target["transform"]), dst_crs=target["crs"],
              src_nodata=None, dst_nodata=0, resampling=Resampling.nearest if categorical else Resampling.average)
    return out


def prepare(records, paths, settings, required_bands):
    target = target_grid(records, settings["resolution_m"])
    inside = geometry_mask([polygon_in_crs(target["aoi_bbox"], target["crs"])], out_shape=tuple(target["shape"]),
                           transform=Affine(*target["transform"]), invert=True)
    if not inside.any():
        raise ValueError("No target pixel centers lie inside this AOI")
    scl_record = records["scl"]
    scl, scl_mask = inspect(paths["scl"], scl_record)
    if np.any(scl > 11):
        raise ValueError("Unknown SCL class value")
    scl = np.where(scl_mask, scl, 0).astype("uint8")
    target_scl = warp(scl, scl_record["raster"], target, categorical=True)
    excluded = settings["excluded_scl"] if settings["mask_policy"] == "scl" else [0,1]
    common_raw = inside.copy()
    common_clear = inside & ~np.isin(target_scl, excluded)
    bands = {}
    for role in required_bands:
        meta = records[role]["raster"]
        raw, native_valid = inspect(paths[role], records[role])
        # SCL is categorical: align to each native band with nearest neighbor.
        native_scl = warp(scl, scl_record["raster"], meta, categorical=True)
        native_valid &= (raw != meta["nodata"])
        reflectance = raw.astype("float64") * meta["scale"] + meta["offset"]
        native_valid &= np.isfinite(reflectance)
        native_clear = native_valid & ~np.isin(native_scl, excluded)
        raw_coverage = warp(native_valid.astype("float32"), meta, target)
        clear_coverage = warp(native_clear.astype("float32"), meta, target)
        common_raw &= raw_coverage >= 0.999
        common_clear &= clear_coverage >= 0.999
        # Mask before continuous resampling; avoid mixing cloud reflectance into a clear result.
        summed = warp(np.where(native_clear, reflectance, 0).astype("float32"), meta, target)
        aligned = np.full(target["shape"], np.nan, dtype="float32")
        np.divide(summed, clear_coverage, out=aligned, where=clear_coverage > 0)
        bands[role] = aligned
    for role in bands:
        bands[role][~common_clear] = np.nan
    metrics = {"aoi_pixels": int(inside.sum()), "grid_pixels": int(inside.size),
               "raw_valid_pixels": int(common_raw.sum()), "raw_valid_fraction": float(common_raw.sum()/inside.sum()),
               "clear_input_pixels": int(common_clear.sum()), "clear_input_fraction": float(common_clear.sum()/inside.sum()),
               "scl_counts_in_aoi": {str(k):int(np.count_nonzero(inside & (target_scl == k))) for k in range(12)},
               "cloud_screened": settings["mask_policy"] == "scl" and {3,8,9,10} <= set(excluded), "mask_policy": settings["mask_policy"],
               "excluded_scl": excluded, "reflectance_resampling": "average; require >=0.999 valid source fraction",
               "scl_resampling": "nearest", "pixel_area_m2": float(settings["resolution_m"]**2),
               "area_convention": "projected UTM grid area; pixel centers inside AOI"}
    return bands, common_clear, inside, target, metrics


def validate_result(result, product, valid, inside):
    if set(result.layers) != set(product.output_roles):
        raise ValueError("Returned output roles differ from product declaration")
    for role, value in result.layers.items():
        data = np.asarray(value, dtype="float32")
        if data.shape != inside.shape or np.isinf(data).any():
            raise ValueError("Invalid output shape or infinite values: " + role)
        if np.any(np.isfinite(data) & ~valid):
            raise ValueError("Product returned observations outside prepared valid pixels")
        result.layers[role] = data
    primary = result.layers[product.primary_role]
    usable = valid & np.isfinite(primary)
    for role, data in result.layers.items():
        if np.any(np.isfinite(data) & ~usable):
            raise ValueError("Output exists where primary output is unknown: " + role)
    return usable
