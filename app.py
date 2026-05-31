"""Streamlit dashboard for the Federal Grants Explorer."""

import plotly.express as px
import requests
import streamlit as st

from client import (
    get_toptier_agencies,
    search_grants,
    search_grants_by_recipient,
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
    [data-testid="stCaptionContainer"] {
        color: #64748B;
    }
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
def load_grants(agency_name: str, fiscal_year: int, limit: int):
    return search_grants(agency_name, fiscal_year, limit=limit)


@st.cache_data(ttl=3600)
def load_grants_by_recipient(
    recipient_text: str, start_year: int, end_year: int, limit: int
):
    return search_grants_by_recipient(
        recipient_text, start_year, end_year, limit=limit
    )


# ---------- Shared chart styler ----------
def styled_bar(df, x_col, y_col, label_x="Total Awarded"):
    """Horizontal bar chart with our standard branded styling."""
    fig = px.bar(
        df,
        x=x_col,
        y=y_col,
        orientation="h",
        color_discrete_sequence=[ACCENT],
        labels={x_col: f"{label_x} ($)", y_col: ""},
    )
    fig.update_traces(
        hovertemplate="<b>%{y}</b><br>$%{x:,.0f}<extra></extra>",
    )
    fig.update_layout(
        showlegend=False,
        height=420,
        margin=dict(l=0, r=0, t=20, b=40),
        xaxis_tickprefix="$",
        xaxis_title=label_x,
        yaxis_title="",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="#0F172A", size=12),
        xaxis=dict(gridcolor="#E2E8F0", zerolinecolor="#E2E8F0"),
        yaxis=dict(gridcolor="#E2E8F0"),
    )
    return fig


# ---------- Header ----------
st.title("Federal Grants Explorer")
st.markdown(
    "Interactive view of federal grant spending from "
    "[USAspending.gov](https://www.usaspending.gov/). "
    "Explore by **agency** to see where federal grant dollars flow, "
    "or by **recipient** to see an organization's federal funding history."
)

# ---------- Tabs ----------
tab_agency, tab_recipient = st.tabs(["By Agency", "By Recipient"])


# ============================================================
# TAB 1: BY AGENCY
# ============================================================
with tab_agency:
    try:
        agencies = load_agencies()
    except requests.exceptions.RequestException:
        st.error(
            "⚠️ Couldn't reach USAspending.gov right now. "
            "This is usually a temporary issue — try refreshing the page in a moment."
        )
        st.stop()

    agency_options = sorted(agencies["agency_name"].dropna().tolist())
    default_agency = "Department of Health and Human Services"
    default_idx = (
        agency_options.index(default_agency)
        if default_agency in agency_options
        else 0
    )

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        selected_agency = st.selectbox("Agency", agency_options, index=default_idx)
    with f2:
        fiscal_year = st.number_input(
            "Fiscal Year", min_value=2008, max_value=2026, value=2024, step=1
        )
    with f3:
        grant_limit = st.slider(
            "Top grants to fetch", min_value=10, max_value=100, value=100, step=10
        )

    try:
        with st.spinner(f"Fetching top {grant_limit} grants for {selected_agency}, FY{fiscal_year}..."):
            grants = load_grants(selected_agency, fiscal_year, grant_limit)
    except requests.exceptions.RequestException:
        st.error(
            f"⚠️ Couldn't fetch grants for {selected_agency} right now. "
            "USAspending may be having a temporary issue — try refreshing in a moment."
        )
        st.stop()

    if grants.empty:
        st.warning(f"No grants found for {selected_agency} in FY{fiscal_year}.")
        st.stop()

    grants = grants.copy()
    grants["Recipient Name"] = grants["Recipient Name"].apply(uninvert_recipient_name)

    st.divider()

    m1, m2, m3 = st.columns(3)
    m1.metric("Total awarded", f"${grants['Award Amount'].sum():,.0f}")
    m2.metric("Unique recipients", f"{grants['Recipient Name'].nunique():,}")
    m3.metric("Unique sub-agencies", f"{grants['Awarding Sub Agency'].nunique():,}")

    st.divider()

    st.subheader("Total by sub-agency")
    st.caption(
        f"Sum of award amounts across the top {grant_limit} grants from "
        f"{selected_agency} in FY{fiscal_year}."
    )
    summary = (
        grants.groupby("Awarding Sub Agency")["Award Amount"]
        .sum()
        .sort_values(ascending=True)
        .reset_index()
    )
    st.plotly_chart(styled_bar(summary, "Award Amount", "Awarding Sub Agency"), width="stretch")

    st.divider()

    st.subheader("Top 10 individual grants")
    st.caption(
        f"Largest individual grants from {selected_agency} in FY{fiscal_year}, "
        "by dollar amount."
    )
    top_10 = grants.head(10)[["Recipient Name", "Award Amount", "Awarding Sub Agency"]]
    st.dataframe(
        top_10.style.format({"Award Amount": "${:,.0f}"}),
        width="stretch",
        hide_index=True,
    )


