# README and GitHub publication checklist — Stage 4

This checklist separates the finished **source/documentation draft** from details that require input or validation before switching an existing private GitHub repository to public visibility.

## Completed in the Stage 4 package

- [x] Replace Stage 3 placeholder root README with a code-grounded project overview.
- [x] Document Balanced, Custom Preferences, and Guided Two-Stage Refinement.
- [x] Describe offline ATE/ABSA, v3 ontology, adjusted scoring, review evidence and Neo4j serving.
- [x] Preserve correct `pipeline_output/` (raw predictions) versus `pipeline_output_v3/` (ontology output) semantics.
- [x] Add SemEval Kaggle download and expected original CSV names.
- [x] Specify the exact model extraction directories and planned Google Drive ZIP names.
- [x] Explain backend/frontend setup and the limitation of an empty graph in a fresh clone.
- [x] Bring backend/frontend sub-READMEs up to date with implemented modes and routes.

## Still needed from the project owner before public release

- [ ] Upload `aspect_extraction.zip` and `aspect_sentiment.zip` (each contains only `best_model/`) to Google Drive. Supply working public/anyone-with-link viewer URLs and, optionally, SHA-256 checksums.
- [x] Supply the public Render **frontend** URL: https://laptop-recommendation-frontend.onrender.com. [ ] Independently confirm the deployed site loads and can perform recommendations with the production Neo4j data. (The frontend build API URL is the backend endpoint, **not** the public frontend URL.)
- [ ] Choose **2–4 sanitized, representative application screenshots** for display under the project introduction. Avoid screenshots showing private credentials or unredistributable review content.
- [ ] Verify any final ATE/ABSA evaluation metrics directly against recorded training/evaluation outputs and decide whether to add a results table to the README. No unverified model accuracy values have been inserted.
- [ ] Confirm official thesis title and optional supervisor/university attribution, if desired.
- [ ] Decide on a **LICENSE** file for any public release; do not assume the code is automatically open source.
- [ ] Audit the full GitHub commit history and all branches for secrets, model weights, scraped reviews, and redistribution-restricted files. `.gitignore` does not remove existing tracked/history files.
- [ ] Test environment installation and Vite production build in a fresh clone; these steps were not comprehensively validated in the Stage 4 environment.
- [ ] Determine what the university requires to evaluate the final work if the source repository lacks a self-contained data import snapshot.

## Deployment and source-control policy

- Keep the original `Program/` directory unchanged.
- Keep the Stage 1 corrected data and correction audit **private** and available for research verification.
- Stage source/docs changes on a separate branch, inspect the full staged path list and diff, then merge when satisfied.
- Publishing the corrected final methodology and outputs without historical working files is reasonable, but do not make false claims about provenance or validation.
- Do not add a false or broken screenshot/demo/model link. Replace the explicitly marked placeholders after the author provides the assets.
