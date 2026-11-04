import altair as alt
import pandas as pd
import streamlit as st

from income_summary import build_year_summary
from eurostat_api import fetch_income, fetch_income_catalogue
from real_income_view import render_real_income_view
from housing_view import render_housing_view
from urban_income_view import render_urban_income_view


st.set_page_config(page_title="EURO_DATA | Income explorer", layout="wide")

AGE_LABELS = {
    "TOTAL": "All ages",
    "Y_LT18": "0–17",
    "Y18-24": "18–24",
    "Y25-49": "25–49",
    "Y50-64": "50–64",
    "Y_GE65": "65+",
}


@st.cache_data(ttl=3600, show_spinner="Loading available options...")
def load_catalogue():
    return fetch_income_catalogue()


@st.cache_data(ttl=3600, max_entries=128, show_spinner="Fetching income data...")
def load_income(countries, start_year, end_year, indicator, unit, ages):
    # Ages are part of the cache key, so TOTAL and age-group requests stay separate.
    return fetch_income(
        countries, start_year, end_year, indicator, unit, ages=ages
    )


# Keep the view selector outside the form so its controls update immediately.
view = st.sidebar.radio(
    "View",
    [
        "Countries",
        "Age groups",
        "Real change (Greece)",
        "Housing",
        "Urbanisation"])
age_view = view == "Age groups"

if view == "Urbanisation":
    render_urban_income_view()
    st.stop()

if view == "Housing":
    render_housing_view()
    st.stop()

st.title("EURO_DATA | Income explorer")
if view == "Real change (Greece)":
    scope = "Selected age group | Greece"
else:
    scope = "Five age groups" if age_view else "All ages"
st.caption(f"Equivalised disposable income | {scope} | Total sex")
st.caption(
    "Years are survey years. Income reference periods can differ "
    "by country and period."
)

try:
    catalogue = load_catalogue()
except (RuntimeError, ValueError) as exc:
    st.error(f"Could not load the available options: {exc}")
    st.stop()

available = catalogue.loc[catalogue["value"].notna()]
labels = {
    dim: available[[dim, f"{dim}_label"]].drop_duplicates()
    .set_index(dim)[f"{dim}_label"].to_dict()
    for dim in ["geo", "statinfo", "unit"]
}
country_options = sorted(labels["geo"], key=labels["geo"].get)
years = sorted(available["time"].astype(int).unique().tolist())
indicators = sorted(labels["statinfo"])
default_period = (
    (2022, 2024)
    if {2022, 2024}.issubset(years)
    else (years[0], years[-1]))

if view == "Real change (Greece)":
    render_real_income_view(years, labels["statinfo"], AGE_LABELS)
    st.stop()

with st.sidebar:
    st.header("Filters")

    with st.form("income_filters"):
        if age_view:
            country = st.selectbox(
                "Country",
                options=country_options,
                index=country_options.index("EL") if "EL" in country_options else 0,
                format_func=labels["geo"].get,
            )
            countries = [country]
            ages = [code for code in AGE_LABELS if code != "TOTAL"]
            st.caption("The five published age groups are shown separately.")
        else:
            countries = st.multiselect(
                "Countries",
                options=country_options,
                default=[code for code in ["EL", "DE", "FR"] if code in labels["geo"]],
                format_func=labels["geo"].get,
            )
            ages = ["TOTAL"]

        start_year, end_year = st.select_slider(
            "Survey years",
            options=years,
            value=default_period,
        )
        indicator = st.selectbox(
            "Income measure",
            options=indicators,
            index=indicators.index("MED_EI"),
            format_func=labels["statinfo"].get,
        )
        unit = st.selectbox(
            "Unit",
            options=sorted(labels["unit"]),
            format_func=labels["unit"].get,
        )
        submitted = st.form_submit_button("Load data", type="primary")

    st.caption("Select Load data to apply your choices.")

if not submitted:
    st.info("Choose filters in the sidebar, then select Load data.")
    st.stop()

if not countries:
    st.warning("Select at least one country.")
    st.stop()

try:
    frame = load_income(
        tuple(countries), start_year, end_year, indicator, unit, tuple(ages)
    )
except (RuntimeError, ValueError) as exc:
    st.error(f"Could not load income data: {exc}")
    st.stop()

# Keep every requested country-age-year combination, including missing ones.
key = ["geo", "age", "time"]
requested = pd.MultiIndex.from_product(
    [countries, ages, [str(year) for year in range(start_year, end_year + 1)]],
    names=key,
)
table = frame.set_index(key)[["value", "obs_flag"]].reindex(requested).reset_index()
table["geo_label"] = table["geo"].map(labels["geo"])
table["age_group"] = table["age"].map(AGE_LABELS)
table["time"] = table["time"].astype(int)
table["age"] = pd.Categorical(table["age"], categories=list(AGE_LABELS), ordered=True)
table = table.sort_values(["geo_label", "age", "time"])

# Both views share the chart; only the comparison series changes.
table["series"] = table["age_group"] if age_view else table["geo_label"]
series_title = "Age group" if age_view else "Country"
series_order = (
    [AGE_LABELS[code] for code in ages]
    if age_view else sorted(table["geo_label"].unique())
)

available_count = int(table["value"].notna().sum())
missing_count = len(table) - available_count
flagged_count = int(table["obs_flag"].fillna("").ne("").sum())

