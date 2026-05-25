# Federal Grants Explorer

> 🚀 **Live demo:** [fed-grants-explorer-paul.streamlit.app](https://fed-grants-explorer-paul.streamlit.app)

An interactive dashboard for exploring federal grant data from [USAspending.gov](https://www.usaspending.gov/), the official source for U.S. government spending.

![Dashboard screenshot](docs/dashboard.png)

## Why this project

I spent several years at the U.S. Department of Health and Human Services negotiating indirect cost rates and managing federal grants. The data on USAspending is uniquely valuable for understanding where federal dollars actually go — but the API isn't friendly to non-developers. This project turns that data into an interactive dashboard that grants officers, program managers, and nonprofit finance teams can actually use.

## What it does

Pick any federal agency and fiscal year. The dashboard fetches the top grants from USAspending.gov in real-time and shows:

- **Total awarded, unique recipients, and unique sub-agencies** as quick-glance metrics
- **A horizontal bar chart** of total grant dollars by sub-agency, revealing how the parent agency's grant budget actually breaks down
- **A sortable table** of the largest individual grants, with recipient names cleaned up from USAspending's quirky inverted format

The dashboard runs entirely on free public APIs — no authentication, no API keys, no costs.

## Tech stack

- **Python 3.12** with [`uv`](https://docs.astral.sh/uv/) for dependency management
- [`requests`](https://docs.python-requests.org/) for HTTP calls to the USAspending API
- [`pandas`](https://pandas.pydata.org/) for tabular data handling
- [`streamlit`](https://streamlit.io/) for the interactive dashboard
- [`plotly`](https://plotly.com/python/) for charts
- Deployed on [Streamlit Community Cloud](https://streamlit.io/cloud)

## Getting started

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Git.

```bash
git clone https://github.com/taxmanp/fed-grants-explorer.git
cd fed-grants-explorer
uv sync

# Run the command-line version:
uv run python main.py

# Or launch the dashboard locally:
uv run streamlit run app.py
```

## Roadmap

- [x] Fetch federal grant data from USAspending API
- [x] Clean up USAspending's inverted recipient name format
- [x] Format dollar amounts as readable currency
- [x] Sub-agency breakdown using pandas groupby
- [x] Interactive Streamlit dashboard with sidebar filters
- [x] Deploy to Streamlit Community Cloud
- [ ] State + congressional district geography views
- [ ] Recipient lookup by UEI (Unique Entity Identifier)
- [ ] CFDA / Assistance Listing program breakdowns
- [ ] Time-series view across multiple fiscal years
- [ ] Unit tests for the data-cleaning functions

## Background reading

- [USAspending API documentation](https://api.usaspending.gov/)
- [2 CFR Part 200](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200) — Uniform Guidance for federal grants
- [DATA Act of 2014](https://en.wikipedia.org/wiki/Federal_Funding_Accountability_and_Transparency_Act) — the law that makes this data public

## About the author

Built by Paul Rodriguez — finance and analytics professional with a background in federal grants management, Big Four tax, and international finance consulting. [LinkedIn](https://www.linkedin.com/in/paulrodriguez5/) · [GitHub](https://github.com/taxmanp)