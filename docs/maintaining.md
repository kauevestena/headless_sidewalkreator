# Build and publish the documentation

The Sphinx site focuses on the [parameter reference](parameters.rst). Build it
with a small documentation-only environment; the GIS package is not imported
or installed by the documentation build.

```bash
python -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/python tools/parameter_reference.py --check
.venv-docs/bin/python -m sphinx -n -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` locally. On Windows use the environment's
`Scripts/python.exe` in place of `.venv-docs/bin/python`.

## Keep parameters accurate

`docs/parameter_catalog.json` holds explanations, units, types, handling and
which APIs actually use each key. `tools/parameter_reference.py` reads the
runtime dictionaries and module constants using Python's AST; it does not
execute application code. Each build generates the defaults and road-width
table in `docs/_generated/parameter_reference.rst`. Generated files are ignored
by Git. A new or removed runtime key without a matching catalog update fails
both the documentation build and `--check`.

When changing a parameter, update its explanation and effective API list, the
implementation, and behavior tests together. Add actual validation/clamping
details instead of presenting recommendations as enforced constraints. The
catalog is documentation, not a runtime validation schema.

The documentation coverage tests require a source checkout. The isolated
installed-wheel job skips those source-only checks; runtime behavior tests
still run against the wheel, and the source CI and Sphinx workflow check the
documentation inventory.

## GitHub Pages

The `Documentation` workflow builds on pull requests and pushes. A strict build
must pass before a Pages artifact is uploaded. It deploys only on a push or
manual run on the repository's default branch, currently
`feature/headless-prototype`; pull requests only validate the documentation.

In **Settings → Pages → Build and deployment**, select **Source: GitHub
Actions**. Enabling branch-based Pages alone does not enable a custom Sphinx
deployment. The workflow uses the automatic GitHub token and the `github-pages`
environment; no personal token is needed. If an environment branch rule exists,
allow the default branch. After merging, the push triggers the first deployment;
later manual runs use **Actions → Documentation → Run workflow**.

Expected site location:
<https://kauevestena.github.io/headless_sidewalkreator/>.
Use the completed deployment's URL to verify the published reference.
