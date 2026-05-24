"""Federal Grants Explorer - USAspending.gov API client."""

import requests
import pandas as pd

BASE_URL = "https://api.usaspending.gov/api/v2"

# Award type codes for grants and cooperative agreements:
# 02 = Block Grant, 03 = Formula Grant, 04 = Project Grant, 05 = Cooperative Agreement
GRANT_AWARD_TYPES = ["02", "03", "04", "05"]


def get_toptier_agencies() -> pd.DataFrame:
    """List all top-tier federal agencies."""
    response = requests.get(
        f"{BASE_URL}/references/toptier_agencies/",
        timeout=30,
    )
    response.raise_for_status()
    return pd.DataFrame(response.json()["results"])


def search_grants(
    agency_name: str,
    fiscal_year: int,
    limit: int = 10,
) -> pd.DataFrame:
    """Top grants awarded by an agency in a given federal fiscal year."""
    payload = {
        "filters": {
            "agencies": [
                {"type": "awarding", "tier": "toptier", "name": agency_name}
            ],
            "time_period": [
                {
                    "start_date": f"{fiscal_year - 1}-10-01",
                    "end_date": f"{fiscal_year}-09-30",
                }
            ],
            "award_type_codes": GRANT_AWARD_TYPES,
        },
        "fields": [
            "Recipient Name",
            "Award Amount",
            "Awarding Sub Agency",
        ],
        "page": 1,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
    }
    response = requests.post(
        f"{BASE_URL}/search/spending_by_award/",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return pd.DataFrame(response.json()["results"])


def main() -> None:
    print("Fetching list of top-tier federal agencies...")
    agencies = get_toptier_agencies()
    print(f"Found {len(agencies)} agencies. First 5:\n")
    print(agencies[["abbreviation", "agency_name"]].head().to_string(index=False))

    print("\nFetching top 10 HHS grants for FY2024...\n")
    grants = search_grants("Department of Health and Human Services", 2024)
    print(grants.to_string(index=False))


if __name__ == "__main__":
    main()