# ============================================================
# TAB 2: BY RECIPIENT
# ============================================================
with tab_recipient:
    r1, r2, r3 = st.columns([2, 2, 1])
    with r1:
        recipient_text = st.text_input(
            "Recipient name (or UEI)",
            placeholder="e.g., 'University of California' or 'American Red Cross'",
            help="USAspending fuzzy-matches against recipient name, UEI, and DUNS. Partial names work.",
        )
    with r2:
        year_range = st.slider(
            "Fiscal years",
            min_value=2008,
            max_value=2026,
            value=(2020, 2025),
        )
    with r3:
        recipient_limit = st.slider(
            "Max results",
            min_value=10,
            max_value=100,
            value=100,
            step=10,
        )

    if not recipient_text:
        st.info(
            "**Enter a recipient name above** to see their federal grant history. "
            "Try `University of California`, `Yale University`, or `American Red Cross`."
        )
        st.stop()

    start_year, end_year = year_range

    try:
        with st.spinner(
            f"Searching grants matching '{recipient_text}' across FY{start_year}–FY{end_year}..."
        ):
            r_grants = load_grants_by_recipient(
                recipient_text, start_year, end_year, recipient_limit
            )
    except requests.exceptions.RequestException:
        st.error(
            "⚠️ Couldn't fetch grants right now. "
            "USAspending may be having a temporary issue — try refreshing in a moment."
        )
        st.stop()

    if r_grants.empty:
        st.warning(
            f"No grants found matching '{recipient_text}' between FY{start_year} and FY{end_year}. "
            "Try a different spelling, a partial name, or a wider year range."
        )
        st.stop()

    r_grants = r_grants.copy()
    r_grants["Recipient Name"] = r_grants["Recipient Name"].apply(uninvert_recipient_name)

    st.divider()

    rm1, rm2, rm3 = st.columns(3)
    rm1.metric("Total funding", f"${r_grants['Award Amount'].sum():,.0f}")
    rm2.metric("Number of awards", f"{len(r_grants):,}")
    rm3.metric("Awarding agencies", f"{r_grants['Awarding Agency'].nunique():,}")

    st.divider()

    st.subheader("Total by awarding agency")
    st.caption(
        f"Sum of award amounts to '{recipient_text}' across FY{start_year}–FY{end_year}, "
        "grouped by top-tier agency."
    )
    agency_summary = (
        r_grants.groupby("Awarding Agency")["Award Amount"]
        .sum()
        .sort_values(ascending=True)
        .reset_index()
    )
    st.plotly_chart(styled_bar(agency_summary, "Award Amount", "Awarding Agency"), width="stretch")

    st.divider()

    st.subheader("Individual grants")
    st.caption(
        f"All grants matching '{recipient_text}' from FY{start_year}–FY{end_year}, "
        "sorted by amount."
    )
    display = (
        r_grants[[
            "Recipient Name",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Period of Performance Start Date",
        ]]
        .rename(columns={"Period of Performance Start Date": "Start Date"})
        .fillna("—")
    )
    st.dataframe(
        display.style.format({"Award Amount": "${:,.0f}"}),
        width="stretch",
        hide_index=True,
    )


# ---------- Footer ----------
st.divider()
st.caption(
    "Data from [USAspending.gov](https://www.usaspending.gov/) · "
    "Built with [Streamlit](https://streamlit.io/) and [Plotly](https://plotly.com/python/) · "
    "[Source on GitHub](https://github.com/taxmanp/fed-grants-explorer)"
)