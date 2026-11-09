import altair as alt
import pandas as pd
import streamlit as st

from income_changes import compare_income_years
from income_comparison import build_eur_pps_pairs, rank_eur_pps_pairs
from income_summary import build_year_summary
from eurostat_api import fetch_income, fetch_income_catalogue, fetch_income_for_changes
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
SEX_LABELS = {"F": "Females", "M": "Males", "T": "Total"}

@st.cache_data(ttl=3600, show_spinner="Loading available options...")
def load_catalogue():
    return fetch_income_catalogue()


@st.cache_data(ttl=3600, max_entries=128, show_spinner="Fetching income data...")
def load_income(
    countries, start_year, end_year, indicator, unit, ages, sexes, survey_years,
    selected_years, include_annual, include_period,
):
    if include_annual or include_period:
        return fetch_income_for_changes(
            countries, selected_years, indicator=indicator, unit=unit,
            ages=ages, sexes=sexes, include_previous_years=include_annual,
            include_period_years=include_period,
        )
    return fetch_income(
        countries, start_year, end_year, indicator, unit,
        ages=ages, sexes=sexes, survey_years=survey_years,
    )


# Keep the view selector outside the form so its controls update immediately.
view = st.sidebar.radio(
    "Analysis",
    [
        "Countries",
        "Age groups",
        "Real change (Greece)",
        "Housing",
        "Urbanisation",
    ],
    index=None)

# Wait for an explicit selection before loading analysis options.
if view is None:
    st.title("EURO_DATA | Income explorer")
    st.info("Choose an analysis from the sidebar to begin.")
    st.stop()

age_view = view == "Age groups"

if view == "Urbanisation":
    render_urban_income_view()
    st.stop()

if view == "Housing":
    render_housing_view()
    st.stop()

st.title("EURO_DATA | Income explorer")
if view == "Real change (Greece)":
    scope = "Selected age group | Greece | Total sex"
else:
    scope = "Age group comparison" if age_view else "Country comparison"
st.caption(f"Equivalised disposable income | {scope}")
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


if view == "Real change (Greece)":
    render_real_income_view(years, labels["statinfo"], AGE_LABELS)
    st.stop()

with st.sidebar:
    st.header("Filters")
    year_mode = st.radio("Year selection", ["Range", "Specific years"], horizontal=True)

    with st.form("income_filters"):
        if age_view:
            country = st.selectbox(
                "Country",
                options=country_options,
                index=None,
                format_func=labels["geo"].get,
            )
            countries = [country] if country is not None else []
            selected_ages = st.multiselect(
                "Age groups",
                options=[code for code in AGE_LABELS if code != "TOTAL"],
                default=[],
                format_func=AGE_LABELS.get,
            )
            ages = [code for code in AGE_LABELS if code in selected_ages]
        else:
            countries = st.multiselect(
                "Countries",
                options=country_options,
                default=[],
                format_func=labels["geo"].get,
            )
            selected_age = st.selectbox(
                "Age group",
                options=list(AGE_LABELS),
                index=None,
                format_func=AGE_LABELS.get,
            )
            ages = [selected_age] if selected_age is not None else []


        sexes = st.multiselect(
            "Sex",
            options=list(SEX_LABELS),
            default=[],
            format_func=SEX_LABELS.get,
        )

        if year_mode == "Range":
            range_start = st.selectbox(
                "Start survey year", options=years, index=None
            )
            range_end = st.selectbox(
                "End survey year", options=years, index=None
            )
            specific_years = []
        else:
            range_start = None
            range_end = None
            specific_years = st.multiselect("Survey years", options=years, default=[])
        indicator = st.selectbox(
            "Income measure",
            options=indicators,
            index=None,
            format_func=labels["statinfo"].get,
        )
        comparison_units = ("EUR", "PPS")
        unit_labels = dict(sorted(labels["unit"].items()))
        if not age_view and set(comparison_units).issubset(unit_labels):
            unit_labels[comparison_units] = "Euro and PPS"

        unit = st.selectbox(
            "Unit",
            options=list(unit_labels),
            index=None,
            format_func=unit_labels.get,
        )
        ranking_labels = {
            "available": "Available countries per year",
            "common": "Common countries",
        }
        ranking_mode = None
        if comparison_units in unit_labels:
            ranking_mode = st.selectbox(
                "Ranking sample",
                options=list(ranking_labels),
                index=None,
                format_func=ranking_labels.get,
                help="Applies when Unit is Euro and PPS.",
            )

        show_annual_change = st.checkbox("Show annual change (EUR)")
        show_period_change = st.checkbox("Show period change (EUR)")
        submitted = st.form_submit_button("Load data", type="primary")

    st.caption("Select Load data to apply your choices.")

