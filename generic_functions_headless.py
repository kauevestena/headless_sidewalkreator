"""Compatibility shim re-exporting package generic functions.

This file preserves imports such as `from generic_functions_headless import ...` used
by tests and older scripts by importing the implementation from
`headless_sidewalkreator.generic_functions`.
"""

from headless_sidewalkreator.generic_functions import *

__all__ = [
    name for name in globals().keys() if not name.startswith("_")
]
