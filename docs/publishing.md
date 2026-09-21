# Publishing sidewalkreator

Initial version: **0.1.0**. Distribution: `sidewalkreator`; import:
`headless_sidewalkreator`; command: `sidewalkreator`.
The PyPI JSON API returned 404 for this name on 2026-09-21. This does not reserve
the name or guarantee PyPI will permit registration.

## One-time owner setup

Create GitHub environments `testpypi` and `pypi` in
`kauevestena/headless_sidewalkreator`. Configure required reviewers for `pypi`
where available and restrict deployment branches to the reviewed release branch
(`feature/headless-prototype` currently).

Add a pending trusted publisher on **each** index:

| Field | Value |
| --- | --- |
| PyPI project name | `sidewalkreator` |
| Owner | `kauevestena` |
| Repository | `headless_sidewalkreator` |
| Workflow filename | `publish.yml` |
| Environment on TestPyPI | `testpypi` |
| Environment on PyPI | `pypi` |

PyPI and TestPyPI are separate accounts/configurations. No API token secret is
needed. See [PyPI trusted-publisher setup](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
and [publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Release sequence

1. Merge the reviewed preparation PR. Confirm CI and Package validation pass.
2. Run **Publish Python package** manually on that reviewed branch, selecting
   `testpypi`. It rebuilds the sdist and a wheel from it, checks metadata, and
   tests the installed wheel outside the checkout on Python 3.11–3.13 before upload.
3. Verify the TestPyPI release in a new environment. Download only this package
   from TestPyPI, then resolve dependencies from normal PyPI (avoid mixing indexes):

   ```bash
   python -m venv /tmp/sidewalkreator-test
   /tmp/sidewalkreator-test/bin/python -m pip download --no-deps --only-binary=:all: --index-url https://test.pypi.org/simple/ sidewalkreator==0.1.0 -d /tmp/sidewalkreator-download
   /tmp/sidewalkreator-test/bin/python -m pip install /tmp/sidewalkreator-download/sidewalkreator-0.1.0-py3-none-any.whl
   /tmp/sidewalkreator-test/bin/python -m pip check
   /tmp/sidewalkreator-test/bin/sidewalkreator --help
   ```

4. After approving publication, run the workflow on the **same commit** with
   target `pypi`. This rebuilds and validates distributions again; it does not
   promote byte-identical TestPyPI artifacts. Check the workflow's commit SHA.
5. Verify `pip install sidewalkreator==0.1.0` in a fresh environment, then create
   the corresponding `v0.1.0` tag/release for that commit.

Published files cannot be replaced. For a changed release, update the version
in `pyproject.toml`, review/test again, and use a new version number.

## Local validation

```bash
python -m pip install build twine
python -m build
python -m twine check --strict dist/*
```

The Package validation workflow additionally installs the wheel into a clean
venv, checks dependencies, exercises both CLI entry points and nested provider
imports, generates an offline synthetic street grid, and runs the full suite
with no source package present. Editable installs alone cannot validate release
packaging.

Packaging readiness does not certify Từ Liêm production acceptance: GUI geometry
comparison and manual network QA remain necessary. Road attributes lost during
line splitting are a separate known algorithmic limitation.
