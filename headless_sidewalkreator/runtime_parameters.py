"""Validate runtime option names before acquisition or geometry processing."""

from copy import deepcopy
from difflib import get_close_matches


PROVIDER_OPTIONS = {
    None: {"max_retries", "sleep_fn", "show_progress"},
    "overture": {"release", "base_url", "show_progress"},
    "protomaps": {"url", "zoom", "auto_zoom_tile_budget", "tile_workers",
                  "max_workers", "max_retries", "show_progress", "sleep_fn"},
}


def _check_keys(values, allowed, label):
    for key in values:
        if key not in allowed:
            matches = get_close_matches(str(key), allowed, n=1)
            hint = f" Did you mean '{matches[0]}'?" if matches else ""
            raise ValueError(f"Unknown {label} '{key}'.{hint}")


def merge_parameters(defaults, overrides):
    """Shallow-merge recognized overrides into an independent defaults copy.

    Nested dictionaries replace the corresponding default. Provider option
    names are checked for the selected provider; numeric geometry constraints
    remain with the helpers that use them.
    """
    if overrides is not None and not isinstance(overrides, dict):
        raise TypeError("parameters must be a dictionary or None")
    _check_keys(overrides or {}, defaults, "runtime parameter")
    result = deepcopy(defaults)
    result.update(deepcopy(overrides or {}))
    provider = result["provider"]
    if provider not in (None, "overture", "protomaps"):
        raise ValueError("provider must be None, 'overture', or 'protomaps'")
    options = result["provider_kwargs"]
    if not isinstance(options, dict):
        raise TypeError("provider_kwargs must be a dictionary")
    _check_keys(options, PROVIDER_OPTIONS[provider], "provider option")
    if not isinstance(result["default_widths"], dict):
        raise TypeError("default_widths must be a dictionary")
    return result
