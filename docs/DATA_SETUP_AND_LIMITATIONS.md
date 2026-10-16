# Dataset and model setup

## SemEval-2014 Task 4

Kaggle source used by the project:
https://www.kaggle.com/datasets/charitarth/semeval-2014-task-4-aspectbasedsentimentanalysis

The original `archive.zip` contains several file formats. The current code
needs only `Laptop_Train_v2.csv` and `Restaurants_Train_v2.csv`.
Copy those two files to the project-root `SemEval_2014_dataset/` directory;
then run `python Data_preprocessing.py` from the project root. It generates
`Final_SemEval.csv` in the same directory. Do not rename the files.

## DistilBERT model exports

After the author publishes the model archives, extract their **best_model/**
subfolder so these exact paths exist:

- `aspect_extraction/best_model/config.json` (and matching exported model/tokenizer files)
- `aspect_sentiment/best_model/config.json` (and matching exported model/tokenizer files)

Do not create `aspect_extraction/aspect_extraction/best_model/` by accidentally
extracting the containing folder twice. Check the zip internal layout.

The final exports are sufficient for **inference**; full reruns of training
require the SemEval dataset, dependencies, and compute resources. Experimental
checkpoints are not provided in the public repository.

## Raw laptop source data and derived artifacts

The project originally used customer reviews and structured specifications for
30 laptops. **This ZIP contains no complete 30-laptop raw dataset**, so
running `ATE_ABSA_Pipeline.py`, `prepare_review_evidence.py`, and graph
construction from empty placeholders cannot reproduce the populated graph.

A compatible existing Neo4j database can support the deployed FastAPI app
without downloading the training datasets or running DistilBERT. Reconstructing
such a database from scratch requires separately provided validated final
artifact CSVs and proper permissions for the underlying review data.

## Dataset quality and provenance

The official final analysis uses validated corrected ASUS ROG Strix G16 data,
not the superseded duplicate-source intermediate outputs. The validated final
artifacts and correction audit are preserved in a private archival copy.
They are not disguised as uncorrected original scrape results.

## Output folder structure

All conventional folder names are preserved as `.gitkeep` placeholders so the
existing Python relative paths remain applicable; the files are intentionally
absent until created or supplied by the researcher.
