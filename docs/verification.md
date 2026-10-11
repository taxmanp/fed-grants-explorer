# Accuracy fix: verification record

## Production release: October 11, 2026

The approved accuracy fix was merged in [PR #1](https://github.com/taxmanp/fed-grants-explorer/pull/1) at commit `d0107515057d5c64c14fba303bf75b616215d258` and verified on the existing [public app](https://fed-grants-explorer-paul.streamlit.app/) around 04:48–04:50 UTC. The app’s GitHub toolbar points to `taxmanp/fed-grants-explorer/blob/main/app.py`. GitHub main was fetched and its complete file tree matched the reviewed package exactly (`f5521a37c46fd9fd018d9e083eff4b9c23fb491f`).

### Release checks passed

- Locked dependency installation, all 78 offline tests, compilation, and whitespace validation were rerun before publication.
- The updated live UI rendered both search forms, the corrected metric definitions, and a default FY2026 with FY2027 available.
- **Live agency search:** National Endowment for the Arts, FY2024, displayed **$159,067,430** period net obligations. A separate fresh API query returned **$159,067,429.95**, matching after display rounding. At a 100-award cap the lifetime sum was **$156,644,539** with an explicit partial-result warning.
- **Live pagination:** raising the same agency search cap to 250 loaded **250 unique awards across 3 pages**, with the cap warning and a **$206,085,940** lifetime sum. The fiscal-period total stayed unchanged.
- **Live recipient search:** `SOUTH ARTS`, FY2023–FY2024, displayed **$8,216,333** period obligations, **5** award records, and **$16,468,078** lifetime obligations. The fiscal-year chart showed FY2023 and FY2024; a fresh API query confirmed annual amounts of **$6,205,300** and **$2,011,033**, respectively. USAspending reported no further award pages for that query.
- Recipient refresh advanced both source-retrieval timestamps. Tab switching preserved the submitted agency and recipient results. Editing the award cap did not reload the query until form submission.
- GitHub confirmed PR #1 merged and main at the release commit. The exact commit had **no check runs, commit-status entries, or Actions runs**; the repository has no configured CI workflow or required status checks. Local tests are therefore not represented as a remote CI pass.

These are bounded smoke tests of the real production app using live USAspending data, not synthetic fixtures. Displayed values are observations and may change as USAspending revises its records. A platform-reported deployed commit hash was not exposed in the public app; the release was verified through the source-branch link, exact remote tree, and changed production behavior. The 1,000-row cap, mobile/Safari/Firefox behavior, accessibility, and load testing were not re-exercised in production.

## Pre-release verification record

Checked October 11, 2026. Local branch: `fix/accurate-grant-metrics`.
Source baseline: `85bb5b8` from `taxmanp/fed-grants-explorer`.

### Passed before release

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

### Pre-release limitations

- **Local live browser-to-API end-to-end success:** the pre-release browser-serving runtime reported `Network is unreachable` for the USAspending HTTPS connection. Successful live probes ran separately from the test runner. No network/security settings were changed to work around this restriction. The visual success path was checked using synthetic fixtures.
- A full 1,000-row live query was not downloaded. Pagination and cap edge cases are covered with mocks; live continuation was exercised on two small pages.
- Mobile viewport, Safari, Firefox, screen-reader audit, and production performance/load tests were not run.
- No dedicated linter or static type checker is configured in this repository; neither is represented as passed.
- At this pre-release stage, no remote CI, public branch push, pull request, merge, or deployment had been performed. The later approved production release and its verification are recorded above.

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