if submitted and unit == comparison_units and ranking_mode is None:
    st.warning("Select a ranking sample for Euro and PPS.")
    st.stop()

if not submitted:
    st.info("Choose filters in the sidebar, then select Load data.")
    st.stop()

if (
    not countries
    or not ages
    or not sexes
    or indicator is None
    or unit is None
):
    st.warning(
        "Select at least one country, age group and sex category, "
        "an income measure and a unit."
    )
    st.stop()

if year_mode == "Range":
    if range_start is None or range_end is None:
        st.warning("Select both survey years for the range.")
        st.stop()
    if range_end < range_start:
        st.warning("The end year must not be earlier than the start year.")
        st.stop()
    selected_years = list(range(range_start, range_end + 1))
    api_years = None
    year_text = str(range_start)
    if range_start != range_end:
        year_text = f"{range_start}–{range_end}"
else:
    if not specific_years:
        st.warning("Select at least one survey year.")
        st.stop()
    selected_years = sorted(specific_years)
    api_years = tuple(selected_years)
    year_text = ", ".join(str(year) for year in selected_years)

has_period = len(selected_years) >= 2
annual_enabled = show_annual_change and unit == "EUR"
period_enabled = show_period_change and unit == "EUR" and has_period
if unit != "EUR" and (show_annual_change or show_period_change):
    st.warning("Select Euro to include income changes.")
elif show_period_change and not has_period:
    st.warning("Select at least two survey years for a period change.")

try:
    frame = load_income(
        tuple(countries), range_start, range_end, indicator, unit,
        tuple(ages), tuple(sexes), api_years, tuple(selected_years),
        annual_enabled, period_enabled,
    )
except (RuntimeError, ValueError) as exc:
    st.error(f"Could not load income data: {exc}")
    st.stop()

def render_income_source(frame):
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


