"""Bounded, explicit Collection 1 acquisition for chosen AOIs and products."""
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import transform, transform_bounds
from rasterio.windows import Window, from_bounds
from .common import file_hash, now, read_json, safe_name, write_json
from .range_reader import RangeSession

ENDPOINT = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
SUPPORTED = {"blue", "green", "red", "nir", "nir08", "rededge1", "rededge2", "rededge3", "swir16", "swir22", "scl"}


def get_json(url, body=None):
    payload = None if body is None else json.dumps(body).encode()
    request = Request(url, data=payload, headers={"User-Agent": "AGH-optical-lab06/1.0", "Content-Type": "application/json"})
    with urlopen(request, timeout=40) as response:
        return json.load(response)


def check_bbox(bbox):
    if len(bbox) != 4 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in bbox):
        raise ValueError("bbox must be [west,south,east,north] in degrees")
    w, s, e, n = bbox
    if not -180 <= w < e <= 180 or not -80 <= s < n <= 84:
        raise ValueError("Use a small bbox inside a single UTM tile, without crossing the date line")
    return list(map(float, bbox))


def polygon_in_crs(bbox, crs):
    w, s, e, n = bbox
    ring = []
    for a, b in [((w,s),(e,s)), ((e,s),(e,n)), ((e,n),(w,n)), ((w,n),(w,s))]:
        ring.extend((a[0] + (b[0]-a[0])*i/32, a[1] + (b[1]-a[1])*i/32) for i in range(32))
    ring.append(ring[0])
    xs, ys = transform("EPSG:4326", crs, [p[0] for p in ring], [p[1] for p in ring])
    return {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}


def search(bbox, interval, max_items=20):
    bbox = check_bbox(bbox)
    if not 1 <= max_items <= 100:
        raise ValueError("max-items must be between 1 and 100")
    body = {"collections": [COLLECTION], "bbox": bbox, "datetime": interval, "limit": min(max_items, 100)}
    page = get_json(ENDPOINT + "/search", body)
    values = []; seen = set(); links_seen = set()
    while True:
        for item in page.get("features", []):
            if item["id"] not in seen:
                seen.add(item["id"])
                values.append({"id": item["id"], "datetime": item["properties"]["datetime"], "cloud_cover_tile_percent": item["properties"].get("eo:cloud_cover"), "bbox": item.get("bbox")})
            if len(values) >= max_items:
                return {"collection": COLLECTION, "items": values, "limit_reached": True}
        link = next((x for x in page.get("links", []) if x["rel"] == "next"), None)
        if not link:
            return {"collection": COLLECTION, "items": values, "limit_reached": False}
        key = json.dumps(link, sort_keys=True)
        if key in links_seen:
            raise ValueError("Search pagination repeated a link")
        links_seen.add(key)
        page = get_json(link["href"], link.get("body", body) if link.get("method", "GET") == "POST" else None)


def make_plan(item, role, bbox, max_pixels=1000000):
    if role not in SUPPORTED:
        raise ValueError("Unsupported optical band: " + role)
    asset = item["assets"][role]
    if "cloud-optimized" not in asset.get("type", ""):
        raise ValueError("Only declared COG assets are supported")
    rb = asset["raster:bands"][0]
    dtype = "uint8" if role == "scl" else "uint16"
    if rb["data_type"] != dtype or rb.get("nodata") is None:
        raise ValueError("Unexpected data type or absent nodata")
    props = item["properties"]
    crs = asset.get("proj:code", props.get("proj:code"))
    if crs is None:
        crs = "EPSG:" + str(asset.get("proj:epsg", props.get("proj:epsg")))
    crs = rasterio.crs.CRS.from_user_input(crs)
    affine = Affine(*asset["proj:transform"][:6])
    height, width = asset["proj:shape"]
    if affine.b or affine.d or affine.a <= 0 or affine.e != -affine.a:
        raise ValueError("Require a square north-up source grid")
    bounds = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
    fractional = from_bounds(*bounds, transform=affine)
    if fractional.col_off < 0 or fractional.row_off < 0 or fractional.col_off + fractional.width > width or fractional.row_off + fractional.height > height:
        raise ValueError("AOI is not wholly inside this tile; use a covering tile or a smaller AOI")
    # One native pixel of context supports alignment before the final AOI mask.
    left = max(0, math.floor(fractional.col_off) - 1)
    top = max(0, math.floor(fractional.row_off) - 1)
    right = min(width, math.ceil(fractional.col_off + fractional.width) + 1)
    bottom = min(height, math.ceil(fractional.row_off + fractional.height) + 1)
    if (right-left)*(bottom-top) > max_pixels:
        raise ValueError("AOI exceeds the native pixel budget; use a smaller AOI")
    if role != "scl" and (rb.get("scale") is None or rb.get("offset") is None):
        raise ValueError("Missing reflectance calibration metadata")
    window = Window(left, top, right-left, bottom-top)
    return {"asset_key": role, "source_url": asset["href"], "crs": crs.to_string(), "source_shape": [height, width],
            "source_transform": list(affine)[:6], "window": list(window.flatten()), "shape": [bottom-top,right-left],
            "transform": list(rasterio.windows.transform(window, affine))[:6], "dtype": dtype, "nodata": rb["nodata"],
            "scale": float(rb.get("scale", 1)), "offset": float(rb.get("offset", 0)), "aoi_bbox": bbox,
            "recipe": "native-context-v1", "calibration_basis": "Collection 1 STAC raster:bands; applied only in processing"}


