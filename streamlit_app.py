import json
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from functools import partial
from income_report import build_ranking_pdf
from income_changes import compare_income_years
from income_comparison import build_eur_pps_pairs, rank_eur_pps_pairs
from income_share import build_ranking_link, read_ranking_link
from saved_rankings import render_save_ranking, render_saved_rankings
from income_country_map import COUNTRY_PICKER_KEY, render_country_picker
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
    selected_years, include_annual, include_period, _load_id=None,
):
    if include_annual or include_period:
        frame = fetch_income_for_changes(
            countries, selected_years, indicator=indicator, unit=unit,
            ages=ages, sexes=sexes, include_previous_years=include_annual,
            include_period_years=include_period,
        )
    else:
        frame = fetch_income(
            countries, start_year, end_year, indicator, unit,
            ages=ages, sexes=sexes, survey_years=survey_years,
        )

    # Keep the ID of the call that fetched this response.
    frame.attrs["streamlit_load_id"] = _load_id
    return frame


try:
    shared_ranking = read_ranking_link(st.query_params)
except ValueError as exc:
    st.warning(f"Could not restore the ranking link. {exc}")
    shared_ranking = {}

# Keep the view selector outside the form so its controls update immediately.
view = st.sidebar.radio(
    "Analysis",
    [
        "Countries",
        "Age groups",
        "Real change (Greece)",
        "Housing",
        "Urbanisation",
        "Saved rankings",        
    ],
    index=0 if shared_ranking else None,
)

# Wait for an explicit selection before loading analysis options.
if view is None:
    st.title("EURO_DATA | Income explorer")
    st.info("Choose an analysis from the sidebar to begin.")
    st.stop()

if view == "Saved rankings":
    render_saved_rankings()
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

ranking_defaults = {}
if view == "Countries" and shared_ranking:
    shared_years = shared_ranking["survey_years"]
    if shared_ranking["year_selection"] == "Range":
        shared_years = [shared_years[0], shared_years[-1]]

    filters_available = (
        set(shared_ranking["countries"]).issubset(country_options)
        and shared_ranking["ages"][0] in AGE_LABELS
        and set(shared_ranking["sexes"]).issubset(SEX_LABELS)
        and set(shared_years).issubset(years)
        and shared_ranking["statinfo"] in indicators
        and {"EUR", "PPS"}.issubset(labels["unit"])
    )
    if filters_available:
        ranking_defaults = shared_ranking
    else:
        st.warning("This ranking link contains unavailable filters. Select filters manually.")

map_area = st.container() if view == "Countries" else None

