"""Offline Streamlit interaction regression tests. No network calls."""

from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from client import AWARD_FIELDS, AwardSearchResult, PeriodObligations, current_fiscal_year

APP = Path(__file__).resolve().parents[1] / "app.py"
AGENCY = "Department of Health and Human Services"


def award_result(*, empty=False, complete=False):
    rows = [] if empty else [{"Award ID": "A1", "generated_internal_id": "ASST_A1",
        "Recipient Name": "SERVICES, STATE DEPARTMENT OF", "Recipient UEI": "TESTUEI",
        "Award Amount": 1_000_000.0, "Awarding Agency": AGENCY,
        "Awarding Sub Agency": None, "Start Date": None}]
    return AwardSearchResult(pd.DataFrame(rows, columns=AWARD_FIELDS), complete,
                             "No more pages." if complete else "Result limit reached; more awards may match.",
                             1, "2026-10-11T00:00:00+00:00")


def total_result(value=25.0):
    return PeriodObligations(pd.DataFrame([{"Fiscal year": 2026, "Net obligations": value}]),
                             "2026-10-11T00:00:00+00:00")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.agencies = self.stack.enter_context(patch("client.get_toptier_agencies",
            return_value=pd.DataFrame({"agency_name": [AGENCY]})))
        self.awards = self.stack.enter_context(patch("client.search_awards", return_value=award_result()))
        self.total = self.stack.enter_context(patch("client.get_period_obligations", return_value=total_result()))
        # Any accidental unmocked network access fails immediately.
        self.stack.enter_context(patch("requests.sessions.Session.request",
                                      side_effect=AssertionError("Unexpected network request")))

    def start(self):
        return AppTest.from_file(str(APP)).run(timeout=15)

    def submit_agency(self, at):
        return at.button(key="FormSubmitter:agency_filters-Explore agency").click().run(timeout=15)

    def submit_recipient(self, at, text="Example university"):
        at.text_input[0].set_value(text)
        return at.button(key="FormSubmitter:recipient_filters-Search recipients").click().run(timeout=15)

    def test_initial_view_has_both_forms_footer_and_dynamic_year(self):
        at = self.start()
        self.assertFalse(at.exception)
        self.assertEqual(at.number_input[0].value, current_fiscal_year() - 1)
        self.assertEqual(at.number_input[0].max, current_fiscal_year())
        self.assertEqual(len(at.text_input), 1)
        self.assertTrue(any("Source on GitHub" in c.value for c in at.caption))
        self.total.assert_not_called()
        self.awards.assert_not_called()

    def test_period_total_is_not_lifetime_sample_and_partial_warning_visible(self):
        at = self.submit_agency(self.start())
        self.assertFalse(at.exception)
        self.assertEqual([m.value for m in at.metric], ["$25", "1", "$1,000,000"])
        self.assertTrue(any("only these loaded awards" in w.value for w in at.warning))
        self.assertEqual(len(at.dataframe), 1)
        self.assertIn("Unknown agency", at.dataframe[0].value["Awarding Sub Agency"].tolist())
        self.assertTrue(any("do not reconcile" in c.value for c in at.caption))

    def test_empty_awards_leave_transaction_metric_visible(self):
        self.awards.return_value = award_result(empty=True, complete=True)
        at = self.submit_agency(self.start())
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value, "$25")
        self.assertEqual(at.metric[1].value, "0")
        self.assertEqual(len(at.text_input), 1)
        self.assertTrue(any("No award rows" in i.value for i in at.info))

    def test_aggregate_failure_never_uses_sample_total_as_fallback(self):
        self.total.side_effect = requests.Timeout("timeout")
        at = self.submit_agency(self.start())
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value, "Unavailable")
        self.assertEqual(at.metric[2].value, "$1,000,000")
        self.assertTrue(any("Fiscal-period obligations are unavailable" in e.value for e in at.error))

    def test_award_failure_keeps_valid_aggregate(self):
        self.awards.side_effect = requests.Timeout("timeout")
        at = self.submit_agency(self.start())
        self.assertFalse(at.exception)
        self.assertEqual([m.value for m in at.metric], ["$25", "Unavailable", "Unavailable"])

    def test_agency_failure_does_not_block_recipient_search(self):
        self.agencies.side_effect = requests.Timeout("timeout")
        at = self.submit_recipient(self.start())
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value, "$25")
        self.assertIn("recipient_search_text", self.total.call_args.args[0])
        self.assertTrue(any("Source on GitHub" in c.value for c in at.caption))

    def test_empty_agency_directory_can_retry_immediately(self):
        self.agencies.return_value = pd.DataFrame(columns=["agency_name"])
        at = self.start()
        self.assertFalse(at.exception)
        self.agencies.return_value = pd.DataFrame({"agency_name": [AGENCY]})
        next(button for button in at.button if button.label == "Retry agency directory").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(self.agencies.call_count, 2)
        self.assertTrue(any(button.label == "Explore agency" for button in at.button))

    def test_blank_recipient_clears_old_results_and_makes_no_search(self):
        at = self.submit_recipient(self.start())
        self.total.reset_mock()
        self.awards.reset_mock()
        at = self.submit_recipient(at, "   ")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.metric), 0)
        self.assertTrue(any("Enter a recipient" in w.value for w in at.warning))
        self.total.assert_not_called()
        self.awards.assert_not_called()

    def test_submitted_filters_remain_labeled_until_resubmission(self):
        at = self.submit_agency(self.start())
        original_year = current_fiscal_year() - 1
        at.number_input[0].set_value(original_year - 1).run()
        self.assertTrue(any(f"FY{original_year}" in h.value for h in at.subheader))
        self.assertFalse(at.exception)
        at = self.submit_agency(at)
        self.assertTrue(any(f"FY{original_year - 1}" in h.value for h in at.subheader))
        self.assertEqual(self.total.call_args.args[0]["time_period"][0]["end_date"],
                         f"{original_year - 1}-09-30")

    def test_refresh_reloads_both_sources_and_recipient_does_not_break_agency(self):
        at = self.submit_agency(self.start())
        at.button(key="agency_refresh").click().run(timeout=15)
        self.assertEqual(self.total.call_count, 2)
        self.assertEqual(self.awards.call_count, 2)
        at = self.submit_recipient(at)
        self.assertFalse(at.exception)
        self.assertEqual(len(at.metric), 6)
        self.assertEqual(len(at.dataframe), 2)

    def test_current_year_warning_and_negative_obligations(self):
        self.total.return_value = total_result(-50.0)
        at = self.start()
        at.number_input[0].set_value(current_fiscal_year())
        at = self.submit_agency(at)
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[0].value, "$-50")
        self.assertTrue(any("still in progress" in i.value for i in at.info))


if __name__ == "__main__":
    unittest.main()
