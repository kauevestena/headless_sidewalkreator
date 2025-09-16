# -*- coding: utf-8 -*-
"""Compatibility shim re-exporting package parameters.

This preserves imports like `from parameters import *` by importing the
variables from `headless_sidewalkreator.parameters`.
"""

from headless_sidewalkreator.parameters import *

__all__ = [name for name in globals().keys() if not name.startswith("_")]
