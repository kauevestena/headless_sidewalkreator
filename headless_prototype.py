"""Compatibility shim.

Older tests and scripts import `run_headless` from the module `headless_prototype`.
This file re-exports the function from the package `headless_sidewalkreator`.
"""

from headless_sidewalkreator import run_headless

__all__ = ["run_headless"]
