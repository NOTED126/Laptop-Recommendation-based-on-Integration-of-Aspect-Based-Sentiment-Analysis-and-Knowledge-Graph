# Canonical aspect categorization and normalization

The offline ATE model extracts aspect phrases from customer reviews.
`canonical_aspect_mapping.py` categorizes and normalizes those phrases using
predefined canonical aspect categories, exact aliases, regular expressions,
and context-dependent rules. Unknown phrases remain unmapped; irrelevant
phrases are rejected. Experience aspects and specification mentions remain
separate throughout aggregation and scoring.

## Public Python interface

```python
from canonical_aspect_mapping import classify_aspect, canonical_aspect_table

decision = classify_aspect("battery life", "The battery life is excellent.")
assert decision.mapping_status == "mapped"
assert decision.canonical_aspect == "BATTERY_LIFE"
categories = canonical_aspect_table()
```

`AspectDecision.mapping_status` and the raw-prediction CSV column
`mapping_status` use the same three values: `mapped`, `unmapped`, and `rejected`.
`mapping_method` records the matched rule type, while `mapping_reason` provides
an explanation. The updated code and CSVs must be used together; external
notebooks or scripts that read the previous schema need their column references
updated to `mapping_status`.

## Commands (from the repository root)

```bash
python ATE_ABSA_Pipeline.py --reviews-dir reviews --output-dir pipeline_output
python reaggregate_canonical_aspects_v3.py --raw pipeline_output/raw_aspect_predictions.csv --output-dir pipeline_output_v3
python recommendation_scoring.py
```

The reaggregation command uses saved predictions without rerunning either
trained model. The first command requires the trained models and source review
files described in the environment and data setup guides.

For exploratory saved predictions:

```bash
python test_canonical_aspects_on_exploratory.py --raw exploratory_test_output/exploratory_raw_aspect_predictions.csv --output-dir canonical_aspects_test_output
```

Its default output directory is `canonical_aspects_test_output/`. It writes
`exploratory_canonical_aspect_predictions.csv` and
`canonical_aspect_categories.csv`, alongside the other exploratory reports.
The main pipeline writes `pipeline_output/canonical_aspect_categories.csv`;
v3 reaggregation writes `pipeline_output_v3/canonical_aspect_categories_v3.csv`.
These category tables contain `canonical_aspect`, `canonical_label`,
`aspect_type`, and `description`.

## Preservation and validation

This terminology migration retains the mapping rules, category identifiers,
sentiment labels, corrected source identities, counts, scoring formulas, graph
schema, saved graph exports, evidence records, and generated summaries.
Mapping explanations use the revised terminology. Historical recovery manifests
retain the hashes recorded during the original repair; those hashes describe
the files at that time. The accompanying change report records the hashes of
the migrated files.

```bash
python -m pytest -q
python tools/validate_final_data.py
cd frontend
node test_display_all.mjs
node test_summary_coverage.mjs
node test_supervisor_comparison.mjs
node test_supervisor_four_refinements.mjs
npm ci
npm run build
```

The tests exercise mapping decisions, the renamed CLI outputs, existing backend
recommendation behavior, summaries, and recovery safeguards. Live Neo4j imports
and model inference require separately supplied services or model files.
