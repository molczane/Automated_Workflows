"""Copy to a name of your choosing and implement your own scientific product.

This is the only supplied Python starter that needs completing. Core code is
shared. Consult docs/PRODUCT_CONTRACT.md and the complete MNDWI implementation.
"""
import numpy as np
from eo_processing.products import ProductResult, normalized_difference


class MyProduct:
    name = "my_product"
    version = "0.1.0"
    required_bands = ("nir", "swir16")  # Replace with the inputs YOUR product needs.
    output_roles = ("index",)
    primary_role = "index"
    nominal_range = (-1.0, 1.0)  # Use None for products without an appropriate nominal range.
    default_parameters = {"epsilon": 0.000001}

    def calculate(self, bands, valid, parameters, pixel_area_m2):
        # Inputs are float arrays of calibrated, screened, aligned reflectance.
        # Start by writing the scientific equation and citing its source.
        # Return ProductResult({"index": output}, {"your_metric": value}).
        # Keep invalid observations as NaN, and do not modify input arrays.
        raise NotImplementedError("Implement and explain your chosen scientific product")


PRODUCT = MyProduct()
