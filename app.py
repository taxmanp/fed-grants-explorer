"""Streamlit dashboard for the Federal Grants Explorer."""

import plotly.express as px
import requests
import streamlit as st

from client import (
    get_toptier_agencies,
    search_grants,
    uninvert_recipient_name,
)

# ---------- Page configuration ----------
st.set_page_config(
    page_title="Federal Grants Explorer",
    page_icon="💰",
    layout="wide",
)


# ---------- Cached data loaders ----------
@st.cache_data(ttl=3600)
def load_agencies():
    return get_toptier_agencies()


@st.cache_data(ttl=3600)
def load_grants(agency_name: str, fiscal_year: int, limit: int):
    return search_grants(agency_name, fiscal_year, limit=limit)


# ---------- Header ----------
st.title("💰 Federal Grants Explorer")
st.markdown(
    "Interactive view of federal grant spending from "
    "[USAspending.gov](https://www.usaspending.gov/). "
    "Explore by **agency** to see where federal grant dollars flow, "
    "or by **recipient** to see an organization's federal funding history."
)

# ---------- Tabs ----------
tab_agency, tab_recipient = st.tabs(["📊 By Agency", "🏢 By Recipient"])


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

    # Filters in a horizontal row
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

    # Fetch grants
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

    # Clean up inverted recipient names
    grants = grants.copy()
    grants["Recipient Name"] = grants["Recipient Name"].apply(uninvert_recipient_name)

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total awarded", f"${grants['Award Amount'].sum():,.0f}")
    m2.metric("Unique recipients", f"{grants['Recipient Name'].nunique():,}")
    m3.metric("Unique sub-agencies", f"{grants['Awarding Sub Agency'].nunique():,}")

    # Sub-agency bar chart
    st.header("Total by sub-agency")
    summary = (
        grants.groupby("Awarding Sub Agency")["Award Amount"]
        .sum()
        .sort_values(ascending=True)
        .reset_index()
    )
    fig = px.bar(
        summary,
        x="Award Amount",
        y="Awarding Sub Agency",
        orientation="h",
        labels={"Award Amount": "Total Awarded ($)", "Awarding Sub Agency": ""},
    )
    fig.update_layout(
        showlegend=False,
        height=400,
        margin=dict(l=0, r=0, t=20, b=40),
        xaxis_tickprefix="$",
        xaxis_title="Total Awarded",
        yaxis_title="",
    )
    st.plotly_chart(fig, width="stretch")

    # Top 10 individual grants table
    st.header(f"Top 10 individual grants — {selected_agency}, FY{fiscal_year}")
    top_10 = grants.head(10)[["Recipient Name", "Award Amount", "Awarding Sub Agency"]]
    st.dataframe(
        top_10.style.format({"Award Amount": "${:,.0f}"}),
        width="stretch",
        hide_index=True,
    )


# ============================================================
# TAB 2: BY RECIPIENT (placeholder, filled in next commit)
# ============================================================
with tab_recipient:
    st.info(
        "🚧 **Coming next:** enter a recipient name to see all their federal grants "
        "across every agency over a range of fiscal years. Useful for understanding "
        "an organization's federal funding mix and how it has evolved over time."
    )