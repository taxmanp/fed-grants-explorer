"""Streamlit dashboard for the Federal Grants Explorer."""

import math

import plotly.express as px
import requests
import streamlit as st

from client import (
    APIDataError,
    MIN_FISCAL_YEAR,
    current_fiscal_year,
    get_period_obligations,
    get_toptier_agencies,
    grant_filters,
    search_awards,
    uninvert_recipient_name,
)

# ---------- Page configuration ----------
st.set_page_config(
    page_title="Federal Grants Explorer",
    page_icon="💰",
    layout="wide",
)

# ---------- Custom styling ----------
st.markdown(
    """
    <style>
    /* Import editorial-grade fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Serif:wght@500;600;700&display=swap');

    /* Modern sans for body */
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    /* Sharp serif for headlines — editorial finance look */
    h1, h2, h3 {
        font-family: 'IBM Plex Serif', Georgia, serif;
        font-weight: 600;
        letter-spacing: -0.02em;
    }
    h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }

    /* Metric labels: small, uppercase, tracked-out */
    [data-testid="stMetricLabel"] p {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748B;
        font-weight: 500;
    }

    /* Metric values: tabular nums for clean alignment */
    [data-testid="stMetricValue"] {
        font-variant-numeric: tabular-nums;
        font-weight: 600;
        color: #0F172A;
    }

    /* Tabs: cleaner spacing */
    button[data-baseweb="tab"] {
        font-weight: 500;
        padding-left: 20px;
        padding-right: 20px;
    }

    /* Softer dividers */
    hr {
        margin: 2rem 0;
        border-color: #E2E8F0;
    }

    /* Captions */
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        color: #475569;
    }
    [data-testid="stCaptionContainer"] { opacity: 1; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Accent color — keep in sync with .streamlit/config.toml's primaryColor
ACCENT = "#1E40AF"


# ---------- Cached data loaders ----------
@st.cache_data(ttl=3600)
def load_agencies():
    return get_toptier_agencies()


@st.cache_data(ttl=3600)
def load_awards(filters, limit):
    return search_awards(filters, max_results=limit)


@st.cache_data(ttl=3600)
def load_obligations(filters):
    return get_period_obligations(filters)


def styled_bar(df, x_col, y_col, label_x="Lifetime obligations"):
    fig = px.bar(df, x=x_col, y=y_col, orientation="h",
                 color_discrete_sequence=[ACCENT], labels={x_col: f"{label_x} ($)", y_col: ""})
    fig.update_traces(hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>")
    fig.update_layout(showlegend=False, height=420, margin=dict(l=0, r=0, t=20, b=40),
                      xaxis_tickprefix="$", xaxis_title=label_x, yaxis_title="",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter", color="#0F172A", size=12),
                      xaxis=dict(gridcolor="#E2E8F0", zerolinecolor="#E2E8F0"),
                      yaxis=dict(gridcolor="#E2E8F0"))
    return fig


def render_results(filters, limit, start_year, end_year, label, key, group_column):
    st.divider()
    st.subheader(label)
    period = filters["time_period"][0]
    st.caption(f"Selected dates: {period['start_date']} through {period['end_date']} (inclusive).")
    if end_year == current_fiscal_year():
        st.info(f"FY{end_year} is still in progress. Current-year totals reflect reported activity so far and may lag.")
    if st.button("Refresh these results", key=f"{key}_refresh"):
        load_awards.clear(filters, limit)
        load_obligations.clear(filters)

    total, result = None, None
    # Independent requests: neither failure can silently turn into zero or a sample sum.
    with st.spinner("Loading fiscal-period totals and award details..."):
        try:
            total = load_obligations(filters)
        except (requests.RequestException, APIDataError):
            st.error("Fiscal-period obligations are unavailable. Award details may still load; use Refresh to retry.")
        try:
            result = load_awards(filters, limit)
        except (requests.RequestException, APIDataError):
            st.error("Award details could not be loaded or validated. Use Refresh to retry.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Period net obligations", f"${total.total:,.0f}" if total is not None else "Unavailable")
    m2.metric("Awards loaded", f"{len(result.awards):,}" if result is not None else "Unavailable")
    m3.metric("Loaded awards: lifetime obligations",
              f"${math.fsum(result.awards['Award Amount']):,.0f}" if result is not None else "Unavailable")
    st.caption("Period net obligations include obligations and deobligations on matching grant transactions "
               "dated within the selection. This is an API-wide aggregate, independent of the award-list limit. "
               "Obligations are commitments, not payments or outlays.")
    if total is not None:
        st.caption(f"Transaction aggregate retrieved {total.fetched_at}; cached for up to one hour.")
        if start_year != end_year:
            st.subheader("Net obligations by fiscal year")
            annual = total.by_fiscal_year.copy()
            annual["Fiscal year"] = annual["Fiscal year"].map(lambda year: f"FY{year}")
            st.plotly_chart(styled_bar(annual, "Net obligations", "Fiscal year", "Period net obligations"),
                            width="stretch", key=f"{key}_years")

    if result is not None:
        coverage = f"{len(result.awards):,} unique awards loaded across {result.pages_loaded} page(s). {result.reason}"
        if result.complete:
            st.info(coverage)
        else:
            st.warning(coverage + " Charts and lifetime sums describe only these loaded awards.")
        st.caption(f"Award details retrieved {result.fetched_at}; cached for up to one hour.")
        st.caption("The award list uses USAspending's activity-span overlap search: latest transaction date "
                   "on or after the selection's start and base award date on or before its end. "
                   "A listed award may have no transaction within the selected period. Lifetime amounts can "
                   "include activity before and after that period, so these two dollar metrics do not reconcile.")
        if result.awards.empty:
            st.info("No award rows were returned for this search. This does not replace the transaction total above.")
        else:
            grants = result.awards.copy()
            # Keep missing agencies in the chart, rather than silently dropping their dollars.
            grants[group_column] = grants[group_column].fillna("Unknown agency")
            summary = (grants.groupby(group_column, dropna=False)["Award Amount"].sum()
                       .sort_values().reset_index())
            st.subheader(f"Loaded awards by {'sub-agency' if key == 'agency' else 'awarding agency'}")
            st.caption("Sum of lifetime obligations among loaded awards only. Broad searches may be partial.")
            st.plotly_chart(styled_bar(summary, "Award Amount", group_column),
                            width="stretch", key=f"{key}_agencies")
            st.subheader("Loaded award details")
            st.caption("Sorted by lifetime obligations. Start date is the period-of-performance start, "
                       "not the transaction date. Names are reformatted for readability; UEIs and award IDs "
                       "help distinguish organizations and awards.")
            display = grants.rename(columns={"Award Amount": "Lifetime obligations",
                                              "Start Date": "Performance start date"}).copy()
            display["Recipient Name"] = display["Recipient Name"].apply(uninvert_recipient_name)
            st.dataframe(display[["Award ID", "Recipient Name", "Recipient UEI", "Lifetime obligations",
                                  "Awarding Agency", "Awarding Sub Agency", "Performance start date"]],
                         column_config={"Lifetime obligations": st.column_config.NumberColumn(format="dollar")},
                         width="stretch", hide_index=True)
    messages = list(dict.fromkeys((total.messages if total else ()) + (result.messages if result else ())))
    if messages:
        with st.expander("USAspending response notices"):
            for message in messages:
                st.write(message)


def render_agency():
    try:
        agencies = load_agencies()
    except (requests.RequestException, APIDataError):
        st.error("The agency directory could not be loaded. Recipient search is still available.")
        if st.button("Retry agency directory"):
            load_agencies.clear()
            st.rerun()
        return
    options = sorted(agencies["agency_name"].dropna().unique().tolist())
    if not options:
        st.warning("USAspending returned an empty agency directory. Recipient search is still available.")
        if st.button("Retry agency directory"):
            load_agencies.clear()
            st.rerun()
        return
    default = "Department of Health and Human Services"
    with st.form("agency_filters"):
        f1, f2, f3 = st.columns([2, 1, 1])
        agency = f1.selectbox("Agency", options, index=options.index(default) if default in options else 0)
        year = f2.number_input("Fiscal year", min_value=MIN_FISCAL_YEAR, max_value=current_fiscal_year(),
                               value=current_fiscal_year() - 1, step=1)
        limit = f3.selectbox("Award detail limit", [100, 250, 500, 1000],
                             help="Only the award list and its lifetime summaries use this cap. Period totals do not.")
        submitted = st.form_submit_button("Explore agency")
    if submitted:
        st.session_state["agency_query"] = (agency, year, limit)
    if "agency_query" not in st.session_state:
        st.info("Choose an agency and fiscal year, then select Explore agency.")
        return
    agency, year, limit = st.session_state["agency_query"]
    render_results(grant_filters(year, year, agency_name=agency), limit, year, year,
                   f"{agency} · FY{year}", "agency", "Awarding Sub Agency")


def render_recipient():
    with st.form("recipient_filters"):
        r1, r2, r3 = st.columns([2, 2, 1])
        text = r1.text_input("Recipient or parent name / UEI", placeholder="e.g., University of California",
                             help="USAspending searches recipient and parent-recipient names, UEIs, and DUNS. "
                                  "Results can include multiple organizations; a name search is not verified identity.")
        years = r2.slider("Fiscal years", min_value=MIN_FISCAL_YEAR, max_value=current_fiscal_year(),
                           value=(max(MIN_FISCAL_YEAR, current_fiscal_year() - 6), current_fiscal_year() - 1))
        limit = r3.selectbox("Award detail limit", [100, 250, 500, 1000], key="recipient_limit")
        submitted = st.form_submit_button("Search recipients")
    st.caption("Text matching can include parent organizations and several recipients. Check names and UEIs; "
               "results are not a guaranteed complete funding history for one organization.")
    if submitted:
        if not text.strip():
            st.session_state.pop("recipient_query", None)
            st.warning("Enter a recipient name or UEI to search.")
            return
        st.session_state["recipient_query"] = (text.strip(), years[0], years[1], limit)
    if "recipient_query" not in st.session_state:
        st.info("Enter a recipient or parent name / UEI, then select Search recipients.")
        return
    text, start, end, limit = st.session_state["recipient_query"]
    render_results(grant_filters(start, end, recipient_text=text), limit, start, end,
                   f"Matches for {text} · FY{start}–FY{end}", "recipient", "Awarding Agency")


st.title("Federal Grants Explorer")
st.markdown("Explore federal grant obligations from [USAspending.gov](https://www.usaspending.gov/) "
            "by awarding agency or recipient search. Compare fiscal-period activity with individual award details.")
with st.expander("What these numbers mean"):
    st.write("Includes prime grants and cooperative agreements (award types 02–05) from FY2008 onward. "
             "Period totals use transaction action dates; award detail amounts are cumulative lifetime obligations. "
             "The award list loads at most 1,000 records, with explicit partial-result warnings. "
             "Negative obligations are retained. This explorer is not an accounting reconciliation or a data download.")
    st.write("A federal fiscal year runs October 1 through September 30. "
             "The current fiscal year is incomplete; reporting and later corrections can change historical totals.")

agency_tab, recipient_tab = st.tabs(["By Agency", "By Recipient"])
with agency_tab:
    render_agency()
with recipient_tab:
    render_recipient()

st.divider()
st.caption("Data from [USAspending.gov](https://www.usaspending.gov/) · "
           "Built with [Streamlit](https://streamlit.io/) and [Plotly](https://plotly.com/python/) · "
           "[Source on GitHub](https://github.com/taxmanp/fed-grants-explorer)")
