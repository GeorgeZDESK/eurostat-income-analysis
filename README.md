# Eurostat Income Analysis

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://eurostat-income-analysis-thucepf9uar5ybkg9nxeyg.streamlit.app/)

Python analysis of equivalised disposable income in Greece and Europe: trends, age groups, inflation, housing costs and urbanisation.

## Data

Eurostat: [ilc_di03](https://ec.europa.eu/eurostat/databrowser/view/ilc_di03/default/table?lang=en), [prc_hicp_ainr](https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_ainr/default/table?lang=en), [ilc_lvho07a](https://ec.europa.eu/eurostat/databrowser/view/ilc_lvho07a/default/table?lang=en), [ilc_di17](https://ec.europa.eu/eurostat/databrowser/view/ilc_di17/default/table?lang=en). Published group statistics; raw CSV snapshots remain unchanged.

## Streamlit explorer

Explore live Eurostat data for countries, age groups, housing and urbanisation, plus HICP-adjusted income changes for Greece.

For a first installation, run these commands from the repository root:

```bash
conda env create -f environment.yml
conda activate eurostat-income-app
python -m streamlit run streamlit_app.py
```

Apply sidebar filters with **Load data**. Responses are cached for up to one hour.


## Reproduce

Recorded environment: Python 3.13.17 and VS Code. See [setup and execution](docs/REPRODUCIBILITY.md). Outputs: `data/processed/` and `reports/figures/`.

[EUR/PPS comparison](notebooks/04_eur_pps_comparison.ipynb) uses live Eurostat API data from survey year 2003 onwards, with a fixed country set across years. In the recorded run, only 2018 has complete coverage of all 37 countries.

## Verified example

Greece's median income increased **9.29% after inflation** between income years 2019 and 2023.

The author is responsible for transformations and interpretation; Eurostat bears no responsibility.

