import altair as alt
import pandas as pd
import streamlit as st

from real_income import calculate_real_change, fetch_greek_real_income


DETAIL_COLUMNS = [
    "survey_year", "income_year", "nominal_income",
    "hicp", "income_flag", "hicp_flag",
]


@st.cache_data(ttl=3600, max_entries=128, show_spinner="Loading income and HICP...")
def load_real_income(start_year, end_year, indicator, age):
    return fetch_greek_real_income(start_year, end_year, indicator, age)


def build_index_chart(frame):
    """Rebase income, HICP and HICP-adjusted income to the same starting point."""
    indexed = frame.sort_values("income_year").copy()
    first = indexed.iloc[0]

    indexed["Nominal income"] = (
        indexed["nominal_income"] / first["nominal_income"] * 100
    )
    indexed["HICP"] = indexed["hicp"] / first["hicp"] * 100
    indexed["HICP-adjusted income"] = (
        indexed["Nominal income"] / indexed["HICP"] * 100
    )

    series = ["Nominal income", "HICP", "HICP-adjusted income"]
    plotted = indexed.melt(
        id_vars=["income_year", "income_flag", "hicp_flag"],
        value_vars=series,
        var_name="series",
        value_name="index",
    )

    return alt.Chart(plotted).mark_line(point=True).encode(
        x=alt.X("income_year:O", title="Income year", axis=alt.Axis(labelAngle=0)),
        y=alt.Y(
            "index:Q",
            title=f"Index ({int(first['income_year'])} = 100)",
            scale=alt.Scale(zero=False),
        ),
        color=alt.Color(
            "series:N",
            title=None,
            sort=series,
            legend=alt.Legend(orient="bottom"),
        ),
        tooltip=[
            alt.Tooltip("income_year:O", title="Income year"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("index:Q", title="Index", format=".2f"),
            alt.Tooltip("income_flag:N", title="Income flag"),
            alt.Tooltip("hicp_flag:N", title="HICP flag"),
        ],
    ).properties(height=420)


def render_real_income_view(years, indicator_labels, age_labels):
    default_period = (
        (2020, 2024)
        if {2020, 2024}.issubset(years)
        else (years[0], years[-1])
    )
    indicators = sorted(indicator_labels)

    with st.sidebar:
        st.header("Filters")

        with st.form("real_income_filters"):
            st.caption("Greece | EUR | Total sex")
            start_year, end_year = st.select_slider(
                "Survey years", options=years, value=default_period
            )
            indicator = st.selectbox(
                "Income measure",
                options=indicators,
                index=indicators.index("MED_EI"),
                format_func=indicator_labels.get,
            )
            age = st.selectbox(
                "Age group",
                options=list(age_labels),
                format_func=age_labels.get,
            )
            submitted = st.form_submit_button("Load data", type="primary")

    if not submitted:
        st.info("Choose a period, income measure and age group, then select Load data.")
        return

    if start_year == end_year:
        st.warning("Select at least two different survey years.")
        return

    try:
        frame = load_real_income(start_year, end_year, indicator, age)
    except (RuntimeError, ValueError) as exc:
        st.error(f"Could not load the comparison: {exc}")
        return

    st.subheader("Income change after inflation | Greece")
    st.caption(
        f"{indicator_labels[indicator]} | {age_labels[age]} | EUR | "
        f"Survey years {start_year}-{end_year} | "
        f"Income years {start_year - 1}-{end_year - 1}"
    )

    try:
        result = calculate_real_change(frame)
    except ValueError as exc:
        st.warning(f"Comparison unavailable: {exc}")
        result = None

    if result is not None:
        nominal = result["nominal_change_pct"]
        prices = result["hicp_change_pct"]
        real = result["real_change_pct"]

        columns = st.columns(3)
        columns[0].metric("Nominal income change", f"{nominal:+.2f}%", border=True)
        columns[1].metric("HICP change", f"{prices:+.2f}%", border=True)
        columns[2].metric("HICP-adjusted income change", f"{real:+.2f}%", border=True)
        st.caption("Cumulative changes over the selected income years.")

        flagged = [
            f"{name}: {', '.join(codes)}"
            for name, codes in result["flags"].items() if codes
        ]
        if flagged:
            st.warning("Flagged observations included. " + "; ".join(flagged))

        st.altair_chart(build_index_chart(frame), width="stretch", height=420)
        st.caption(
            f"Each series is rebased to 100 in {result['start_income_year']}. "
            "The vertical axis shows indices."
        )
        st.write(
            f"From income year {result['start_income_year']} to "
            f"{result['end_income_year']}, {indicator_labels[indicator].lower()} "
            f"changed by {nominal:+.2f}% in nominal EUR and by {real:+.2f}% "
            "after adjustment with HICP."
        )

    with st.expander("Data and flags"):
        st.dataframe(
            frame[DETAIL_COLUMNS],
            hide_index=True,
            width="stretch",
            column_config={
                "survey_year": st.column_config.NumberColumn(
                    "Survey year", format="%d"
                ),
                "income_year": st.column_config.NumberColumn(
                    "Income / HICP year", format="%d"
                ),
                "nominal_income": st.column_config.NumberColumn(
                    "Income (EUR)", format="%.2f"
                ),
                "hicp": st.column_config.NumberColumn(
                    "HICP annual average", format="%.2f"
                ),
                "income_flag": "Income flag",
                "hicp_flag": "HICP flag",
            },
        )

    with st.expander("Sources and calculation"):
        st.write(
            "HICP-adjusted change (%) = "
            "((income_end / income_start) / (HICP_end / HICP_start) - 1) * 100"
        )
        st.caption(
            "Price adjustment uses Greece's national annual all-items HICP "
            "for every age group."
        )
        for name, metadata in frame.attrs["sources"].items():
            st.markdown(f"**{name.upper()}**")
            st.write("Retrieved at UTC:", metadata["retrieved_at_utc"])
            st.write("Eurostat updated:", metadata["eurostat_metadata"].get("updated"))
            st.markdown(f"[Open {name} API response]({metadata['request_url']})")