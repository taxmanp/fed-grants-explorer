"""Offline behavioral regression tests for the USAspending client.

Run: .venv/bin/python -m unittest discover -s tests -v
All requests are replaced by mocks; no live API is used.
"""

from copy import deepcopy
from datetime import date, datetime, timezone
import math
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

import client


def award(identifier="award-1", amount=123.45, **changes):
    row = {
        "Award ID": f"FAIN-{identifier}",
        "generated_internal_id": identifier,
        "Recipient Name": "EXAMPLE RECIPIENT",
        "Recipient UEI": "EXAMPLE12345",
        "Award Amount": amount,
        "Awarding Agency": "Example Agency",
        "Awarding Sub Agency": "Example Sub Agency",
        "Start Date": "2023-10-01",
    }
    row.update(changes)
    return row


def award_page(rows, *, page=1, has_next=False, **metadata):
    return {
        "spending_level": "awards",
        "results": rows,
        "page_metadata": {"page": page, "hasNext": has_next, **metadata},
    }


def aggregate(rows=()):
    return {"spending_level": "transactions", "group": "fiscal_year", "results": list(rows)}


def period(year=2024, amount=100.0):
    return {"time_period": {"fiscal_year": year}, "aggregated_amount": amount}


def response(data=None, *, http_error=None, json_error=None):
    result = Mock(spec=requests.Response)
    result.raise_for_status.side_effect = http_error
    result.json.side_effect = json_error
    result.json.return_value = data
    return result


class OfflineClientTestCase(unittest.TestCase):
    def setUp(self):
        self.session_patch = patch.object(client, "_SESSION", autospec=True)
        self.session = self.session_patch.start()
        self.addCleanup(self.session_patch.stop)
        # An unexpected request fails immediately rather than reaching the internet.
        self.session.post.side_effect = AssertionError("Unexpected POST")
        self.session.get.side_effect = AssertionError("Unexpected GET")
        self.filters = client.grant_filters(2024, 2025, agency_name="Example Agency")

    def post_responses(self, *responses):
        self.session.post.side_effect = list(responses)

    def search(self, *responses, **kwargs):
        self.post_responses(*responses)
        return client.search_awards(self.filters, **kwargs)

    def get_aggregate(self, data):
        self.post_responses(response(data))
        return client.get_period_obligations(self.filters)