if unit == comparison_units:
    try:
        pairs = build_eur_pps_pairs(frame, country_options)
        ranked = rank_eur_pps_pairs(
            pairs, mode=ranking_mode, survey_years=selected_years,
        )
    except ValueError as exc:
        st.error(f"Could not calculate the EUR–PPS rankings: {exc}")
        st.stop()

    age_text = ", ".join(AGE_LABELS[code] for code in ages)
    sex_text = ", ".join(SEX_LABELS[code] for code in sexes)
    st.subheader(f"{labels['statinfo'][indicator]} | EUR and PPS")
    st.caption(f"Applied survey years: {year_text} | Age: {age_text} | Sex: {sex_text}")
    st.caption(f"Ranking sample: {ranking_labels[ranking_mode]}")
    st.caption(
        "Rank change = EUR rank − PPS rank within a survey year. "
        "A positive value means a higher position in PPS. "
        "Ties share a rank, for example 1, 1, 3."
    )

    if ranking_mode == "available":
        membership = ranked.assign(in_sample=ranked["rank_EUR"].notna())
        country_series = ["freq", "age", "sex", "statinfo", "geo"]
        membership_counts = membership.groupby(country_series)["in_sample"].nunique()
        if membership_counts.gt(1).any():
            st.warning(
                "The set of ranked countries changes across the selected survey years. "
                "Differences in ranks over time can reflect changes in the sample."
            )

    if ranked["rank_EUR"].isna().all():
        st.warning("No countries meet the selected ranking sample rules.")

    ranked["time"] = ranked["time"].astype(int)
    ranked["geo_label"] = ranked["geo"].map(labels["geo"])
    ranked["age_group"] = ranked["age"].map(AGE_LABELS)
    ranked["sex_label"] = ranked["sex"].map(SEX_LABELS)
    ranked = ranked.sort_values(["time", "sex_label", "rank_EUR", "geo_label"])
    chart_year = selected_years[-1]
    in_chart = ranked["time"].eq(chart_year) & ranked["rank_EUR"].notna()
    chart_rows = ranked.loc[in_chart]

    if not chart_rows.empty:
        st.subheader(f"Country ranking for survey year {chart_year}")
        st.caption("Each panel has its own income scale. Diamonds mark Eurostat flags.")

        for sex in sexes:
            st.markdown(f"**{SEX_LABELS[sex]}**")
            sex_rows = chart_rows.loc[chart_rows["sex"].eq(sex)]
            if sex_rows.empty:
                st.info("No ranked countries for this sex category in the chart year.")
                continue

            panels = st.columns(2)
            for chart_unit, panel in zip(comparison_units, panels):
                rank_field = f"rank_{chart_unit}"
                value_field = f"value_{chart_unit}"
                flag_field = f"flag_{chart_unit}"

                plot_rows = sex_rows.sort_values([rank_field, "geo_label"]).copy()
                plot_rows["rank_label"] = (
                    plot_rows[rank_field].astype(str) + " · " + plot_rows["geo_label"]
                )
                plot_rows["flagged"] = plot_rows[flag_field].fillna("").ne("")

                base = alt.Chart(plot_rows).encode(
                    x=alt.X(
                        f"{value_field}:Q",
                        title=f"Income ({chart_unit})",
                        scale=alt.Scale(zero=True),
                    ),
                    y=alt.Y(
                        "rank_label:N",
                        title=None,
                        sort=plot_rows["rank_label"].tolist(),
                    ),
                    tooltip=[
                        alt.Tooltip("geo_label:N", title="Country"),
                        alt.Tooltip("time:Q", title="Survey year", format="d"),
                        alt.Tooltip(f"{rank_field}:Q", title="Rank", format="d"),
                        alt.Tooltip(
                            f"{value_field}:Q", title=f"Income ({chart_unit})", format=",.2f",
                        ),
                        alt.Tooltip("rank_sample_size:Q", title="Sample size", format="d"),
                        alt.Tooltip(f"{flag_field}:N", title="Eurostat flag"),
                    ],
                )

                bars = base.mark_bar(size=18)
                flagged = base.transform_filter(alt.datum.flagged).mark_point(
                    shape="diamond", filled=True, size=90, stroke="white", strokeWidth=1,
                )
                chart = (bars + flagged).properties(
                    title=f"{chart_unit} ranking",
                    height=max(145, 28 * len(plot_rows)),
                )
                panel.altair_chart(chart, width="stretch")

    elif ranked["rank_EUR"].notna().any():
        st.info(f"No countries are ranked for survey year {chart_year} in this sample.")

    rank_columns = {
        "time": st.column_config.NumberColumn("Survey year", format="%d"),
        "geo_label": "Country",
        "sex_label": "Sex",
        "age_group": "Age group",
        "value_EUR": st.column_config.NumberColumn("Income (EUR)", format="%.2f"),
        "rank_EUR": "Rank (EUR)",
        "value_PPS": st.column_config.NumberColumn("Income (PPS)", format="%.2f"),
        "rank_PPS": "Rank (PPS)",
        "rank_change": "Rank change",
        "rank_sample_size": "Sample size",
        "rank_status": st.column_config.TextColumn("Ranking status", width="large"),
        "coverage_EUR": "EUR coverage",
        "coverage_PPS": "PPS coverage",
        "flag_EUR": "EUR flag",
        "flag_PPS": "PPS flag",
    }
    st.dataframe(
        ranked[list(rank_columns)],
        column_config=rank_columns,
        hide_index=True,
        width="stretch",
    )
    render_income_source(frame)
    st.stop()


