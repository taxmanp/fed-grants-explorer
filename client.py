"""USAspending client: period transaction totals and bounded award exploration.

Award Amount is cumulative lifetime obligation, not spending in a selected FY.
See README.md for endpoint semantics, scope, and operational limits.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
import time

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.usaspending.gov/api/v2"
GRANT_AWARD_TYPES = ["02", "03", "04", "05"]
MIN_FISCAL_YEAR = 2008
MAX_RESULTS = 1000
PAGE_SIZE = 100
MAX_PAGES = 10
AWARD_FIELDS = [
    "Award ID", "generated_internal_id", "Recipient Name", "Recipient UEI",
    "Award Amount", "Awarding Agency", "Awarding Sub Agency", "Start Date",
]


class APIDataError(ValueError):
    """A response cannot safely support the displayed metric."""


@dataclass
class AwardSearchResult:
    awards: pd.DataFrame
    complete: bool
    reason: str
    pages_loaded: int
    fetched_at: str
    messages: tuple[str, ...] = ()


@dataclass
class PeriodObligations:
    by_fiscal_year: pd.DataFrame
    fetched_at: str
    messages: tuple[str, ...] = ()

    @property
    def total(self) -> float:
        return _sum(self.by_fiscal_year["Net obligations"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current_fiscal_year(today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    return today.year + (today.month >= 10)


def fiscal_year_dates(start_year: int, end_year: int) -> dict:
    if (type(start_year) is not int or type(end_year) is not int
            or not MIN_FISCAL_YEAR <= start_year <= end_year <= current_fiscal_year()):
        raise ValueError("Fiscal years must be ordered and between 2008 and the current federal FY.")
    return {"start_date": f"{start_year - 1}-10-01", "end_date": f"{end_year}-09-30"}


def grant_filters(start_year: int, end_year: int, *, agency_name: str | None = None,
                  recipient_text: str | None = None) -> dict:
    filters = {"time_period": [fiscal_year_dates(start_year, end_year)],
               "award_type_codes": GRANT_AWARD_TYPES.copy()}
    if agency_name is not None:
        if not isinstance(agency_name, str) or not agency_name.strip():
            raise ValueError("Choose an agency.")
        filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency_name.strip()}]
    if recipient_text is not None:
        if not isinstance(recipient_text, str) or not recipient_text.strip():
            raise ValueError("Enter a recipient name or UEI.")
        filters["recipient_search_text"] = [recipient_text.strip()]
    return filters


def _build_session() -> requests.Session:
    session = requests.Session()
    # These POSTs are read-only searches. Retry only transient failures.
    retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504],
                  allowed_methods=["GET", "POST"], raise_on_status=False,
                  respect_retry_after_header=False)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


_SESSION = _build_session()


def _json(response: requests.Response) -> dict:
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError as exc:
        raise APIDataError("USAspending returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise APIDataError("USAspending returned an unexpected response structure.")
    return data


def _messages(data: dict) -> tuple[str, ...]:
    messages = data.get("messages", [])
    if not isinstance(messages, list) or any(not isinstance(m, str) for m in messages):
        raise APIDataError("USAspending returned invalid response messages.")
    return tuple(messages)


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise APIDataError(f"USAspending returned a missing or invalid {field}.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise APIDataError(f"USAspending returned an out-of-range {field}.") from exc
    if not math.isfinite(number):
        raise APIDataError(f"USAspending returned a missing or invalid {field}.")
    return number


def _sum(values) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise APIDataError("USAspending amounts exceed the supported numeric range.") from exc
    if not math.isfinite(result):
        raise APIDataError("USAspending amounts exceed the supported numeric range.")
    return result


def get_toptier_agencies() -> pd.DataFrame:
    data = _json(_SESSION.get(f"{BASE_URL}/references/toptier_agencies/", timeout=(5, 30)))
    rows = data.get("results")
    if not isinstance(rows, list) or any(not isinstance(r, dict) or
            not isinstance(r.get("agency_name"), str) or not r["agency_name"].strip() for r in rows):
        raise APIDataError("USAspending returned an invalid agency list.")
    return pd.DataFrame(rows, columns=["agency_name"])


def _award_page(data: dict, page: int, limit: int) -> tuple[list[dict], dict]:
    rows, metadata = data.get("results"), data.get("page_metadata")
    if (data.get("spending_level") != "awards" or not isinstance(rows, list)
            or len(rows) > limit or not isinstance(metadata, dict)
            or type(metadata.get("page")) is not int or metadata["page"] != page
            or type(metadata.get("hasNext")) is not bool):
        raise APIDataError("USAspending returned invalid award pagination metadata.")
    clean = []
    for row in rows:
        if not isinstance(row, dict) or any(field not in row for field in AWARD_FIELDS):
            raise APIDataError("USAspending omitted a requested award field.")
        if not isinstance(row["generated_internal_id"], str) or not row["generated_internal_id"]:
            raise APIDataError("USAspending omitted a unique award identifier.")
        record = {field: row[field] for field in AWARD_FIELDS}
        record["Award Amount"] = _number(row["Award Amount"], "award amount")
        for field in set(AWARD_FIELDS) - {"Award Amount"}:
            if record[field] is not None and not isinstance(record[field], str):
                raise APIDataError(f"USAspending returned an invalid {field}.")
        if record["Start Date"] is not None:
            try:
                date.fromisoformat(record["Start Date"])
            except ValueError as exc:
                raise APIDataError("USAspending returned an invalid award start date.") from exc
        clean.append(record)
    return clean, metadata


def search_awards(filters: dict, max_results: int = 100, *, page_size: int = PAGE_SIZE,
                  max_pages: int = MAX_PAGES, time_budget: float = 90) -> AwardSearchResult:
    """Load at most 1,000 awards, retaining coverage on errors or limits.

    The deadline is checked between requests; an in-flight request/retry can
    exceed it. Cursor values are forwarded unchanged when supplied by the API.
    Complete means only that the API reported no next page.
    """
    if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
        raise ValueError("max_results must be between 1 and 1,000.")
    if type(page_size) is not int or not 1 <= page_size <= PAGE_SIZE:
        raise ValueError("page_size must be between 1 and 100.")
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("max_pages must be between 1 and 10.")
    if (isinstance(time_budget, bool) or not isinstance(time_budget, (int, float))
            or not math.isfinite(time_budget) or time_budget <= 0):
        raise ValueError("time_budget must be positive and finite.")
    payload = {"filters": deepcopy(filters), "fields": AWARD_FIELDS.copy(),
               "sort": "Award Amount", "order": "desc", "spending_level": "awards"}
    rows, seen, messages, seen_cursors = [], set(), [], set()
    pages_loaded, complete, reason = 0, False, "Result limit reached; more awards may match."
    started = time.monotonic()
    for page in range(1, max_pages + 1):
        if time.monotonic() - started >= time_budget:
            reason = "Time budget reached; the award list is partial."
            break
        # Keep the page width stable even without cursor support. Changing the
        # limit for the last page would change its offset and repeat/skip rows.
        payload.update(page=page, limit=min(page_size, max_results))
        try:
            data = _json(_SESSION.post(f"{BASE_URL}/search/spending_by_award/",
                                       json=deepcopy(payload), timeout=(5, 30)))
            batch, metadata = _award_page(data, page, payload["limit"])
            _sum(r["Award Amount"] for r in rows + batch)
            new_messages = _messages(data)
        except (requests.RequestException, APIDataError):
            if not pages_loaded:
                raise
            reason = f"Page {page} could not be loaded or validated; the award list is partial."
            break
        pages_loaded += 1
        messages.extend(m for m in new_messages if m not in messages)
        overlap = False
        truncated = len(batch) > max_results - len(rows)
        for row in batch:
            award_id = row["generated_internal_id"]
            if award_id in seen:
                overlap = True
                continue
            seen.add(award_id)
            if len(rows) < max_results:
                rows.append(row)
        if overlap or (not batch and metadata["hasNext"]):
            reason = "Pagination was inconsistent; duplicates were removed and coverage is unverified."
            break
        if not metadata["hasNext"] and not truncated:
            complete, reason = True, "USAspending reported no more matching award pages."
            break
        if len(rows) >= max_results:
            reason = "Result limit reached; more awards may match."
            break
        # Never derive the monetary cursor from dollars: the API uses cents.
        for key in ("last_record_unique_id", "last_record_sort_value"):
            payload.pop(key, None)
        if all(metadata.get(k) is not None for k in ("last_record_unique_id", "last_record_sort_value")):
            cursor = (metadata["last_record_unique_id"], metadata["last_record_sort_value"])
            if (type(cursor[0]) is not int or not isinstance(cursor[1], (str, int, float))
                    or isinstance(cursor[1], bool) or cursor in seen_cursors):
                reason = "Pagination cursor was invalid or repeated; coverage is unverified."
                break
            seen_cursors.add(cursor)
            payload.update({k: metadata[k] for k in ("last_record_unique_id", "last_record_sort_value")})
        reason = "Page budget reached; the award list is partial."
    return AwardSearchResult(pd.DataFrame(rows, columns=AWARD_FIELDS), complete, reason,
                             pages_loaded, _now(), tuple(messages))


def get_period_obligations(filters: dict) -> PeriodObligations:
    """Aggregate net transaction obligations independently of award rows loaded."""
    transaction_filters = deepcopy(filters)
    periods = transaction_filters["time_period"]
    for period in periods:
        period["date_type"] = "action_date"
    data = _json(_SESSION.post(f"{BASE_URL}/search/spending_over_time/",
                              json={"filters": transaction_filters, "group": "fiscal_year",
                                    "spending_level": "transactions"}, timeout=(5, 30)))
    if (data.get("spending_level") != "transactions" or data.get("group") != "fiscal_year"
            or not isinstance(data.get("results"), list)):
        raise APIDataError("USAspending returned an invalid transaction aggregate.")
    start_fy = current_fiscal_year(date.fromisoformat(periods[0]["start_date"]))
    end_fy = current_fiscal_year(date.fromisoformat(periods[-1]["end_date"]))
    rows, seen = [], set()
    for item in data["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("time_period"), dict):
            raise APIDataError("USAspending returned an invalid aggregate period.")
        year = item["time_period"].get("fiscal_year")
        if (not isinstance(year, (str, int)) or isinstance(year, bool)
                or not str(year).isascii() or not str(year).isdigit()
                or not start_fy <= int(year) <= end_fy or int(year) in seen):
            raise APIDataError("USAspending returned an unexpected or duplicate fiscal year.")
        seen.add(int(year))
        rows.append({"Fiscal year": int(year), "Net obligations": _number(item.get("aggregated_amount"), "net obligations")})
    amounts = {row["Fiscal year"]: row["Net obligations"] for row in rows}
    frame = pd.DataFrame([{"Fiscal year": year, "Net obligations": amounts.get(year, 0.0)}
                          for year in range(start_fy, end_fy + 1)])
    _sum(frame["Net obligations"])
    return PeriodObligations(frame, _now(), _messages(data))


def search_grants(agency_name: str, fiscal_year: int, limit: int = 100) -> AwardSearchResult:
    return search_awards(grant_filters(fiscal_year, fiscal_year, agency_name=agency_name), limit)


def search_grants_by_recipient(recipient_text: str, start_fiscal_year: int,
                                end_fiscal_year: int, limit: int = 100) -> AwardSearchResult:
    return search_awards(grant_filters(start_fiscal_year, end_fiscal_year, recipient_text=recipient_text), limit)


def uninvert_recipient_name(name: str | None) -> str:
    """Display-only heuristic; source names and identifiers remain in the data."""
    if not isinstance(name, str) or not name:
        return "Unknown recipient"
    head, separator, modifier = name.rpartition(",")
    if separator and modifier.strip().upper().endswith(" OF"):
        return f"{modifier.strip()} {head.strip()}"
    return name


def format_grants_for_display(grants: pd.DataFrame) -> str:
    formatted = grants[["Award ID", "Recipient Name", "Award Amount", "Awarding Sub Agency"]].copy()
    formatted["Recipient Name"] = formatted["Recipient Name"].apply(uninvert_recipient_name)
    formatted = formatted.rename(columns={"Award Amount": "Lifetime obligations"})
    return formatted.to_string(index=False, formatters={"Lifetime obligations": "${:,.0f}".format})