st.subheader(f"{labels['statinfo'][indicator]} ({unit})")
selection = labels["geo"][countries[0]] if age_view else "Selected countries"
st.caption(f"{selection} | Applied survey years: {start_year}-{end_year}")

counts = st.columns(4)
counts[0].metric("Requested", len(table))
counts[1].metric("Available", available_count)
counts[2].metric("Missing", missing_count)
counts[3].metric("Flagged", flagged_count)

if missing_count:
    st.warning(f"{missing_count} requested observations have no published value.")

unit_notes = {
    "EUR": "EUR values are nominal and have not been adjusted for inflation.",
    "PPS": "PPS supports comparisons across countries; it is not a constant-price series.",
    "NAC": "National currencies differ across countries. Compare values within each currency.",
}
st.caption(unit_notes.get(unit, labels["unit"][unit]))

if unit == "NAC":
    st.info(
        "Choose EUR or PPS for this chart. NAC uses national currencies, "
        "which may differ by country and period. NAC values remain in the table."
    )
else:
    st.subheader(
        f"{series_title} comparison" if start_year == end_year else "Income over time"
    )
    chart_data = table.copy()
    chart_data["flag_text"] = chart_data["obs_flag"].fillna("")
    chart_data["flagged"] = chart_data["flag_text"].ne("")
    chart_data["break_before"] = chart_data["flag_text"].str.contains("b", regex=False)

    # Breaks belong to a specific country and age group.
    chart_data["segment"] = chart_data.groupby(
        ["geo", "age"], sort=False, observed=True
    )["break_before"].cumsum()

    base = alt.Chart(chart_data).encode(
        color=alt.Color(
            "series:N",
            title=series_title,
            sort=series_order,
            scale=alt.Scale(domain=series_order, scheme="tableau10"),
            legend=alt.Legend(orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("geo_label:N", title="Country"),
            alt.Tooltip("age_group:N", title="Age group"),
            alt.Tooltip("time:O", title="Survey year"),
            alt.Tooltip("value:Q", title=f"Income ({unit})", format=",.2f"),
            alt.Tooltip("flag_text:N", title="Eurostat flag"),
        ],
    )

    if start_year == end_year:
        # Age bars follow age order; country bars follow descending income.
        bar_order = series_order if age_view else (
            chart_data.sort_values("value", ascending=False, na_position="last")
            ["series"].tolist()
        )
        x = alt.X("value:Q", title=f"Income ({unit})", scale=alt.Scale(zero=True))
        y = alt.Y(
            "series:N",
            title=None,
            sort=bar_order,
            axis=alt.Axis(labelOverlap=False))

        bars = base.mark_bar().encode(x=x, y=y)
        flagged = (
            base.transform_filter(alt.datum.flagged)
            .mark_point(
                shape="diamond", filled=True, size=140,
                stroke="white", strokeWidth=1,
            )
            .encode(x=x, y=y)
        )
        chart = (bars + flagged).properties(height=max(220, 28 * len(series_order)))

    else:
        x = alt.X("time:O", title="Survey year", axis=alt.Axis(labelAngle=0))
        y = alt.Y("value:Q", title=f"Income ({unit})", scale=alt.Scale(zero=True))

        lines = base.mark_line(
            strokeWidth=2, invalid="break-paths-show-domains"
        ).encode(
            x=x, y=y,
            detail=["geo:N", "age:N", "segment:N"],
            order=alt.Order("time:Q"),
        )
        points = base.mark_point(filled=True, size=80, opacity=1).encode(
            x=x, y=y,
            shape=alt.condition(
                alt.datum.flagged, alt.value("diamond"), alt.value("circle")
            ),
        )
        chart = (lines + points).properties(height=420)

    chart_height = (
        max(360, 36 * len(series_order) + 140)
        if start_year == end_year else 500
    )
    st.altair_chart(
        chart.properties(height=chart_height),
        width="stretch",
        height=chart_height)
    st.caption("Diamonds mark flagged observations.")

    if start_year != end_year:
        st.caption("Lines stop at missing values and restart at b flags.")

if unit != "NAC":
    st.subheader(f"Summary for survey year {end_year}")
    summary = build_year_summary(
        table,
        end_year,
        unit,
        labels["statinfo"][indicator],
        "age groups" if age_view else "countries",
    )
    for line in summary:
        st.write(line)

display_columns = ["geo_label", "geo"]
if age_view:
    display_columns.append("age_group")
display_columns += ["time", "value", "obs_flag"]

st.dataframe(
    table[display_columns],
    hide_index=True,
    width="stretch",
    column_config={
        "geo_label": "Country",
        "geo": "Code",
        "age_group": "Age group",
        "time": st.column_config.NumberColumn("Survey year", format="%d"),
        "value": st.column_config.NumberColumn(f"Income ({unit})", format="%.2f"),
        "obs_flag": "Flag",
    },
)

with st.expander("Source and notes"):
    st.write("Source: Eurostat, ilc_di03.")
    st.write("Retrieved at UTC:", frame.attrs["retrieved_at_utc"])
    st.write("Eurostat updated:", frame.attrs["eurostat_metadata"].get("updated"))
    st.markdown(f"[Open API response]({frame.attrs['request_url']})")
    st.write(
        "Flags: b = break in time series; e = estimated; "
        "p = provisional; u = low reliability. Combined flags are preserved."
    )
    st.caption(
        "Responses are cached for up to one hour. "
        "The retrieval time belongs to the cached response."
    )