with st.sidebar:
    st.header("Filters")
    year_modes = ["Range", "Specific years"]
    initial_year_mode = ranking_defaults.get("year_selection", "Range")
    year_mode = st.radio(
        "Year selection", year_modes,
        index=year_modes.index(initial_year_mode),
        horizontal=True,
    )
    linked_years = []
    if year_mode == initial_year_mode:
        linked_years = ranking_defaults.get("survey_years", [])

    if view == "Countries":
        render_country_picker(
            map_area, country_options, labels["geo"], ranking_defaults.get("countries", []),
        )

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
            countries = list(st.session_state[COUNTRY_PICKER_KEY])
            selected_age = st.selectbox(
                "Age group",
                options=list(AGE_LABELS),
                index=list(AGE_LABELS).index(ranking_defaults["ages"][0]) if ranking_defaults else None,
                format_func=AGE_LABELS.get,
            )
            ages = [selected_age] if selected_age is not None else []


        sexes = st.multiselect(
            "Sex",
            options=list(SEX_LABELS),
            default=ranking_defaults.get("sexes", []),
            format_func=SEX_LABELS.get,
        )

        if year_mode == "Range":
            range_start = st.selectbox(
                "Start survey year", options=years, index=years.index(linked_years[0]) if linked_years else None
            )
            range_end = st.selectbox(
                "End survey year", options=years, index=years.index(linked_years[-1]) if linked_years else None
            )
            specific_years = []
        else:
            range_start = None
            range_end = None
            specific_years = st.multiselect("Survey years", options=years, default=linked_years)
        indicator = st.selectbox(
            "Income measure",
            options=indicators,
            index=indicators.index(ranking_defaults["statinfo"]) if ranking_defaults else None,
            format_func=labels["statinfo"].get,
        )
        comparison_units = ("EUR", "PPS")
        unit_labels = dict(sorted(labels["unit"].items()))
        if not age_view and set(comparison_units).issubset(unit_labels):
            unit_labels[comparison_units] = "Euro and PPS"

        unit = st.selectbox(
            "Unit",
            options=list(unit_labels),
        	index=list(unit_labels).index(comparison_units) if ranking_defaults else None,
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
                index=list(ranking_labels).index(ranking_defaults["ranking_sample"]) if ranking_defaults else None,
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

load_id = uuid4().hex
try:
    frame = load_income(
        tuple(countries), range_start, range_end, indicator, unit,
        tuple(ages), tuple(sexes), api_years, tuple(selected_years),
        annual_enabled, period_enabled, _load_id=load_id,
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
    year_rows = ranked.loc[ranked["time"].eq(chart_year)]
    chart_rows = year_rows.loc[year_rows["rank_EUR"].notna()]
    report_sections = {}

    st.subheader(f"Ranking summary for survey year {chart_year}")
    selected_count = len(countries)

    for sex in sexes:
        summary_mask = chart_rows["sex"].eq(sex)
        summary_rows = chart_rows.loc[summary_mask]
        ranked_count = summary_rows["geo"].nunique()
        sentences = [f"Coverage is {ranked_count} of {selected_count} selected countries."]

        if not summary_rows.empty:
            rank_changes = summary_rows["rank_change"]
            rise = max(0, int(rank_changes.max()))
            fall = min(0, int(rank_changes.min()))

            if rise == 0 and fall == 0:
                sentences.append("Every ranked country has the same position in EUR and PPS.")

            for change, description in ((rise, "Largest rise"), (fall, "Largest fall")):
                if change == 0:
                    continue
                tied_mask = rank_changes.eq(change)
                names = summary_rows.loc[tied_mask, "geo_label"]
                country_text = ", ".join(sorted(names))
                places = abs(change)
                unit_text = "place" if places == 1 else "places"
                sentences.append(
                    f"{description} from EUR to PPS is {places} {unit_text} for {country_text}."
                )

            flags = summary_rows[["flag_EUR", "flag_PPS"]].fillna("")
            flagged_count = int(flags.ne("").any(axis=1).sum())
            if flagged_count:
                sentences.append(
                    f"Eurostat flags are present for {flagged_count} of the ranked countries."
                )

        if ranked_count < selected_count:
            sentences.append("See Ranking status in the table for exclusions.")
            
        report_sections[sex] = {
            "label": SEX_LABELS[sex],
            "summary": " ".join(sentences),
            "rows": year_rows.loc[year_rows["sex"].eq(sex)],
            "chart": None
        }

        st.markdown(f"**{SEX_LABELS[sex]}**")
        st.write(" ".join(sentences))

    if not chart_rows.empty:
        st.subheader(f"Country ranking for survey year {chart_year}")
        st.caption("Each panel has its own income scale. Diamonds mark Eurostat flags.")

        for sex in sexes:
            st.markdown(f"**{SEX_LABELS[sex]}**")
            sex_rows = chart_rows.loc[chart_rows["sex"].eq(sex)]
            if sex_rows.empty:
                st.info("No ranked countries for this sex category in the chart year.")
                continue

            export_panels = []
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
                        axis=alt.Axis(labelFontSize=14, labelOverlap=False),
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
                    height=alt.Step(38),
                )
                screen_chart = chart.properties(
                    autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
                )
                panel.altair_chart(screen_chart, width="stretch")
                export_panels.append(chart.properties(width=440))

            export_title = alt.TitleParams(
                text=f"{labels['statinfo'][indicator]} | Survey year {chart_year}",
                subtitle=[
                    f"{SEX_LABELS[sex]} | Age {age_text} | {ranking_labels[ranking_mode]}",
                    f"{sex_rows['geo'].nunique()} of {selected_count} selected countries ranked",
                    f"Applied survey years {year_text}",
                    "Income scales are independent. Diamonds mark Eurostat flags.",
                    f"Eurostat (ilc_di03) | Retrieved {frame.attrs['retrieved_at_utc']}",
                ],
                anchor="start",
                fontSize=20,
                subtitleFontSize=13,
                offset=18,
            )
            export_chart = (
                alt.hconcat(*export_panels, spacing=32)
                .resolve_scale(x="independent", y="independent")
                .properties(title=export_title, padding=16, background="white")
                .configure_axis(labelFontSize=12, titleFontSize=13)
                .configure_axisX(tickCount=6)
            )
            
            report_sections[sex]["chart"] = export_chart            

            def render_png(chart=export_chart):
                output = BytesIO()
                chart.save(output, format="png", scale_factor=2)
                return output.getvalue()

            st.download_button(
                f"Download rankings (PNG) · {SEX_LABELS[sex]}",
                data=render_png,
                file_name=f"eur_pps_rankings_{chart_year}_{indicator}_{ages[0]}_{sex}_{ranking_mode}.png",
                mime="image/png",
                on_click="ignore",
            )

    elif ranked["rank_EUR"].notna().any():
        st.info(f"No countries are ranked for survey year {chart_year} in this sample.")

    has_rank = ranked["rank_EUR"].notna()
    if has_period and has_rank.any():
        history = ranked.loc[has_rank].sort_values(["geo", "time"])
        country_domain = [labels["geo"][code] for code in sorted(country_options)]
        country_colors = [
            f"hsl({(25 + index * 137.5) % 360:g}, 75%, 55%)"
            for index in range(len(country_domain))
        ]
        country_scale = alt.Scale(domain=country_domain, range=country_colors)
        history_x = alt.X(
            "time:Q",
            title="Survey year",
            scale=alt.Scale(
                domain=[selected_years[0] - 0.35, selected_years[-1] + 0.35],
                zero=False, nice=False,
            ),
            axis=alt.Axis(
                values=selected_years, format="d", labelAngle=0, labelOverlap=True,
            ),
        )
        series_key = ["geo", "freq", "age", "statinfo"]

        with st.expander("Rankings over time"):
            st.caption(
                "Rank 1 is at the top. Lines connect consecutive ranked years "
                "and break at gaps or b flags. Diamonds mark Eurostat flags. "
                "Select a country in the legend to highlight it."
            )
            for sex in sexes:
                st.markdown(f"**{SEX_LABELS[sex]}**")
                sex_history = history.loc[history["sex"].eq(sex)]
                if sex_history.empty:
                    st.info("No ranked observations for this sex category.")
                    continue

                first_year = selected_years[0]
                first_mask = sex_history["time"].eq(first_year)
                last_mask = sex_history["time"].eq(chart_year)
                first_rows = sex_history.loc[first_mask].set_index(series_key)
                last_rows = sex_history.loc[last_mask].set_index(series_key)
                paired_keys = first_rows.index.intersection(last_rows.index)

                st.markdown(f"**Rank movement from survey year {first_year} to {chart_year}**")
                st.write(
                    f"Ranked sample sizes are {len(first_rows)} in {first_year} "
                    f"and {len(last_rows)} in {chart_year}. "
                    f"{len(paired_keys)} of {selected_count} selected countries have ranks in both years."
                )
                if len(paired_keys) < max(len(first_rows), len(last_rows)):
                    st.caption("The endpoint samples differ. Rank movements can reflect sample membership.")

                for year, endpoint_rows in ((first_year, first_rows), (chart_year, last_rows)):
                    ranked_codes = set(endpoint_rows.index.get_level_values("geo"))
                    unranked_codes = set(countries) - ranked_codes
                    if unranked_codes:
                        names = ", ".join(sorted(labels["geo"][code] for code in unranked_codes))
                        st.caption(f"Unranked in {year} · {names}.")

                if paired_keys.empty:
                    st.caption("Rank movement requires a position in both endpoint years.")
                else:
                    st.caption(
                        "Flag checks cover the selected survey years. A break after the first year (b) "
                        "or a different definition (d) excludes the country from that unit's movement summary."
                    )
                    period_mask = ranked["sex"].eq(sex) & ranked["time"].isin(selected_years)
                    period_rows = ranked.loc[period_mask].set_index(series_key)
                    after_first = period_rows["time"].gt(first_year)

                    for movement_unit in comparison_units:
                        flags = period_rows[f"flag_{movement_unit}"].fillna("")
                        breaks = flags.str.contains("b", regex=False) & after_first
                        differing = flags.str.contains("d", regex=False)
                        blocked_keys = paired_keys.intersection(period_rows.index[breaks | differing])
                        comparable_keys = paired_keys.difference(blocked_keys)
                        notes = [f"Comparable coverage is {len(comparable_keys)} of {len(paired_keys)} endpoint pairs."]

                        if len(blocked_keys):
                            names = ", ".join(sorted(first_rows.loc[blocked_keys, "geo_label"]))
                            notes.append(f"Excluded by b/d flags · {names}.")

                        if len(comparable_keys):
                            rank_field = f"rank_{movement_unit}"
                            first_ranks = first_rows.loc[comparable_keys, rank_field]
                            last_ranks = last_rows.loc[comparable_keys, rank_field]
                            movement = first_ranks - last_ranks
                            changed_count = int(movement.ne(0).sum())
                            notes.append(f"{changed_count} changed position.")

                            if changed_count:
                                distances = movement.abs()
                                largest_keys = distances.index[distances.eq(distances.max())]
                                names = first_rows.loc[largest_keys, "geo_label"]
                                transitions = [
                                    f"{name} ({int(start_rank)} → {int(end_rank)})"
                                    for name, start_rank, end_rank in zip(
                                        names, first_ranks.loc[largest_keys], last_ranks.loc[largest_keys],
                                    )
                                ]
                                notes.append(f"Largest rank moves · {', '.join(sorted(transitions))}.")

                        st.markdown(f"**{movement_unit}** " + " ".join(notes))

                max_rank = int(sex_history["rank_sample_size"].max())
                rank_scale = alt.Scale(
                    domain=[0.5, max_rank + 0.5], reverse=True, zero=False, nice=False,
                )
                rank_axis = alt.Axis(values=list(range(1, max_rank + 1)), format="d")
                legend_countries = sorted(sex_history["geo_label"].unique())
                panels = st.columns(2)

                for chart_unit, panel in zip(comparison_units, panels):
                    rank_field = f"rank_{chart_unit}"
                    flag_field = f"flag_{chart_unit}"
                    plot_rows = sex_history.copy()
                    flags = plot_rows[flag_field].fillna("")
                    plot_rows["flagged"] = flags.ne("")
                    grouped = plot_rows.groupby(series_key, sort=False, observed=True)
                    gap_before = grouped["time"].diff().gt(1)
                    plot_rows["break_before"] = gap_before | flags.str.contains("b", regex=False)
                    plot_rows["segment"] = grouped["break_before"].cumsum()

                    highlight = alt.selection_point(fields=["geo_label"], bind="legend")
                    base = alt.Chart(plot_rows).encode(
                        x=history_x,
                        y=alt.Y(
                            f"{rank_field}:Q", title="Rank", scale=rank_scale, axis=rank_axis,
                        ),
                        color=alt.Color(
                            "geo_label:N",
                            title="Country",
                            scale=country_scale,
                            legend=alt.Legend(
                                values=legend_countries, orient="bottom", columns=2,
                            ),
                        ),
                        opacity=alt.condition(highlight, alt.value(1), alt.value(0.18)),
                        tooltip=[
                            alt.Tooltip("geo_label:N", title="Country"),
                            alt.Tooltip("time:Q", title="Survey year", format="d"),
                            alt.Tooltip(f"{rank_field}:Q", title="Rank", format="d"),
                            alt.Tooltip("rank_sample_size:Q", title="Sample size", format="d"),
                            alt.Tooltip(f"{flag_field}:N", title="Eurostat flag"),
                        ],
                    )
                    lines = base.mark_line(strokeWidth=2).encode(
                        detail=[f"{field}:N" for field in series_key] + ["segment:N"],
                        order=alt.Order("time:Q"),
                    )
                    points = base.mark_point(filled=True, size=85).encode(
                        shape=alt.condition(
                            alt.datum.flagged, alt.value("diamond"), alt.value("circle"),
                        ),
                    )
                    chart = (lines + points).add_params(highlight).properties(
                        title=f"{chart_unit} ranks over time",
                        height=max(240, 18 * max_rank),
                        autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
                    )
                    panel.altair_chart(chart, width="stretch")

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
    key_columns = ["freq", "geo", "time", "age", "sex", "statinfo"]
    export_columns = key_columns + [
        column for column in rank_columns if column not in key_columns
    ]
    csv_text = ranked[export_columns].to_csv(index=False)
    delivery = "live" if frame.attrs.get("streamlit_load_id") == load_id else "cache"

    metadata = {
        "schema_version": 1,
        "analysis": "EUR and PPS country rankings",
        "filters": {
            "countries": list(countries),
            "ages": list(ages),
            "sexes": list(sexes),
            "year_selection": year_mode,
            "survey_years": [int(year) for year in selected_years],
            "statinfo": indicator,
            "statinfo_label": labels["statinfo"][indicator],
            "units": list(comparison_units),
            "ranking_sample": ranking_mode,
            "ranking_sample_label": ranking_labels[ranking_mode],
        },
        "csv": {
            "file": "eur_pps_rankings.csv",
            "key_columns": key_columns,
            "ties": "Competition ranking (1, 1, 3).",
            "rank_change": "Rank in EUR minus rank in PPS within the same survey year.",
        },
        "source": {
            "provider": "Eurostat",
            "dataset": "ilc_di03",
            "request_url": frame.attrs["request_url"],
            "retrieved_at_utc": frame.attrs["retrieved_at_utc"],
            "updated_at": frame.attrs["eurostat_metadata"].get("updated"),
            "delivery": delivery,
        },
    }

    export_zip = BytesIO()
    with ZipFile(export_zip, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("eur_pps_rankings.csv", csv_text.encode("utf-8-sig"))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))

    year_tag = str(selected_years[0])
    if has_period:
        year_tag = f"{year_tag}_{selected_years[-1]}"
    st.download_button(
        "Download CSV and metadata (ZIP)",
        data=export_zip.getvalue(),
        file_name=f"eur_pps_rankings_{ranking_mode}_{year_tag}.zip",
        mime="application/zip",
        on_click="ignore",
    )
    export_data = ranked[export_columns]
    filter_rows = []
    for name, value in metadata["filters"].items():
        display_value = ", ".join(map(str, value)) if isinstance(value, list) else value
        filter_rows.append((name, display_value))

    source_details = {
        **metadata["source"],
        "analysis": metadata["analysis"],
        "schema_version": metadata["schema_version"],
        "ties": metadata["csv"]["ties"],
        "rank_change": metadata["csv"]["rank_change"],
    }
    coverage_columns = key_columns + [
        "geo_label", "sex_label", "age_group", "rank_sample_size", "rank_status",
        "coverage_EUR", "coverage_PPS", "flag_EUR", "flag_PPS",
    ]
    sheets = {
        "Data": export_data,
        "Filters": pd.DataFrame(filter_rows, columns=["Filter", "Applied value"]),
        "Sources": pd.DataFrame(source_details.items(), columns=["Field", "Value"]),
        "Coverage": export_data[coverage_columns],
    }

    excel_file = BytesIO()
    excel_options = {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
    }
    with pd.ExcelWriter(
        excel_file, engine="xlsxwriter", engine_kwargs={"options": excel_options},
    ) as writer:
        wrap_text = writer.book.add_format({"text_wrap": True})
        for sheet_name, sheet_data in sheets.items():
            sheet_data.to_excel(
                writer, sheet_name=sheet_name, index=False, freeze_panes=(1, 0),
            )
            worksheet = writer.sheets[sheet_name]
            worksheet.autofilter(0, 0, len(sheet_data), len(sheet_data.columns) - 1)
            for column_index, column in enumerate(sheet_data.columns):
                longest_value = max(
                    (len(str(value)) for value in sheet_data[column].dropna()), default=0,
                )
                desired_width = max(10, max(len(column), longest_value) + 4)
                cell_format = wrap_text if desired_width > 70 else None
                worksheet.set_column(
                    column_index, column_index, min(desired_width, 70), cell_format,
                )

    st.download_button(
        "Download Excel (XLSX)",
        data=excel_file.getvalue(),
        file_name=f"eur_pps_rankings_{ranking_mode}_{year_tag}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        on_click="ignore",
    )
    country_names = [labels["geo"][code] for code in countries]
    render_pdf = partial(
        build_ranking_pdf, metadata, country_names, age_text, list(report_sections.values()),
    )
    st.download_button(
        "Download ranking report (PDF)",
        data=render_pdf,
        file_name=f"eur_pps_report_{ranking_mode}_{year_tag}.pdf",
        mime="application/pdf",
        on_click="ignore",
    )
    render_save_ranking({
        "id": load_id,
        "metadata": metadata,
        "data": export_data,
        "country_names": country_names,
        "age_text": age_text,
        "sections": list(report_sections.values()),
    })
    
    app_url = st.context.url
    if app_url:
        share_url = build_ranking_link(app_url, metadata["filters"])
        with st.expander("Share ranking link"):
            st.caption("This link restores the applied filters. Select Load data to retrieve the ranking.")
            st.code(share_url, language=None, wrap_lines=True)

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