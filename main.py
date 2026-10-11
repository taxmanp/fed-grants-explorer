"""Command-line example. Run with: uv run python main.py"""

import requests

from client import APIDataError, format_grants_for_display, get_period_obligations, grant_filters, search_awards


def main() -> None:
    filters = grant_filters(2024, 2024, agency_name="Department of Health and Human Services")
    print("HHS / FY2024 (2023-10-01 through 2024-09-30)\n")
    try:
        total = get_period_obligations(filters)
        print(f"Period net transaction obligations: ${total.total:,.0f}")
    except (requests.RequestException, APIDataError):
        print("Period net obligations: unavailable (not replaced with a sample sum).")
    try:
        result = search_awards(filters, max_results=100)
    except (requests.RequestException, APIDataError):
        print("Award details could not be loaded or validated.")
        return
    print(f"\n{len(result.awards)} awards loaded. {result.reason}")
    print("Award search uses activity-span overlap; amounts below are lifetime obligations, not FY spending.")
    if not result.awards.empty:
        print("\nLargest 10 among loaded awards:\n")
        print(format_grants_for_display(result.awards.head(10)))
    print(f"\nAward data retrieved {result.fetched_at}.")


if __name__ == "__main__":
    main()
