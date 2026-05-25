"""Command-line entry point for the Federal Grants Explorer.

Run with: uv run python main.py
"""

from client import search_grants, format_grants_for_display


def main() -> None:
    print("Fetching HHS grants for FY2024 (top 100 by dollar amount)...\n")
    grants = search_grants(
        "Department of Health and Human Services", 2024, limit=100
    )

    print("Top 10 individual grants:\n")
    print(format_grants_for_display(grants.head(10)))

    print("\n\nTotal awarded by HHS sub-agency (across the top 100 grants):\n")
    summary = (
        grants.groupby("Awarding Sub Agency")["Award Amount"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"Award Amount": "Total Awarded"})
    )
    print(summary.to_string(
        index=False,
        formatters={"Total Awarded": "${:,.0f}".format},
    ))


if __name__ == "__main__":
    main()