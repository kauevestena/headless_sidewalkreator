"""Sphinx configuration; documentation builds need no installed GIS stack."""

from pathlib import Path
import runpy
import tomllib

ROOT = Path(__file__).resolve().parents[1]
metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
project = "Sidewalkreator"
author = metadata["authors"][0]["name"]
release = metadata["version"] + " (development)"
extensions = ["myst_parser"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build", "_generated", "requirements.txt"]
html_theme = "furo"
html_title = f"Sidewalkreator {release}"
html_baseurl = "https://kauevestena.github.io/headless_sidewalkreator/"
html_theme_options = {
    "source_repository": "https://github.com/kauevestena/headless_sidewalkreator/",
    "source_branch": "feature/headless-prototype",
    "source_directory": "docs/",
}
nitpicky = True

# Generate source-derived defaults; a missing explanation fails the build.
runpy.run_path(str(ROOT / "tools" / "parameter_reference.py"))["write_reference"](ROOT)


def setup(app):
    """Record inputs so incremental builds also refresh source-derived defaults."""
    def record_dependencies(app, docname, source):
        if docname == "parameters":
            app.env.note_dependency(str(ROOT / "headless_sidewalkreator" / "parameters.py"))
            app.env.note_dependency(str(ROOT / "headless_sidewalkreator" / "full_sidewalkreator_algorithm.py"))
            app.env.note_dependency(str(ROOT / "docs" / "parameter_catalog.json"))
    app.connect("source-read", record_dependencies)
