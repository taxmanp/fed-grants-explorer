# Federal Grants Explorer

A Python tool for exploring federal grant data from [USAspending.gov](https://www.usaspending.gov/), the official source for U.S. government spending.

## Why this project

I spent several years at the U.S. Department of Health and Human Services negotiating indirect cost rates and managing federal grants. The data on USAspending is uniquely valuable for understanding where federal dollars actually go — but the API isn't friendly to non-developers. This project turns that data into something you can analyze with a few lines of Python, and over time will grow into an interactive dashboard for grants officers, program managers, and nonprofit finance teams.

## Example output

Running `uv run python main.py` produces:

```
Fetching list of top-tier federal agencies...
Found 111 agencies. First 5:

 abbreviation                                       agency_name
         AAHC  400 Years of African-American History Commission
         USAB                                       Access Board
         ACUS             Administrative Conference of the U.S.
         ACHP         Advisory Council on Historic Preservation
        USADF                     African Development Foundation

Fetching top 10 HHS grants for FY2024...
[ The top grants are Medicaid block grants from CMS to California's
  Department of Health Care Services and New York State Department
  of Health — each in the tens of billions. ]
```

## Tech stack

- **Python 3.12** with [`uv`](https://docs.astral.sh/uv/) for dependency management
- [`requests`](https://docs.python-requests.org/) for HTTP calls to the USAspending API
- [`pandas`](https://pandas.pydata.org/) for tabular data handling

## Getting started

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Git.

```bash
git clone https://github.com/taxmanp/fed-grants-explorer.git
cd fed-grants-explorer
uv sync
uv run python main.py
```

## Roadmap

- [ ] Format dollar amounts as currency (drop the scientific notation)
- [ ] Add CFDA / Assistance Listing breakdowns
- [ ] Recipient lookup by UEI
- [ ] State + congressional district geography views
- [ ] Streamlit dashboard for interactive exploration

## Background reading

- [USAspending API documentation](https://api.usaspending.gov/)
- [2 CFR Part 200](https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200) — Uniform Guidance for federal grants
- [DATA Act of 2014](https://en.wikipedia.org/wiki/Federal_Funding_Accountability_and_Transparency_Act) — the law that makes this data public

## About the author

Built by Paul Rodriguez — finance and analytics professional with a background in federal grants management, Big Four tax, and international finance consulting. [LinkedIn](https://www.linkedin.com/in/paulrodriguez5/) · [GitHub](https://github.com/taxmanp)