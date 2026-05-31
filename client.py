"""USAspending.gov API client and helper functions."""

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.usaspending.gov/api/v2"

# Award type codes for grants and cooperative agreements:
# 02 = Block Grant, 03 = Formula Grant, 04 = Project Grant, 05 = Cooperative Agreement
GRANT_AWARD_TYPES = ["02", "03", "04", "05"]


def _build_session() -> requests.Session:
    """Build a requests Session with automatic retries for transient API errors.

    Retries up to 3 times with exponential backoff (1s, 2s, 4s) on:
    - Connection failures (network blips, server hangups)
    - 5xx server errors (500, 502, 503, 504)
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# Module-level session: created once when the module is imported,
# reused for every API call. This is how requests is meant to be used
# in any code that makes more than a handful of calls.
_SESSION = _build_session()


def get_toptier_agencies() -> pd.DataFrame:
    """List all top-tier federal agencies."""
    response = _SESSION.get(
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
    response = _SESSION.post(
        f"{BASE_URL}/search/spending_by_award/",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return pd.DataFrame(response.json()["results"])

def search_grants_by_recipient(
    recipient_text: str,
    start_fiscal_year: int,
    end_fiscal_year: int,
    limit: int = 100,
) -> pd.DataFrame:
    """Find grants awarded to a recipient across a range of fiscal years.

    Uses USAspending's `recipient_search_text` filter, which fuzzy-matches
    against recipient name, UEI, and DUNS. Partial names work — passing
    'University of California' will match all UC campuses.
    """
    payload = {
        "filters": {
            "recipient_search_text": [recipient_text],
            "time_period": [
                {
                    "start_date": f"{start_fiscal_year - 1}-10-01",
                    "end_date": f"{end_fiscal_year}-09-30",
                }
            ],
            "award_type_codes": GRANT_AWARD_TYPES,
        },
        "fields": [
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Period of Performance Start Date",
        ],
        "page": 1,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
    }
    response = _SESSION.post(
        f"{BASE_URL}/search/spending_by_award/",
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return pd.DataFrame(response.json()["results"])

def uninvert_recipient_name(name: str) -> str:
    """Detect USAspending's inverted name format and flip it to natural order.

    USAspending stores some names like 'HEALTH CARE SERVICES, CALIFORNIA DEPARTMENT OF'.
    This function turns those into 'CALIFORNIA DEPARTMENT OF HEALTH CARE SERVICES'.
    Names that aren't inverted are returned unchanged.
    """
    if "," not in name:
        return name
    head, _, modifier = name.rpartition(",")
    modifier = modifier.strip()
    if modifier.upper().endswith("OF"):
        return f"{modifier} {head.strip()}"
    return name


def format_grants_for_display(grants: pd.DataFrame) -> str:
    """Format a grants DataFrame as a readable table with currency amounts."""
    display_cols = ["Recipient Name", "Award Amount", "Awarding Sub Agency"]
    formatted = grants[display_cols].copy()
    formatted["Recipient Name"] = formatted["Recipient Name"].apply(
        uninvert_recipient_name
    )
    return formatted.to_string(
        index=False,
        formatters={"Award Amount": "${:,.0f}".format},
    )