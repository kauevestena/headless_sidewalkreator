# -*- coding: utf-8 -*-

"""
File intended to store "hyperparameters"


ALL DISTANCES MUST BE IN METERS, no feets nor yards
"""


CRS_LATLON_4326 = "EPSG:4326"

# to look for adresses:
addr_tag = "addr:housenumber"

minimal_buffer = 3  # 2m
from headless_sidewalkreator.parameters import *
"""Compatibility shim re-exporting package parameters.

This preserves imports like `from parameters import *` by importing the
variables from `headless_sidewalkreator.parameters`.
"""

from headless_sidewalkreator.parameters import *

__all__ = [name for name in globals().keys() if not name.startswith("_")]

