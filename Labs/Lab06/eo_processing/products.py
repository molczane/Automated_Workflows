"""Product contract: prepared reflectance in, named raster products out."""
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import numpy as np
from .common import file_hash, safe_name


@dataclass
class ProductResult:
    layers: dict  # role -> float32-compatible array; NaN means unknown
    metrics: dict


def normalized_difference(a, b, epsilon):
    """Arguments are calibrated reflectances. Do not clip unusual values."""
    a, b = np.asarray(a, dtype="float64"), np.asarray(b, dtype="float64")
    denominator = a + b
    valid = np.isfinite(a) & np.isfinite(b) & (np.abs(denominator) > epsilon)
    output = np.full(a.shape, np.nan, dtype="float32")
    np.divide(a - b, denominator, out=output, where=valid)
    return output


class MNDWI:
    name = "mndwi"
    version = "1.0.0"
    required_bands = ("green", "swir16")
    output_roles = ("index", "water")
    primary_role = "index"
    nominal_range = (-1.0, 1.0)
    default_parameters = {"epsilon": 0.000001, "threshold": 0.0}

    def calculate(self, bands, valid, parameters, pixel_area_m2):
        index = normalized_difference(bands["green"], bands["swir16"], parameters["epsilon"])
        index[~valid] = np.nan
        observed = np.isfinite(index)
        water = np.full(index.shape, np.nan, dtype="float32")
        water[observed] = (index[observed] > parameters["threshold"]).astype("float32")
        return ProductResult({"index": index, "water": water}, {
            "candidate_water_pixels": int(np.count_nonzero(water == 1)),
            "candidate_water_area_m2": float(np.count_nonzero(water == 1) * pixel_area_m2),
            "observed_area_m2": float(observed.sum() * pixel_area_m2),
            "threshold": parameters["threshold"],
        })


class NDVI:
    name = "ndvi"
    version = "1.0.0"
    required_bands = ("red", "nir")
    output_roles = ("index",)
    primary_role = "index"
    nominal_range = (-1.0, 1.0)
    default_parameters = {"epsilon": 0.000001}

    def calculate(self, bands, valid, parameters, pixel_area_m2):
        result = normalized_difference(bands["nir"], bands["red"], parameters["epsilon"])
        result[~valid] = np.nan
        return ProductResult({"index": result}, {})


def load_product(name, plugin_path=None):
    safe_name(name)
    if name in ("mndwi", "ndvi"):
        if plugin_path:
            raise ValueError("Built in product does not take a plugin path")
        product = MNDWI() if name == "mndwi" else NDVI()
        source = Path(__file__)
    else:
        if not plugin_path:
            raise ValueError("A personal product requires an explicit plugin .py path")
        source = Path(plugin_path).resolve()
        spec = importlib.util.spec_from_file_location("eo_personal_" + file_hash(source), source)
        module = importlib.util.module_from_spec(spec)
        # Compile the selected source directly: avoid a stale timestamp-based .pyc
        # when a quick scientific edit keeps the source file's byte count unchanged.
        exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
        product = module.PRODUCT
        if product.name != name:
            raise ValueError("Plugin name differs from configuration")
    for field in ("name", "version", "required_bands", "output_roles", "primary_role", "default_parameters", "nominal_range"):
        if not hasattr(product, field):
            raise ValueError("Product is missing " + field)
    if not product.required_bands or len(set(product.required_bands)) != len(product.required_bands):
        raise ValueError("Declare distinct required bands")
    for role in (*product.required_bands, *product.output_roles):
        safe_name(role)
    if "scl" in product.required_bands or "valid_mask" in product.output_roles:
        raise ValueError("scl and valid_mask belong to the common preparation")
    if len(set(product.output_roles)) != len(product.output_roles) or product.primary_role not in product.output_roles:
        raise ValueError("Declare distinct outputs and a primary output")
    return product, {"name": product.name, "version": product.version,
                     "source_sha256": file_hash(source), "required_bands": list(product.required_bands),
                     "output_roles": list(product.output_roles), "primary_role": product.primary_role,
                     "nominal_range": product.nominal_range}


def parameters_for(product, values):
    if set(values) - set(product.default_parameters):
        raise ValueError("Unknown product parameter(s): " + str(set(values) - set(product.default_parameters)))
    result = {**product.default_parameters, **values}
    for key, value in result.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError("Product parameters must be finite numbers")
        result[key] = float(value)
    if "epsilon" in result and not 0 < result["epsilon"] < 1:
        raise ValueError("epsilon must be between zero and one")
    return result
