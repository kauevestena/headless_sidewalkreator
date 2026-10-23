"""Keep the public parameter reference aligned with the implementation."""

import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "headless_sidewalkreator").is_dir():
    pytest.skip("Source-derived documentation checks require a source checkout", allow_module_level=True)

spec = importlib.util.spec_from_file_location("parameter_reference", ROOT / "tools" / "parameter_reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


@pytest.fixture
def reference_tree(tmp_path):
    """Copy only the inputs used by the documentation-only AST reader."""
    for path in ("headless_sidewalkreator/parameters.py",
                 "headless_sidewalkreator/full_sidewalkreator_algorithm.py",
                 "docs/parameter_catalog.json"):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    return tmp_path


def test_parameter_reference_covers_defaults_and_applicability():
    """Document every key, resolve aliases, and distinguish public API support."""
    catalog, defaults = reference.load_reference(ROOT)
    assert defaults["sidewalkreator"]["timeout"] == 60
    assert defaults["sidewalkreator"]["protomaps_endpoint_snap_tolerance"] == 0.5
    assert defaults["sidewalkreator"]["provider_kwargs"] == {}
    assert defaults["sidewalkreator"]["default_widths"]["residential"] == 6.0
    assert catalog["parameters"]["cutoff_percent_protoblock"]["used_by"] == ["sidewalkreator"]
    assert "generate_protoblocks" in catalog["parameters"]["save_debug_layers"]["used_by"]
    rendered = reference.render_reference(ROOT)
    assert "not supported; passing this key raises" in rendered
    assert all(f"``{key}``" in rendered for key in defaults["sidewalkreator"])


def test_changed_source_defaults_change_rendered_reference(reference_tree):
    """A changed default must appear without editing a second numeric doc table."""
    source = reference_tree / "headless_sidewalkreator" / "full_sidewalkreator_algorithm.py"
    source.write_text(source.read_text().replace('"timeout": 60,', '"timeout": 91,'))
    assert "default ``91``" in reference.render_reference(reference_tree)


def test_new_runtime_key_requires_documentation(reference_tree):
    """Fail when an implementation change introduces an unexplained override."""
    source = reference_tree / "headless_sidewalkreator" / "full_sidewalkreator_algorithm.py"
    source.write_text(source.read_text().replace('"timeout": 60,', '"timeout": 60, "new_control": True,'))
    with pytest.raises(ValueError, match="missing=.*new_control"):
        reference.load_reference(reference_tree)


def test_stale_catalog_key_fails(reference_tree):
    """Do not retain documentation for removed or invented runtime controls."""
    path = reference_tree / "docs" / "parameter_catalog.json"
    catalog = json.loads(path.read_text())
    catalog["parameters"]["removed_control"] = catalog["parameters"]["timeout"].copy()
    path.write_text(json.dumps(catalog))
    with pytest.raises(ValueError, match="stale=.*removed_control"):
        reference.load_reference(reference_tree)
