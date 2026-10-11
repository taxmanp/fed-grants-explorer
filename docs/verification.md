# Accuracy fix: verification record

Checked October 11, 2026. Local branch: `fix/accurate-grant-metrics`.
Source baseline: `85bb5b8` from `taxmanp/fed-grants-explorer`.

## Passed

- Locked dependency installation: `uv sync --locked` (Python 3.12.14; uv 0.12.23).
- **78 offline tests:** 67 client tests and 11 Streamlit AppTest tests. Command: `uv run python -m unittest discover -s tests -v`.
- Compilation: `uv run python -m compileall -q app.py client.py main.py tests`.
- Whitespace validation: `git diff --check`.
- Independent code review of metric/date semantics, pagination, coverage, errors, and cache behavior. Minor directory-retry and numeric-overflow findings were fixed and regression-tested.
- Real Chromium visual/interaction check on a loopback-only local app: both forms, agency results, recipient multi-year chart, separate period/lifetime metrics, partial warning, identifiers/table, tab switching, and refresh. Successful data views used the explicitly labeled **synthetic offline preview**, not live values.
- Real browser check of the production app's failure path: an unavailable agency directory left recipient controls and footer accessible.

### Small live API probes (read-only; executed from the test runner)

All returned HTTP 200 and passed response validation. They check endpoint integration on representative small queries, not every filter or every page.

| Probe | Observed result |
| --- | --- |
| Top-tier agency directory | 111 agency names returned |
| National Endowment for the Arts, FY2024 transaction aggregate | Net obligations **$159,067,429.95** |
| Same agency, award search | Two pages at page size 2; three retained unique awards; cap correctly marked partial; returned cursor forwarded unchanged |
| Recipient search `SOUTH ARTS`, FY2024 transaction aggregate | Net obligations **$2,011,033.00** |
| Same recipient, award search | Two pages at page size 2; three retained unique awards; cap correctly marked partial |

The NEA aggregate was checked around 04:00–04:06 UTC; recipient probes around 04:15 UTC. These are recorded observations, not permanent expected values: USAspending can revise its data.

## Blocked / not fully exercised

- **Live browser-to-API end-to-end success:** the browser-serving desktop runtime reported `Network is unreachable` for the USAspending HTTPS connection. Successful live probes ran separately from the test runner. No network/security settings were changed to work around this restriction. The visual success path was checked using synthetic fixtures.
- A full 1,000-row live query was not downloaded. Pagination and cap edge cases are covered with mocks; live continuation was exercised on two small pages.
- Mobile viewport, Safari, Firefox, screen-reader audit, and production performance/load tests were not run.
- No dedicated linter or static type checker is configured in this repository; neither is represented as passed.
- No remote CI, public branch push, pull request, merge, or deployment was performed. The existing live application was not changed.

## Reproduce safely

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q app.py client.py main.py tests

# Actual app (requests public USAspending data when a search is submitted)
uv run streamlit run app.py

# Isolated visual preview, no live API requests; conspicuous fixture-data banner
uv run streamlit run tests/preview_app.py
```

Review the README's metric definitions before comparing totals. A transaction-period total and a bounded list of lifetime award obligations are intentionally different populations and measures.