start_year = selected_years[0]
end_year = selected_years[-1]
auxiliary_years = frame.attrs.get("auxiliary_survey_years", [])

# Keep the full requested grid, including missing calculation inputs.
key = ["freq", "age", "sex", "statinfo", "unit", "geo", "time"]
display_year_codes = [str(year) for year in selected_years]
query_year_codes = [str(year) for year in sorted(selected_years + auxiliary_years)]
requested = pd.MultiIndex.from_product(
    [["A"], ages, sexes, [indicator], [unit], countries, query_year_codes],
    names=key,
)
observations = frame.set_index(key)[["value", "obs_flag"]]
table = observations.reindex(requested).reset_index()

table["coverage"] = "Available"
missing_value = table["value"].isna()
table.loc[missing_value, "coverage"] = "Missing value"
outside_cube = ~requested.isin(observations.index)
table.loc[outside_cube, "coverage"] = "Outside API cube"

if annual_enabled or period_enabled:
    calculation_table = table
    display_mask = calculation_table["time"].isin(display_year_codes)
    table = calculation_table.loc[display_mask].copy()

table["sex_label"] = table["sex"].map(SEX_LABELS)
sex_order = [SEX_LABELS[code] for code in sexes]
table["geo_label"] = table["geo"].map(labels["geo"])
table["age_group"] = table["age"].map(AGE_LABELS)
table["time"] = table["time"].astype(int)
table["age"] = pd.Categorical(table["age"], categories=list(AGE_LABELS), ordered=True)
table = table.sort_values(["geo_label", "age", "sex", "time"])

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
selected_age_labels = [AGE_LABELS[code] for code in ages]
st.caption(
    f"{selection} | Applied survey years: {year_text}"
    f" | Age: {', '.join(selected_age_labels)} | Sex: {', '.join(sex_order)}"
)

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
    # Track gaps and breaks within each country, age group and sex.
    series_key = ["geo", "age", "sex"]
    grouped = chart_data.groupby(series_key, sort=False, observed=True)
    year_steps = grouped["time"].diff()
    gap_before = year_steps.gt(1)
    flag_break = chart_data["flag_text"].str.contains("b", regex=False)
    chart_data["break_before"] = flag_break | gap_before
    chart_data["segment"] = grouped["break_before"].cumsum()

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
            alt.Tooltip("sex_label:N", title="Sex"),
            alt.Tooltip("time:O", title="Survey year"),
            alt.Tooltip("value:Q", title=f"Income ({unit})", format=",.2f"),
            alt.Tooltip("flag_text:N", title="Eurostat flag"),
        ],
    )

    if start_year == end_year:
        # Age bars follow age order; country bars follow descending income.
        bar_order = (
            series_order if age_view
            else alt.SortField(field="value", order="descending")
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
        x = alt.X(
            "time:Q",
            title="Survey year",
            axis=alt.Axis(format="d", values=selected_years, labelAngle=0),
            scale=alt.Scale(domain=[start_year, end_year], zero=False, nice=False),
        )
        y = alt.Y("value:Q", title=f"Income ({unit})", scale=alt.Scale(zero=True))

        lines = base.mark_line(
            strokeWidth=2, invalid="break-paths-show-domains"
        ).encode(
            x=x, y=y,
            detail=["geo:N", "age:N", "sex:N", "segment:N"],
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
    chart = chart.properties(height=chart_height)
    if len(sexes) > 1:
        chart = chart.facet(
            row=alt.Row("sex_label:N", sort=sex_order, title="Sex")
        )
        if start_year == end_year and not age_view:
            chart = chart.resolve_scale(y="independent")
    st.altair_chart(chart, width="stretch")
    st.caption("Diamonds mark flagged observations.")

    if start_year != end_year:
        st.caption("Lines break at missing values, gaps in the selection and b flags.")

if unit != "NAC":
    st.subheader(f"Summary for survey year {end_year}")
    for sex in sexes:
        st.markdown(f"**{SEX_LABELS[sex]}**")
        matches_sex = table["sex"].eq(sex)
        sex_table = table.loc[matches_sex]
        summary = build_year_summary(
            sex_table,
            end_year,
            unit,
            labels["statinfo"][indicator],
            "age groups" if age_view else "countries",
        )
        for line in summary:
            st.write(line)
display_columns = [
    "geo_label", "geo", "age_group", "sex_label", "time", "value",
    "coverage", "obs_flag",
]

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
        "sex_label": "Sex",
        "coverage": "Coverage"
    },
)