def write_window(plan, path, session):
    session.get_size()
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_CACHEMAX=32*1024*1024):
            with rasterio.open(session.url, opener=session.opener) as src:
                actual = (src.crs.to_string(), list(src.transform)[:6], [src.height,src.width], src.dtypes[0])
                expected = (plan["crs"], plan["source_transform"], plan["source_shape"], plan["dtype"])
                if actual != expected or src.count != 1 or src.nodata != plan["nodata"]:
                    raise ValueError("Remote header differs from source metadata")
                if not np.isclose(src.scales[0], plan["scale"]) or not np.isclose(src.offsets[0], plan["offset"]):
                    raise ValueError("COG/STAC calibration disagreement; review source before continuing")
                data = src.read(1, window=Window(*plan["window"]))
    except Exception as exc:
        if session.last_error:
            raise OSError(session.last_error) from exc
        raise
    if session.last_error:
        raise OSError(session.last_error)
    if data.shape != tuple(plan["shape"]):
        raise ValueError("Unexpected subset shape")
    with rasterio.open(path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                       dtype=plan["dtype"], crs=plan["crs"], transform=Affine(*plan["transform"]), nodata=plan["nodata"],
                       compress="deflate", tiled=True, blockxsize=128, blockysize=128) as dst:
        dst.write(data, 1)
        dst.scales = (plan["scale"],)
        dst.offsets = (plan["offset"],)
        dst.update_tags(SOURCE_URL=plan["source_url"], AOI_BBOX=json.dumps(plan["aoi_bbox"]), RECIPE=plan["recipe"])


def acquire(config_path, destination):
    config = read_json(config_path)
    if set(config) != {"aois", "item_ids", "bands"}:
        raise ValueError("Acquisition config needs aois, item_ids, bands")
    if not config["aois"] or not config["item_ids"] or not config["bands"]:
        raise ValueError("Acquisition selections cannot be empty")
    if len(config["item_ids"]) > 12 or len(config["aois"]) > 4 or len(set(config["bands"])) != len(config["bands"]):
        raise ValueError("Use at most twelve dates, four AOIs and distinct bands")
    if not set(config["bands"]) <= SUPPORTED:
        raise ValueError("Unknown band in acquisition configuration")
    for name, bbox in config["aois"].items():
        safe_name(name); check_bbox(bbox)
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError("Choose a new input destination")
    destination.mkdir(parents=True)
    manifest = {"schema_version": 2, "endpoint": ENDPOINT, "collection": COLLECTION, "downloaded_at": now(),
                "source": "Actual bounded HTTPS range reads; native raw data and calibration preserved", "complete": False,
                "members": [], "transfers": []}
    write_json(destination / "manifest.json", manifest)
    total = 0
    shared_budget = {"limit":256*1024*1024,"received":0}
    for item_id in config["item_ids"]:
        safe_name(item_id)
        item = get_json(f"{ENDPOINT}/collections/{COLLECTION}/items/{item_id}")
        if item["collection"] != COLLECTION or item["id"] != item_id:
            raise ValueError("Catalogue identity differs")
        write_json(destination / (item_id + ".json"), item)
        sessions = {role: RangeSession(item["assets"][role]["href"], byte_budget=24*1024*1024,total_budget=shared_budget) for role in config["bands"]}
        for aoi, bbox in config["aois"].items():
            member = {"member_id": item_id + "-" + aoi, "item_file": item_id + ".json", "aoi_name": aoi, "bands": {}}
            for role in config["bands"]:
                plan = make_plan(item, role, bbox)
                name = member["member_id"] + "-" + role + ".tif"
                write_window(plan, destination / name, sessions[role])
                p = destination / name
                member["bands"][role] = {"file": name, "plan": plan, "sha256": file_hash(p), "size_bytes": p.stat().st_size}
            manifest["members"].append(member)
            write_json(destination / "manifest.json", manifest)
        for role, session in sessions.items():
            total += session.network_bytes
            manifest["transfers"].append({"item_id": item_id, "band": role, "network_bytes": session.network_bytes,
                                          "range_requests": session.requests, "etag": session.etag})
        if total > 256*1024*1024:
            raise ValueError("Overall acquisition budget exceeded; narrow your selection")
    manifest["complete"] = True
    write_json(destination / "manifest.json", manifest)
    return {"bundle": str(destination), "members": len(manifest["members"]), "network_bytes": total}