class FiscalYearAndFilterTests(OfflineClientTestCase):
    def test_fiscal_year_rolls_over_on_october_first(self):
        self.assertEqual(client.current_fiscal_year(date(2024, 9, 30)), 2024)
        self.assertEqual(client.current_fiscal_year(date(2024, 10, 1)), 2025)
        self.assertEqual(client.current_fiscal_year(date(2025, 1, 1)), 2025)

    def test_current_fiscal_year_uses_utc_today(self):
        with patch.object(client, "datetime") as clock:
            clock.now.return_value = datetime(2024, 10, 1, tzinfo=timezone.utc)
            self.assertEqual(client.current_fiscal_year(), 2025)
            clock.now.assert_called_once_with(timezone.utc)

    def test_fiscal_year_date_range_is_inclusive(self):
        with patch.object(client, "current_fiscal_year", return_value=2025):
            self.assertEqual(client.fiscal_year_dates(2024, 2025), {
                "start_date": "2023-10-01", "end_date": "2025-09-30",
            })
            self.assertEqual(client.fiscal_year_dates(2008, 2008), {
                "start_date": "2007-10-01", "end_date": "2008-09-30",
            })

    def test_fiscal_year_rejects_future_reversed_and_invalid_types(self):
        cases = [(2007, 2025), (2025, 2024), (2024, 2026), (True, 2025),
                 (2024, False), (2024.0, 2025), (2024, "2025"), (None, 2025)]
        with patch.object(client, "current_fiscal_year", return_value=2025):
            for start, end in cases:
                with self.subTest(start=start, end=end):
                    with self.assertRaises(ValueError):
                        client.fiscal_year_dates(start, end)

    def test_filters_keep_grant_codes_and_trim_text(self):
        actual = client.grant_filters(2024, 2025, agency_name="  Example Agency\n",
                                      recipient_text="  EXAMPLE12345  ")
        self.assertEqual(actual, {
            "time_period": [{"start_date": "2023-10-01", "end_date": "2025-09-30"}],
            "award_type_codes": ["02", "03", "04", "05"],
            "agencies": [{"type": "awarding", "tier": "toptier", "name": "Example Agency"}],
            "recipient_search_text": ["EXAMPLE12345"],
        })

    def test_optional_filters_can_be_omitted(self):
        filters = client.grant_filters(2024, 2024)
        self.assertNotIn("agencies", filters)
        self.assertNotIn("recipient_search_text", filters)
        filters["award_type_codes"].append("99")
        self.assertEqual(client.grant_filters(2024, 2024)["award_type_codes"], ["02", "03", "04", "05"])

    def test_filters_reject_blank_text(self):
        for field in ("agency_name", "recipient_text"):
            for value in ("", "  ", "\n\t"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        client.grant_filters(2024, 2024, **{field: value})

    def test_filters_reject_non_string_text_cleanly(self):
        for field in ("agency_name", "recipient_text"):
            for value in (123, True, ["Example"], {"name": "Example"}, b"Example"):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        client.grant_filters(2024, 2024, **{field: value})


class AwardPaginationTests(OfflineClientTestCase):
    def test_one_page_complete_result_has_timestamp_and_expected_fields(self):
        result = self.search(response(award_page([award()])))
        self.assertTrue(result.complete)
        self.assertEqual(result.pages_loaded, 1)
        self.assertEqual(result.awards.columns.tolist(), client.AWARD_FIELDS)
        self.assertEqual(result.awards["Award Amount"].tolist(), [123.45])
        self.assertIsNotNone(datetime.fromisoformat(result.fetched_at).tzinfo)
        url = self.session.post.call_args.args[0]
        payload = self.session.post.call_args.kwargs["json"]
        self.assertEqual(url, f"{client.BASE_URL}/search/spending_by_award/")
        self.assertEqual(payload["spending_level"], "awards")
        self.assertEqual(payload["sort"], "Award Amount")
        self.assertEqual(payload["order"], "desc")
        self.assertEqual(payload["fields"], client.AWARD_FIELDS)
        self.assertEqual(self.session.post.call_args.kwargs["timeout"], (5, 30))

    def test_cursor_pair_is_forwarded_unchanged_not_derived_from_dollars(self):
        result = self.search(
            response(award_page([award("one", 123.45)], has_next=True,
                                last_record_unique_id=7654321, last_record_sort_value="12345.000")),
            response(award_page([award("two", 50)], page=2)), page_size=1,
        )
        payload = self.session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(payload["last_record_unique_id"], 7654321)
        self.assertIs(type(payload["last_record_unique_id"]), int)
        self.assertEqual(payload["last_record_sort_value"], "12345.000")
        self.assertIs(type(payload["last_record_sort_value"]), str)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.awards), 2)

    def test_zero_cursor_value_is_preserved(self):
        self.search(response(award_page([award("one", 0)], has_next=True,
                                        last_record_unique_id=0, last_record_sort_value=0)),
                    response(award_page([award("two", -1)], page=2)), page_size=1)
        payload = self.session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(payload["last_record_unique_id"], 0)
        self.assertEqual(payload["last_record_sort_value"], 0)

    def test_page_number_pagination_works_without_cursor(self):
        result = self.search(response(award_page([award("one")], has_next=True)),
                             response(award_page([award("two")], page=2)), page_size=1)
        second = self.session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(second["page"], 2)
        self.assertNotIn("last_record_unique_id", second)
        self.assertNotIn("last_record_sort_value", second)
        self.assertTrue(result.complete)

    def test_partial_cursor_pair_is_not_forwarded(self):
        for metadata in ({"last_record_unique_id": 17}, {"last_record_sort_value": 12345},
                         {"last_record_unique_id": 17, "last_record_sort_value": None}):
            with self.subTest(metadata=metadata):
                self.session.post.reset_mock()
                self.search(response(award_page([award("one")], has_next=True, **metadata)),
                            response(award_page([award("two")], page=2)), page_size=1)
                second = self.session.post.call_args_list[1].kwargs["json"]
                self.assertNotIn("last_record_unique_id", second)
                self.assertNotIn("last_record_sort_value", second)

    def test_stale_cursor_is_cleared_if_next_response_has_no_pair(self):
        result = self.search(
            response(award_page([award("one")], has_next=True,
                                last_record_unique_id=17, last_record_sort_value=12345)),
            response(award_page([award("two")], page=2, has_next=True)),
            response(award_page([award("three")], page=3)), page_size=1,
        )
        third = self.session.post.call_args_list[2].kwargs["json"]
        self.assertNotIn("last_record_unique_id", third)
        self.assertNotIn("last_record_sort_value", third)
        self.assertTrue(result.complete)

    def test_short_page_with_has_next_does_not_imply_completion(self):
        result = self.search(response(award_page([award("one")], has_next=True)),
                             response(award_page([award("two")], page=2)), page_size=10)
        self.assertTrue(result.complete)
        self.assertEqual(result.pages_loaded, 2)
        self.assertEqual(len(result.awards), 2)

    def test_result_limit_keeps_page_width_stable_and_marks_partial(self):
        result = self.search(response(award_page([award("one"), award("two")], has_next=True)),
                             response(award_page([award("three")], page=2, has_next=True)),
                             page_size=2, max_results=3)
        self.assertEqual([call.kwargs["json"]["limit"] for call in self.session.post.call_args_list], [2, 2])
        self.assertFalse(result.complete)
        self.assertIn("Result limit", result.reason)
        self.assertEqual(len(result.awards), 3)
        self.assertEqual(result.pages_loaded, 2)

    def test_local_truncation_never_claims_complete_even_if_api_has_no_next_page(self):
        for has_next in (True, False):
            with self.subTest(has_next=has_next):
                self.session.post.reset_mock()
                result = self.search(
                    response(award_page([award("one"), award("two")], has_next=True)),
                    response(award_page([award("three"), award("four")], page=2, has_next=has_next)),
                    page_size=2, max_results=3,
                )
                self.assertEqual([call.kwargs["json"]["limit"] for call in self.session.post.call_args_list], [2, 2])
                self.assertEqual(result.awards["generated_internal_id"].tolist(), ["one", "two", "three"])
                self.assertFalse(result.complete)
                self.assertIn("Result limit", result.reason)

    def test_repeated_cursor_stops_even_when_page_rows_are_distinct(self):
        cursor = {"last_record_unique_id": 42, "last_record_sort_value": "12345"}
        result = self.search(
            response(award_page([award("one")], has_next=True, **cursor)),
            response(award_page([award("two")], page=2, has_next=True, **cursor)),
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.awards["generated_internal_id"].tolist(), ["one", "two"])
        self.assertEqual(result.pages_loaded, 2)
        self.assertEqual(self.session.post.call_count, 2)
        self.assertIn("cursor", result.reason.lower())
        self.assertIn("unverified", result.reason.lower())

    def test_invalid_cursor_types_do_not_get_forwarded(self):
        for cursor in (
            {"last_record_unique_id": True, "last_record_sort_value": "12345"},
            {"last_record_unique_id": [], "last_record_sort_value": "12345"},
            {"last_record_unique_id": 42, "last_record_sort_value": []},
            {"last_record_unique_id": 42, "last_record_sort_value": True},
        ):
            with self.subTest(cursor=cursor):
                self.session.post.reset_mock()
                result = self.search(response(award_page([award()], has_next=True, **cursor)))
                self.assertFalse(result.complete)
                self.assertEqual(result.pages_loaded, 1)
                self.assertEqual(self.session.post.call_count, 1)
                self.assertIn("cursor", result.reason.lower())

    def test_exact_limit_can_be_complete_when_api_reports_no_next_page(self):
        result = self.search(response(award_page([award()])), max_results=1)
        self.assertTrue(result.complete)
        self.assertEqual(len(result.awards), 1)

    def test_page_budget_marks_result_partial(self):
        result = self.search(response(award_page([award()], has_next=True)), max_pages=1)
        self.assertFalse(result.complete)
        self.assertIn("Page budget", result.reason)
        self.assertEqual(result.pages_loaded, 1)

    def test_time_budget_preserves_loaded_rows(self):
        with patch.object(client.time, "monotonic", side_effect=[0, 0, 91]):
            result = self.search(response(award_page([award()], has_next=True)), time_budget=90)
        self.assertFalse(result.complete)
        self.assertIn("Time budget", result.reason)
        self.assertEqual(len(result.awards), 1)
        self.assertEqual(result.pages_loaded, 1)
        self.assertEqual(self.session.post.call_count, 1)

    def test_duplicate_in_page_is_removed_and_not_claimed_complete(self):
        result = self.search(response(award_page([award("one"), award("one")])))
        self.assertFalse(result.complete)
        self.assertEqual(len(result.awards), 1)
        self.assertIn("inconsistent", result.reason)

    def test_repeated_page_stops_and_preserves_unique_awards(self):
        result = self.search(response(award_page([award("one"), award("two")], has_next=True)),
                             response(award_page([award("one"), award("two")], page=2, has_next=True)))
        self.assertFalse(result.complete)
        self.assertEqual(result.awards["generated_internal_id"].tolist(), ["one", "two"])
        self.assertEqual(result.pages_loaded, 2)
        self.assertEqual(self.session.post.call_count, 2)

    def test_overlap_keeps_new_rows_but_coverage_stays_unverified(self):
        result = self.search(response(award_page([award("one")], has_next=True)),
                             response(award_page([award("one"), award("two")], page=2)))
        self.assertFalse(result.complete)
        self.assertEqual(result.awards["generated_internal_id"].tolist(), ["one", "two"])
        self.assertIn("inconsistent", result.reason)

    def test_empty_page_with_has_next_is_incomplete(self):
        result = self.search(response(award_page([], has_next=True)))
        self.assertFalse(result.complete)
        self.assertTrue(result.awards.empty)
        self.assertEqual(result.pages_loaded, 1)
        self.assertIn("inconsistent", result.reason)

    def test_empty_page_without_has_next_is_complete_with_columns(self):
        result = self.search(response(award_page([])))
        self.assertTrue(result.complete)
        self.assertTrue(result.awards.empty)
        self.assertEqual(result.awards.columns.tolist(), client.AWARD_FIELDS)

    def test_response_messages_are_deduplicated_in_order(self):
        first = award_page([award("one")], has_next=True)
        first["messages"] = ["First warning", "Shared warning"]
        second = award_page([award("two")], page=2)
        second["messages"] = ["Shared warning", "Last warning"]
        result = self.search(response(first), response(second))
        self.assertEqual(result.messages, ("First warning", "Shared warning", "Last warning"))

    def test_search_does_not_mutate_filters(self):
        original = deepcopy(self.filters)
        self.search(response(award_page([award()])))
        self.assertEqual(self.filters, original)
        submitted = self.session.post.call_args.kwargs["json"]["filters"]
        submitted["time_period"][0]["start_date"] = "1900-01-01"
        self.assertEqual(self.filters, original)


