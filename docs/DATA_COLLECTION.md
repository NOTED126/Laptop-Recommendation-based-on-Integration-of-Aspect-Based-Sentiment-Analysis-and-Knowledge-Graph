# Data collection: Best Buy laptop reviews and specifications

This document explains the **original data-collection implementation** included in this undergraduate laptop recommendation thesis. It is based on the checked-in `review_scraping.py` and `specification_scraping.py` files. Both scripts use Selenium with Firefox and GeckoDriver, and save individual CSV files for the products listed in their source-code configurations.

> **Historical reproducibility:** The research used 30 laptop products and 6,000 collected review records. The full validated research datasets are **not** distributed in this source-only repository. URLs, prices, reviews, page structure, and available review counts may have changed since the original collection. Running these scripts today is not guaranteed to reproduce the thesis data or succeed without maintenance.
>
> **Website access:** Check the site's current terms, access restrictions, and relevant permissions before collecting data. The scripts do not authorize bypassing access controls. Avoid publishing collected third-party customer review text without appropriate redistribution rights.

## 1. Prerequisites

- Python 3.11 (the author's historical environment used Python 3.11.0).
- Mozilla Firefox installed locally.
- A **compatible GeckoDriver** executable for your operating system and Firefox installation.
- Python packages `selenium` and `pandas`.
- Valid Best Buy product URLs and access to the site's relevant product/review pages.

From the **project root** on Windows PowerShell, in an existing Python environment:

```powershell
python -m pip install selenium pandas
```

The larger research environment is described in [`ENVIRONMENT_SETUP.md`](ENVIRONMENT_SETUP.md), but model-training or GPU dependencies are not required just to run these two scrapers.

Both scraper constructors currently contain Windows-specific defaults, which other users **must adjust**:

```python
firefox_binary: str = r'C:\Program Files\Mozilla Firefox\firefox.exe'
geckodriver_path: str = r'C:\Users\USER\Downloads\geckodriver-v0.36.0-win64\geckodriver.exe'
```

The first value identifies the Firefox executable; the second is the path to a separately obtained GeckoDriver executable. Edit the defaults in `BestBuyReviewScraper.__init__` and `LaptopSpecScraper.__init__` to point to your local installation. These two scripts do **not** currently expose command-line arguments for driver paths or product lists. Their source-code configurations control what they scrape.

## 2. Collect customer reviews — `review_scraping.py`

### Target products

The `PRODUCT_DICT` object, defined near the bottom of `review_scraping.py`, is keyed by a product name. Each product entry provides:

| Field | Purpose |
|---|---|
| Dictionary key | Name used for the resulting review CSV filename. |
| `brand` | Manufacturer included in each output row. |
| `model` | Model description included in each output row. |
| `URL` | Best Buy product/review URL used to construct the paginated review URL. |
| `URL_pages` | Maximum number of review pages attempted for this product; defaults to **11** if omitted. |

The scraper converts configured URLs to review-page URLs through `modify_link(url)`. This helper assumes historical Best Buy URL patterns, so verify it against current URLs and page behavior before use.

`BestBuyReviewScraper.__init__` also defines:

```python
output_folder: str = "./reviews/"
max_reviews_per_product: int = 200
```

The script attempts to collect **up to 200 reviews per configured laptop**, subject to review availability, page limits and successful page parsing. It does not guarantee that exactly 200 will be collected.

### Run

From the repository root:

```powershell
python review_scraping.py
```

The script's `main()` function constructs `BestBuyReviewScraper()` and calls `scrape_all(PRODUCT_DICT)`, which iterates over **every configured product**. If you intend to test a smaller subset, adjust a *copy* of the configuration before running; do not unintentionally launch the full historical collection job.

### Output structure and fields

Files are written individually to `reviews/`:

```text
reviews/
└── <product_name>_reviews.csv
```

The filename is sanitized using `format_safe_filename()` (spaces and hyphens become underscores). Each CSV has these exact columns, constructed by the script:

| Column | Meaning |
|---|---|
| `Review Count` | Sequential counter within the product's collected reviews. |
| `Brand` | Manufacturer from the product configuration. |
| `Model` | Model from the product configuration. |
| `Product` | Configured product-name key. |
| `Date` | Date attribute when available; may be missing. |
| `Review` | Extracted customer review text. |

The code uses CSS selectors for review containers, review text, and date metadata. It waits for page elements and includes delays between requests. Page markup changes can cause a timeout, missing text, or incomplete CSV output. The original script should not be assumed to remain compatible with the current Best Buy site.

## 3. Collect specifications — `specification_scraping.py`

### Target products

The `LAPTOPS_TO_SCRAPE` variable is a list of dictionaries containing:

| Field | Purpose |
|---|---|
| `brand` | Laptop manufacturer. |
| `model` | Laptop model description. |
| `name` | Product name used in the output row. |
| `URL` | Best Buy product page URL. |

`LaptopSpecScraper` visits each configured product page, extracts the displayed price and primary image URL when available, opens the **Specifications** section/drawer, and searches the page for keys listed in its `desired_specs` attribute. The default output folder is `./specifications/`.

The desired fields span display, CPU, RAM, storage, GPU, operating system, connectivity, cooling, battery, camera, dimensions, and weight. Values may be blank when a product page does not expose a particular field or the page cannot be parsed successfully.

### Run

From the repository root:

```powershell
python specification_scraping.py
```

Its `__main__` block uses `with LaptopSpecScraper() as scraper:` and invokes `scraper.scrape_all(LAPTOPS_TO_SCRAPE)`, processing **the entire configured list**. The context manager closes the Firefox driver when the run finishes or exits.

### Output structure and fields

Files are written individually to `specifications/`:

```text
specifications/
└── <brand>_<model>_specifications.csv
```

The standardized CSV starts with these exact columns:

```text
Brand, Model, Product Name, Product URL, Price ($), Image URL
```

They are followed by the predefined `desired_specs` columns, including examples such as:

- `Screen Size`, `Screen Resolution`, `Touch Screen`, `Refresh Rate`
- `Processor Brand`, `Processor Model`, `Processor Model Number`
- `System Memory (RAM)`, `Total Storage Capacity`
- `Graphics`, `GPU Brand`, `Operating System`
- `Wireless Connectivity`, `USB Ports`, `Battery Life (up to)`

The price parser `clean_price_to_float()` converts the displayed currency-formatted text into a number when possible; it is a capture of the listed price at collection time, **not a live price guarantee**.

## 4. Common checks and limitations

Before considering any collected CSV suitable for analysis:

1. Confirm that the product URLs and website-specific CSS/XPath selectors still work and that access is permitted.
2. Confirm the correct laptop identity for **each** output file; a valid filename alone does not establish that the reviews belong to that product.
3. Inspect the number of rows, missing review text, duplicated reviews, and key fields such as `Brand`, `Model`, and `Product`.
4. Check specification headers and missing values before using files in downstream graph preparation.
5. Keep raw exports and validation records private unless sharing is authorized by the data provider's terms.

**Website Structure and Selector Compatibility:** Both scraping scripts rely on predefined CSS selectors and XPath expressions to locate specific elements on Best Buy's website, including customer reviews, product prices, images, and specification details. Since the website's HTML structure may change over time, users should inspect the current page structure using browser developer tools and update the corresponding selectors in `review_scraping.py` and `specification_scraping.py` when necessary. Users should also verify that the updated selectors extract the intended information accurately and comply with the website's applicable access requirements.

**Known historical correction:** During the thesis, incorrect duplicate ASUS ROG Flow Z13 review data were discovered under the ASUS ROG Strix G16 record. The final research dataset was corrected and validated. That corrected source data and the provenance/audit materials are retained in a separate private archive; they are not reproduced by a fresh scraper run.

## 5. Where these files enter the offline research pipeline

```text
review_scraping.py  -> reviews/*.csv
                      -> ATE_ABSA_Pipeline.py (offline inference)
                      -> ontology v3 reaggregation / evidence preparation

specification_scraping.py -> specifications/*.csv
                           -> prepare_kg_data.py (graph-ready records)

precomputed aspect scores + graph-ready specifications + review evidence
                           -> Neo4j / AuraDB -> FastAPI -> React frontend
```

The trained ATE/ABSA models and full raw review/specification datasets are **not** included in this source-only repository. The deployed website uses precomputed Neo4j data; it does not scrape Best Buy or rerun DistilBERT for each user search.

For related setup constraints, see [`DATA_SETUP_AND_LIMITATIONS.md`](DATA_SETUP_AND_LIMITATIONS.md) and [`ENVIRONMENT_SETUP.md`](ENVIRONMENT_SETUP.md).
