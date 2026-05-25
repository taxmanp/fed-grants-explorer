"""Streamlit dashboard for the Federal Grants Explorer."""

import plotly.express as px
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
# These wrap our API calls so Streamlit doesn't refetch on every interaction.
# ttl = "time to live" in seconds; 3600 = 1 hour.
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
    "Pick an agency and fiscal year to explore where federal grant dollars actually go."
)

# ---------- Sidebar filters ----------
with st.sidebar:
    st.header("Filters")

    agencies = load_agencies()
    agency_options = sorted(agencies["agency_name"].dropna().tolist())
    default_agency = "Department of Health and Human Services"
    default_idx = (
        agency_options.index(default_agency)
        if default_agency in agency_options
        else 0
    )
    selected_agency = st.selectbox("Agency", agency_options, index=default_idx)

    fiscal_year = st.number_input(
        "Fiscal Year", min_value=2008, max_value=2026, value=2024, step=1
    )

    grant_limit = st.slider(
        "How many top grants to fetch", min_value=10, max_value=100, value=100, step=10
    )

# ---------- Fetch grants ----------
with st.spinner(f"Fetching top {grant_limit} grants for {selected_agency}, FY{fiscal_year}..."):
    grants = load_grants(selected_agency, fiscal_year, grant_limit)

if grants.empty:
    st.warning(f"No grants found for {selected_agency} in FY{fiscal_year}.")
    st.stop()

# Clean up the inverted recipient names
grants = grants.copy()
grants["Recipient Name"] = grants["Recipient Name"].apply(uninvert_recipient_name)

# ---------- Summary metrics ----------
col1, col2, col3 = st.columns(3)
col1.metric("Total awarded", f"${grants['Award Amount'].sum():,.0f}")
col2.metric("Unique recipients", f"{grants['Recipient Name'].nunique():,}")
col3.metric("Unique sub-agencies", f"{grants['Awarding Sub Agency'].nunique():,}")

# ---------- Sub-agency bar chart ----------
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

# ---------- Top individual grants table ----------
st.header(f"Top 10 individual grants — {selected_agency}, FY{fiscal_year}")
top_10 = grants.head(10)[["Recipient Name", "Award Amount", "Awarding Sub Agency"]]
st.dataframe(
    top_10.style.format({"Award Amount": "${:,.0f}"}),
    width="stretch",
    hide_index=True,
)