def render_change_table(changes, country_labels, start_label, end_label):
    display = changes.copy()
    display["geo_label"] = display["geo"].map(country_labels)
    display["age_group"] = display["age"].map(AGE_LABELS)
    display["sex_label"] = display["sex"].map(SEX_LABELS)
    display["coverage_start"] = display["coverage_start"].fillna(
        "Outside supported period"
    )
    columns = {
        "geo_label": "Country",
        "age_group": "Age group",
        "sex_label": "Sex",
        "start_year": st.column_config.NumberColumn(f"{start_label} survey year", format="%d"),
        "end_year": st.column_config.NumberColumn(f"{end_label} survey year", format="%d"),
        "value_start": st.column_config.NumberColumn(f"{start_label} income (EUR)", format="%.2f"),
        "value_end": st.column_config.NumberColumn(f"{end_label} income (EUR)", format="%.2f"),
        "change_eur": st.column_config.NumberColumn("Change (EUR)", format="%.2f"),
        "change_pct": st.column_config.NumberColumn("Change (%)", format="%.2f"),
        "coverage_start": f"{start_label} coverage",
        "coverage_end": f"{end_label} coverage",
        "obs_flag_start": f"{start_label} flag",
        "obs_flag_end": f"{end_label} flag",
        "blocked_by_flag": "Blocked by b/d flag",
    }
    st.dataframe(
        display[list(columns)], column_config=columns, hide_index=True, width="stretch"
    )


if annual_enabled:
    annual_parts = [
        compare_income_years(calculation_table, year - 1, year)
        for year in selected_years
    ]
    annual = pd.concat(annual_parts, ignore_index=True)
    annual_aux = frame.attrs["annual_auxiliary_survey_years"]
    annual_text = ", ".join(str(year) for year in annual_aux) or "None"
    st.subheader("Annual nominal income change (EUR)")
    st.caption(f"Auxiliary survey years requested: {annual_text}.")
    st.caption(
        "Each selected survey year is compared with the previous survey year. "
        "A percentage requires a positive previous value."
    )
    render_change_table(annual, labels["geo"], "Previous", "Selected")

if period_enabled:
    period = compare_income_years(calculation_table, start_year, end_year)
    period_aux = frame.attrs["period_auxiliary_survey_years"]
    period_text = ", ".join(str(year) for year in period_aux) or "None"
    st.subheader("Total nominal income change (EUR)")
    st.caption(f"Selected period {start_year}–{end_year}.")
    st.caption(f"Auxiliary survey years requested for the period: {period_text}.")
    st.caption(
        "The percentage uses the first survey year's income as the base. "
        "A break after the first year (b) or a different definition (d) blocks the comparison."
    )
    render_change_table(period, labels["geo"], "First", "Last")

    review_years = calculation_table["time"].astype(int)
    within_period = review_years.between(start_year, end_year)
    flagged = calculation_table["obs_flag"].fillna("").ne("")
    missing = calculation_table["value"].isna()
    review_mask = within_period & (flagged | missing)
    review = calculation_table.loc[
        review_mask, ["geo", "age", "sex", "time", "coverage", "obs_flag"]
    ]
    if not review.empty:
        with st.expander("Period flags and missing observations"):
            st.dataframe(
                review,
                column_config={
                    "geo": "Country code", "age": "Age code", "sex": "Sex code",
                    "time": "Survey year", "coverage": "Coverage", "obs_flag": "Flag",
                },
                hide_index=True,
                width="stretch",
            )

render_income_source(frame)