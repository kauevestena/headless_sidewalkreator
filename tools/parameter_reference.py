"""Build the parameter reference from source defaults without importing GIS libraries.

Only literal values and references to constants in parameters.py are resolved;
application code is never executed. The catalog supplies explanations, not a
second copy of runtime defaults. Missing/stale catalog entries fail the build.
"""

import argparse
import ast
import json
from pathlib import Path


APIS = ("sidewalkreator", "generate_protoblocks")


def _value(node, constants):
    """Resolve literals and the parameter module's simple constant aliases."""
    if isinstance(node, ast.Name):
        return constants[node.id]
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if node.value.id == "params":
            return constants[node.attr]
    return ast.literal_eval(node)


def source_defaults(root):
    """Return each public API's defaults, including optional provider keys."""
    package = Path(root) / "headless_sidewalkreator"
    constants = {}
    for node in ast.parse((package / "parameters.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                constants[target.id] = _value(node.value, constants)
    tree = ast.parse((package / "full_sidewalkreator_algorithm.py").read_text(encoding="utf-8"))
    defaults = {}
    for function in tree.body:
        if not isinstance(function, ast.FunctionDef) or function.name not in APIS:
            continue
        assignments = [
            node for node in function.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Dict)
            and any(isinstance(t, ast.Name) and t.id == "run_params" for t in node.targets)
        ]
        if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Dict):
            raise ValueError(f"Cannot identify runtime defaults for {function.name}")
        mapping = assignments[0].value
        values = {ast.literal_eval(k): _value(v, constants) for k, v in zip(mapping.keys, mapping.values)}
        for node in ast.walk(function):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "run_params" and node.func.attr == "get"):
                key = ast.literal_eval(node.args[0])
                if key not in values:
                    values[key] = _value(node.args[1], constants) if len(node.args) > 1 else None
        defaults[function.name] = values
    if set(defaults) != set(APIS):
        raise ValueError("The public API parameter dictionaries were not found")
    return defaults


def load_reference(root):
    """Check coverage and return the catalog together with resolved defaults."""
    root = Path(root)
    defaults = source_defaults(root)
    catalog = json.loads((root / "docs" / "parameter_catalog.json").read_text(encoding="utf-8"))
    expected = set().union(*(set(values) for values in defaults.values()))
    documented = set(catalog["parameters"])
    if expected != documented:
        raise ValueError(f"Parameter documentation drift: missing={sorted(expected - documented)}, stale={sorted(documented - expected)}")
    for key, entry in catalog["parameters"].items():
        for field in ("group", "type", "units", "values", "description", "used_by"):
            if not entry.get(field) and field != "used_by":
                raise ValueError(f"Missing {field} for parameter {key}")
        if set(entry["used_by"]) - {api for api, values in defaults.items() if key in values}:
            raise ValueError(f"Unsupported effective API for {key}")
        if entry["group"] not in catalog["groups"]:
            raise ValueError(f"Unknown documentation group for {key}")
    return catalog, defaults


def render_reference(root):
    """Render grouped reStructuredText with defaults read from this checkout."""
    catalog, defaults = load_reference(root)
    lines = []
    for group in catalog["groups"]:
        lines += [group, "~" * len(group), ""]
        for key, entry in catalog["parameters"].items():
            if entry["group"] != group:
                continue
            title = f"``{key}``"
            lines += [f".. _param-{key.replace('_', '-')}:", "", title, "^" * len(title), ""]
            lines += [f"**Type:** {entry['type']}. **Units:** {entry['units']}.", ""]
            for api in APIS:
                if key in defaults[api]:
                    value = defaults[api][key]
                    label = "road-width table below" if key == "default_widths" else f"``{value!r}``"
                    lines += [f"* ``{api}()``: default {label}."]
                else:
                    lines += [f"* ``{api}()``: not supported; passing this key raises ``ValueError``."]
            lines += ["", f"**Values and handling:** {entry['values']}", "", entry["description"], ""]
    lines += ["Default road-width table", "~~~~~~~~~~~~~~~~~~~~~~~~", "",
              "These are total road widths in metres, not sidewalk widths. A missing",
              "highway class uses ``fallback_default_width``. Values below 0.5 m",
              "exclude that highway class during data cleaning.", "",
              ".. list-table:: Default widths from parameters.py", "   :header-rows: 1", "",
              "   * - Highway class", "     - Width (m)"]
    for key, value in defaults["sidewalkreator"]["default_widths"].items():
        lines += [f"   * - ``{key}``", f"     - {value:g}"]
    return "\n".join(lines) + "\n"


def write_reference(root):
    """Write the generated include used by Sphinx."""
    destination = Path(root) / "docs" / "_generated" / "parameter_reference.rst"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_reference(root), encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check coverage without writing generated files")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    catalog, defaults = load_reference(root)
    if not args.check:
        print(write_reference(root))
    print(f"Documented {len(catalog['parameters'])} runtime keys across {len(defaults)} APIs")