class AwardValidationAndFailureTests(OfflineClientTestCase):
    def test_invalid_limits_fail_before_requests(self):
        for field, values in {
            "max_results": (0, -1, 1001, True, "100", 1.5),
            "page_size": (0, -1, 101, True, "10", 1.5),
            "max_pages": (0, -1, 11, True, "2", 1.5),
            "time_budget": (0, -1, math.inf, -math.inf, math.nan),
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        client.search_awards(self.filters, **{field: value})
        self.session.post.assert_not_called()

    def test_time_budget_rejects_non_numeric_and_boolean_values_cleanly(self):
        for value in (None, "90", True, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    client.search_awards(self.filters, time_budget=value)
        self.session.post.assert_not_called()

    def test_first_page_http_failure_raises(self):
        with self.assertRaises(requests.HTTPError):
            self.search(response(http_error=requests.HTTPError("503 service unavailable")))

    def test_first_page_transport_failure_raises(self):
        with self.assertRaises(requests.Timeout):
            self.search(requests.Timeout("timed out"))

    def test_first_page_schema_failure_raises(self):
        malformed = [None, [], {}, {"results": [], "page_metadata": {"page": 1, "hasNext": False}}]
        for data in malformed:
            with self.subTest(data=data):
                with self.assertRaises(client.APIDataError):
                    self.search(response(data))

    def test_first_page_invalid_json_raises_data_error(self):
        with self.assertRaises(client.APIDataError):
            self.search(response(json_error=ValueError("invalid JSON")))

    def test_midstream_http_or_schema_failure_returns_valid_partial_rows(self):
        failures = [response(http_error=requests.HTTPError("503")), requests.Timeout("timeout"),
                    response({}), response(json_error=ValueError("invalid JSON"))]
        for failed in failures:
            with self.subTest(failure=failed):
                result = self.search(response(award_page([award("one")], has_next=True)), failed)
                self.assertFalse(result.complete)
                self.assertEqual(result.pages_loaded, 1)
                self.assertEqual(result.awards["generated_internal_id"].tolist(), ["one"])
                self.assertIn("Page 2", result.reason)

    def test_malformed_pagination_metadata_is_rejected(self):
        cases = []
        for key, values in {"page": (None, 2, "1", True), "hasNext": (None, 0, 1, "false")}.items():
            for value in values:
                data = award_page([award()])
                data["page_metadata"][key] = value
                cases.append(data)
        for key, value in (("spending_level", "transactions"), ("results", {}), ("page_metadata", [])):
            data = award_page([award()])
            data[key] = value
            cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(client.APIDataError):
                    self.search(response(data))

    def test_oversized_page_is_rejected_instead_of_silently_truncated(self):
        with self.assertRaises(client.APIDataError):
            self.search(response(award_page([award("one"), award("two")])), max_results=1)

    def test_every_requested_award_field_is_required(self):
        for field in client.AWARD_FIELDS:
            row = award()
            del row[field]
            with self.subTest(field=field):
                with self.assertRaises(client.APIDataError):
                    self.search(response(award_page([row])))

    def test_missing_non_numeric_boolean_and_nonfinite_amounts_are_rejected(self):
        for amount in (None, "123.45", True, math.nan, math.inf, -math.inf, []):
            with self.subTest(amount=amount):
                with self.assertRaises(client.APIDataError):
                    self.search(response(award_page([award(amount=amount)])))

    def test_overflow_amount_and_sum_raise_data_error(self):
        for rows in ([award(amount=10**400)], [award("one", 1e308), award("two", 1e308)]):
            with self.subTest(rows=rows):
                with self.assertRaises(client.APIDataError):
                    self.search(response(award_page(rows)))

    def test_zero_and_negative_award_amounts_are_valid(self):
        result = self.search(response(award_page([award("zero", 0), award("negative", -123.45)])))
        self.assertTrue(result.complete)
        self.assertEqual(result.awards["Award Amount"].tolist(), [0.0, -123.45])

    def test_null_names_and_dates_are_retained_without_invented_values(self):
        row = award(**{"Recipient Name": None, "Recipient UEI": None, "Awarding Agency": None,
                       "Awarding Sub Agency": None, "Start Date": None, "Award ID": None})
        result = self.search(response(award_page([row])))
        self.assertTrue(result.complete)
        for field in ("Recipient Name", "Recipient UEI", "Awarding Agency", "Awarding Sub Agency", "Start Date", "Award ID"):
            self.assertIsNone(result.awards.iloc[0][field])

    def test_invalid_text_fields_dates_and_identifiers_are_rejected(self):
        cases = [{"generated_internal_id": value} for value in (None, "", 123)]
        cases += [{"Recipient Name": 123}, {"Recipient UEI": []}, {"Awarding Agency": False},
                  {"Award ID": 123}, {"Start Date": "2024-02-30"}, {"Start Date": "yesterday"},
                  {"Start Date": ""}, {"Start Date": 20241001}]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(client.APIDataError):
                    self.search(response(award_page([award(**changes)])))

    def test_non_object_award_rows_are_rejected(self):
        for row in (None, [], "award"):
            with self.subTest(row=row):
                with self.assertRaises(client.APIDataError):
                    self.search(response(award_page([row])))

    def test_malformed_response_messages_are_rejected(self):
        for messages in (None, "warning", {}, [1], ["warning", None]):
            data = award_page([award()])
            data["messages"] = messages
            with self.subTest(messages=messages):
                with self.assertRaises(client.APIDataError):
                    self.search(response(data))


class PeriodObligationTests(OfflineClientTestCase):
    def test_aggregate_uses_transaction_endpoint_action_dates_and_all_filters(self):
        self.filters["recipient_search_text"] = ["EXAMPLE12345"]
        original = deepcopy(self.filters)
        result = self.get_aggregate(aggregate([period(2024, 123.45), period("2025", 10)]))
        self.session.post.assert_called_once()
        call = self.session.post.call_args
        self.assertEqual(call.args[0], f"{client.BASE_URL}/search/spending_over_time/")
        submitted = call.kwargs["json"]
        expected = deepcopy(original)
        expected["time_period"][0]["date_type"] = "action_date"
        self.assertEqual(submitted, {"filters": expected, "group": "fiscal_year", "spending_level": "transactions"})
        self.assertEqual(self.filters, original)
        self.assertEqual(result.by_fiscal_year.to_dict("records"), [
            {"Fiscal year": 2024, "Net obligations": 123.45},
            {"Fiscal year": 2025, "Net obligations": 10.0},
        ])
        self.assertAlmostEqual(result.total, 133.45)
        self.assertIsNotNone(datetime.fromisoformat(result.fetched_at).tzinfo)

    def test_period_total_is_independent_of_capped_lifetime_award_rows(self):
        self.post_responses(response(award_page([award(amount=999999)], has_next=True)),
                            response(aggregate([period(2024, 12), period(2025, -2)])))
        awards = client.search_awards(self.filters, max_results=1)
        obligations = client.get_period_obligations(self.filters)
        self.assertFalse(awards.complete)
        self.assertEqual(awards.awards["Award Amount"].sum(), 999999)
        self.assertEqual(obligations.total, 10)
        self.assertNotIn("limit", self.session.post.call_args.kwargs["json"])
        self.assertNotIn("page", self.session.post.call_args.kwargs["json"])

    def test_missing_years_are_filled_with_zero_and_results_sorted(self):
        self.filters = client.grant_filters(2023, 2025)
        result = self.get_aggregate(aggregate([period("2025", 50), period(2023, 30)]))
        self.assertEqual(result.by_fiscal_year["Fiscal year"].tolist(), [2023, 2024, 2025])
        self.assertEqual(result.by_fiscal_year["Net obligations"].tolist(), [30.0, 0.0, 50.0])
        self.assertEqual(result.total, 80)

    def test_empty_aggregate_is_zero_for_each_requested_fiscal_year(self):
        result = self.get_aggregate(aggregate())
        self.assertEqual(result.by_fiscal_year["Fiscal year"].tolist(), [2024, 2025])
        self.assertEqual(result.by_fiscal_year["Net obligations"].tolist(), [0.0, 0.0])
        self.assertEqual(result.total, 0.0)

    def test_aggregate_overflow_is_rejected_before_display(self):
        for rows in ([period(2024, 10**400)], [period(2024, 1e308), period(2025, 1e308)]):
            with self.subTest(rows=rows):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(aggregate(rows))

    def test_zero_and_negative_net_obligations_are_valid(self):
        result = self.get_aggregate(aggregate([period(2024, 0), period(2025, -50.25)]))
        self.assertEqual(result.by_fiscal_year["Net obligations"].tolist(), [0.0, -50.25])
        self.assertEqual(result.total, -50.25)

    def test_aggregate_out_of_range_fiscal_years_are_rejected(self):
        for year in (2023, "2026"):
            with self.subTest(year=year):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(aggregate([period(year)]))

    def test_duplicate_fiscal_years_are_rejected_including_string_int_aliases(self):
        for years in ((2024, 2024), (2024, "2024")):
            with self.subTest(years=years):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(aggregate([period(years[0]), period(years[1])]))

    def test_malformed_aggregate_top_level_is_rejected(self):
        cases = [None, [], {}, {"spending_level": "transactions", "group": "fiscal_year", "results": {}}]
        for key, value in (("spending_level", "awards"), ("group", "month")):
            data = aggregate([period()])
            data[key] = value
            cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(data)

    def test_malformed_aggregate_rows_and_fiscal_years_are_rejected(self):
        cases = [None, [], "row", {}, {"time_period": None}, {"time_period": []}]
        cases += [period(value) for value in (None, True, 2024.0, "FY2024", "", "2024.5", "²")]
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(aggregate([row]))

    def test_missing_non_numeric_and_nonfinite_aggregate_amounts_are_rejected(self):
        cases = [period(amount=value) for value in (None, "100", True, math.nan, math.inf, -math.inf, [])]
        cases.append({"time_period": {"fiscal_year": 2024}})
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(client.APIDataError):
                    self.get_aggregate(aggregate([row]))

    def test_aggregate_messages_are_returned_and_validated(self):
        data = aggregate([period()])
        data["messages"] = ["Reporting caveat"]
        self.assertEqual(self.get_aggregate(data).messages, ("Reporting caveat",))
        data["messages"] = [None]
        with self.assertRaises(client.APIDataError):
            self.get_aggregate(data)

    def test_aggregate_http_and_json_failures_raise(self):
        for failed, error_type in ((response(http_error=requests.HTTPError("503")), requests.HTTPError),
                                   (response(json_error=ValueError("invalid JSON")), client.APIDataError)):
            with self.subTest(error_type=error_type):
                self.post_responses(failed)
                with self.assertRaises(error_type):
                    client.get_period_obligations(self.filters)


class AgencyAndDisplayTests(OfflineClientTestCase):
    def test_agency_list_uses_reference_endpoint_and_returns_names(self):
        self.session.get.side_effect = [response({"results": [
            {"agency_name": "Agency A", "toptier_code": "001"}, {"agency_name": "Agency B"},
        ]})]
        result = client.get_toptier_agencies()
        self.assertEqual(result.columns.tolist(), ["agency_name"])
        self.assertEqual(result["agency_name"].tolist(), ["Agency A", "Agency B"])
        self.session.get.assert_called_once_with(f"{client.BASE_URL}/references/toptier_agencies/", timeout=(5, 30))

    def test_empty_agency_list_keeps_expected_column(self):
        self.session.get.side_effect = [response({"results": []})]
        result = client.get_toptier_agencies()
        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), ["agency_name"])

    def test_malformed_agency_data_is_rejected(self):
        cases = [None, [], {}, {"results": None}, {"results": {}}, {"results": [None]},
                 {"results": ["Agency A"]}, {"results": [{}]}]
        cases += [{"results": [{"agency_name": value}]} for value in (None, 123, "", " \n\t")]
        for data in cases:
            with self.subTest(data=data):
                self.session.get.side_effect = [response(data)]
                with self.assertRaises(client.APIDataError):
                    client.get_toptier_agencies()

    def test_agency_http_failure_is_not_converted_to_empty_list(self):
        self.session.get.side_effect = [response(http_error=requests.HTTPError("503"))]
        with self.assertRaises(requests.HTTPError):
            client.get_toptier_agencies()

    def test_uninvert_only_recognizes_of_modifier(self):
        examples = {
            "BOSTON, CITY OF": "CITY OF BOSTON",
            "  EXAMPLE  ,  UNIVERSITY OF  ": "UNIVERSITY OF EXAMPLE",
            "EXAMPLE, County of": "County of EXAMPLE",
            "EXAMPLE, INC.": "EXAMPLE, INC.",
            "EXAMPLE UNIVERSITY": "EXAMPLE UNIVERSITY",
            "OF EXAMPLE": "OF EXAMPLE",
            "EXAMPLE, CITY OF, DEPARTMENT": "EXAMPLE, CITY OF, DEPARTMENT",
        }
        for source, expected in examples.items():
            with self.subTest(source=source):
                self.assertEqual(client.uninvert_recipient_name(source), expected)

    def test_uninvert_handles_missing_names(self):
        for name in (None, "", 123, math.nan):
            with self.subTest(name=name):
                self.assertEqual(client.uninvert_recipient_name(name), "Unknown recipient")

    def test_display_uses_lifetime_label_and_does_not_mutate_source(self):
        source = pd.DataFrame([award(amount=1234.5, **{"Recipient Name": "BOSTON, CITY OF"}),
                               award("negative", -25, **{"Recipient Name": None})])
        before = source.copy(deep=True)
        output = client.format_grants_for_display(source)
        self.assertIn("Lifetime obligations", output)
        self.assertNotIn("Award Amount", output)
        self.assertIn("CITY OF BOSTON", output)
        self.assertIn("Unknown recipient", output)
        self.assertIn("$1,234", output)
        self.assertIn("$-25", output)
        pd.testing.assert_frame_equal(source, before)

    def test_convenience_searches_preserve_limits_and_normalized_filters(self):
        sentinel = object()
        with patch.object(client, "search_awards", return_value=sentinel) as search:
            self.assertIs(client.search_grants(" Example Agency ", 2024, 17), sentinel)
            search.assert_called_once_with(client.grant_filters(2024, 2024, agency_name="Example Agency"), 17)
        with patch.object(client, "search_awards", return_value=sentinel) as search:
            self.assertIs(client.search_grants_by_recipient(" EXAMPLE12345 ", 2024, 2025, 23), sentinel)
            search.assert_called_once_with(client.grant_filters(2024, 2025, recipient_text="EXAMPLE12345"), 23)


if __name__ == "__main__":
    unittest.main()
