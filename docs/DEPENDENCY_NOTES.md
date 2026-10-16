# Dependency selection audit — Stage 3

Source: user-supplied `Program_python_packages(2).txt` (2026-10-16) and Python 3.11.0, cross-checked against imports in the actual Stage 2 project. The original `pip freeze` is **not** included in the GitHub source-only package; it is retained by the author in their private research records.

## Direct offline dependencies

| Installed package | Version | Why included |
|---|---|---|
| torch | 2.11.0+cu130 | Model training/inference; install separately by platform |
| transformers | 5.19.0 | Hugging Face DistilBERT models and Trainer |
| pandas | 3.0.6 | Dataset and CSV processing |
| numpy | 2.4.6 | Numerical processing/evaluation |
| scikit-learn | 1.9.1 | Training splits and metrics |
| matplotlib | 3.11.2 | `Data_preprocessing.py` sentiment charts |
| selenium | 4.51.0 | Original web-scraping scripts |
| neo4j | 6.3.1 | Graph preparation/import/query scripts |
| python-dotenv | 1.2.3 | Local graph-connection environment loading |
| tabulate | 0.10.0 | Training/evaluation tables |
| pytest | 9.1.1 | Regression tests |

`requirements-ml.txt` pins only the **non-PyTorch direct dependencies** to match the author's exported versions; use the official PyTorch installation selector before it. Installing `requirements-ml.txt` does **not** install all packages from `pip freeze` by design. Ancillary packages such as `torchaudio`, `torchvision`, Hugging Face transitive libraries, and `accelerate` were not detected as direct imports; `accelerate` in particular did not appear in the freeze even though Trainer may need it on some installations. This is a **reason to run a clean environment integration test** before claiming complete environment reproducibility.

## Other dependency files

- `backend/requirements.txt`: existing FastAPI app requirements; preserved **unchanged**, uses supported version ranges.
- `frontend/package.json` and `frontend/package-lock.json`: npm dependencies; preserved **unchanged**.
- `backend/.python-version`: `3.11` for the backend host, whereas the author's local interpreter was Python `3.11.0`.

These files intentionally do not impose the author's local GPU-specific PyTorch build on the Render backend, which does **not** perform live DistilBERT inference.

## Verification status

- Direct import/version audit: completed against source code and freeze.
- Frontend and unit regression tests: see `docs/STAGE3_VERIFICATION.md`.
- Clean `pip install`, CUDA setup, actual training, model loading, and live Neo4j: **not** performed in this release environment. Preserve the author's `Program/` installation as the known working reference.
