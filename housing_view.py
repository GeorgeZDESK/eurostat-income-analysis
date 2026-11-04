import altair as alt
import pandas as pd
import streamlit as st

from eurostat_api import fetch_housing_catalogue, fetch_housing_overburden


POPULATION_LABELS = {
    "TOTAL": "Total population",
    "B_60": "Below 60% of national median income",
    "A_60": "Above 60% of national median income",
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_housing_catalogue():
    return fetch_housing_catalogue()


@st.cache_data(ttl=3600, show_spinner=False)
def load_housing_data(countries, start_year, end_year, population):
    return fetch_housing_overburden(
        list(countries),
        start_year,
        end_year,
        poverty_status=population,
    )


def show_housing_chart(table, single_year):
    country_order = sorted(table["country"].unique())

    color = alt.Color(
        "country:N",
        title="Country",
        scale=alt.Scale(domain=country_order),
        legend=alt.Legend(orient="bottom"),
    )
    tooltip = [
        alt.Tooltip("country:N", title="Country"),
        alt.Tooltip("year:O", title="Year"),
        alt.Tooltip(
            "value:Q",
            title="Housing overburden (%)",
            format=".1f",
        ),
        alt.Tooltip("flag:N", title="Eurostat flag"),
    ]
    base = alt.Chart(table).encode(color=color, tooltip=tooltip)

    if single_year:
        order = table.sort_values(
            "value", ascending=False
        )["country"].tolist()

        bars = base.mark_bar().encode(
            x=alt.X(
                "value:Q",
                title="Selected population (%)",
                scale=alt.Scale(zero=True),
            ),
            y=alt.Y(
                "country:N",
                title=None,
                sort=order,
                axis=alt.Axis(labelOverlap=False),
            ),
        )
        markers = bars.transform_filter(
            "isValid(datum.value) && datum.flag != ''"
        ).mark_point(
            shape="diamond",
            filled=True,
            size=110,
            stroke="white",
            strokeWidth=1,
        )
        chart = bars + markers
        height = max(360, 36 * len(country_order) + 100)

    else:
        # Break flags start new segments; keep missing rows to show gaps.
        plot = table.copy()
        breaks = plot["flag"].str.contains("b", regex=False)
        segments = breaks.groupby(plot["geo"]).cumsum()
        plot["segment"] = plot["geo"] + "_" + segments.astype(str)

        base = alt.Chart(plot).encode(color=color, tooltip=tooltip)
        position = base.encode(
            x=alt.X(
                "year:O",
                title="Year",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "value:Q",
                title="Selected population (%)",
                scale=alt.Scale(zero=True),
            ),
        )
        lines = position.mark_line(
            invalid="break-paths-show-domains"
        ).encode(
            detail="segment:N",
            order="year:Q",
        )
        points = position.transform_filter(
            "isValid(datum.value)"
        ).mark_point(
            filled=True,
            size=65,
            opacity=1,
        ).encode(
            shape=alt.condition(
                alt.datum.flag != "",
                alt.value("diamond"),
                alt.value("circle"),
            )
        )
        chart = lines + points
        height = 360

    st.altair_chart(
        chart.properties(height=height),
        width="stretch",
    )

    note = "Diamonds mark flagged observations."
    if not single_year:
        note += " Lines stop at missing values and restart at b flags."
    st.caption(note)


def show_housing_summary(table, year):
    st.subheader(f"Summary for year {year}")

    latest = table.loc[table["year"].eq(year)]
    available = latest.dropna(subset=["value"])

    st.write(
        f"{len(available)} of {len(latest)} selected countries have data."
    )

    missing = latest.loc[
        latest["value"].isna(), "country"
    ].tolist()
    if missing:
        st.caption("No published value: " + ", ".join(missing))

    if available.empty:
        st.info(
            "No published values for this year. "
            "No earlier year is substituted."
        )
        return

    if available["flag"].ne("").any():
        st.caption("Some values in this summary carry Eurostat flags.")

    highest = float(available["value"].max())
    lowest = float(available["value"].min())

    if highest == lowest:
        countries = ", ".join(available["country"])
        st.write(
            f"{countries}: {highest:.1f}% of the selected population."
        )
        return

    top = ", ".join(
        available.loc[available["value"].eq(highest), "country"]
    )
    bottom = ", ".join(
        available.loc[available["value"].eq(lowest), "country"]
    )

    st.write(f"Highest: {top} ({highest:.1f}%).")
    st.write(f"Lowest: {bottom} ({lowest:.1f}%).")

    # Differences between rates are expressed in percentage points.
    st.write(
        f"Difference: {highest - lowest:.1f} percentage points."
    )


def render_housing_view():
    st.title("EURO_DATA | Housing")
    st.caption("Housing cost overburden rate | All ages | Total sex")
    st.caption(
        "Share living in households whose housing costs exceed 40% "
        "of disposable household income."
    )

    try:
        catalogue = load_housing_catalogue()
    except (RuntimeError, ValueError) as exc:
        st.error(f"Could not load housing options: {exc}")
        return

    available = catalogue.dropna(subset=["value"])
    labels = (
        available.drop_duplicates("geo")
        .set_index("geo")["geo_label"]
        .to_dict()
    )
    countries = sorted(labels, key=labels.get)
    years = sorted(
        available["time"].astype(int).unique().tolist()
    )
    groups = [
        code for code in POPULATION_LABELS
        if code in available["rskpovth"].unique()
    ]

    period = (
        (2022, 2024)
        if {2022, 2024}.issubset(years)
        else (years[max(0, len(years) - 3)], years[-1])
    )

    with st.sidebar:
        st.header("Filters")

        with st.form("housing_filters"):
            selected = st.multiselect(
                "Countries",
                countries,
                default=[
                    code for code in ["EL", "DE", "FR"]
                    if code in countries
                ],
                format_func=labels.get,
                key="housing_countries",
            )
            start, end = st.select_slider(
                "Years",
                options=years,
                value=period,
                key="housing_years",
            )
            population = st.selectbox(
                "Population group",
                groups,
                format_func=POPULATION_LABELS.get,
                key="housing_population",
            )
            submitted = st.form_submit_button("Load data", type="primary")

        st.caption("Select Load data to apply your choices.")

    if not submitted:
        st.info("Choose your filters and select Load data.")
        return

    if not selected:
        st.info("Select at least one country and load data.")
        return

    try:
        frame = load_housing_data(
            tuple(selected), start, end, population
        )
    except (RuntimeError, ValueError) as exc:
        st.error(f"Could not load housing data: {exc}")
        return

    # Reindex every requested pair so unpublished values remain visible.
    requested = pd.MultiIndex.from_product(
        [
            selected,
            [str(year) for year in range(start, end + 1)],
        ],
        names=["geo", "time"],
    )
    table = frame.set_index(
        ["geo", "time"]
    )[["value", "obs_flag"]]

    table = table.reindex(requested).reset_index()
    table["country"] = table["geo"].map(labels)
    table["year"] = table["time"].astype(int)
    table["flag"] = table["obs_flag"].fillna("").astype(str)
    table = table.sort_values(
        ["country", "year"]
    ).reset_index(drop=True)

    st.subheader("Housing cost overburden rate (%)")
    st.caption(
        f"{POPULATION_LABELS[population]} | Applied years: {start}-{end}"
    )

    if population != "TOTAL":
        st.caption(
            "The percentage refers to this income group. "
            "The threshold is 60% of each country's median "
            "equivalised disposable income after transfers."
        )

    count = int(table["value"].notna().sum())
    missing = len(table) - count
    values = [
        len(table),
        count,
        missing,
        int(table["flag"].ne("").sum()),
    ]

    for column, label, value in zip(
        st.columns(4),
        ["Requested", "Available", "Missing", "Flagged"],
        values,
    ):
        column.metric(label, value)

    if missing:
        st.warning(
            f"{missing} requested country-year pairs "
            "have no published value."
        )

    st.subheader(
        "Country comparison" if start == end else "Housing over time"
    )
    show_housing_chart(table, single_year=start == end)
    show_housing_summary(table, end)

    display = table[
        ["country", "geo", "year", "value", "flag"]
    ].rename(columns={
        "country": "Country",
        "geo": "Code",
        "year": "Year",
        "value": "Housing overburden (%)",
        "flag": "Flag",
    })

    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Year": st.column_config.NumberColumn(format="%d"),
            "Housing overburden (%)": st.column_config.NumberColumn(
                format="%.1f"
            ),
        },
    )

    with st.expander("Source and notes"):
        st.write(
            "Source: Eurostat, ilc_lvho07a. "
            "Unit: % of the selected population."
        )
        st.write(
            "Housing costs and disposable household income are both "
            "net of housing allowances. "
            "Years follow the published housing series."
        )
        st.markdown(
            "[Indicator definition]"
            "(https://ec.europa.eu/eurostat/statistics-explained/"
            "index.php?title=Glossary:Housing_cost_overburden_rate) | "
            "[Income threshold definition]"
            "(https://ec.europa.eu/eurostat/statistics-explained/"
            "index.php?title=Glossary:At-risk-of-poverty_rate)"
        )
        st.write(
            f"Retrieved at UTC: {frame.attrs['retrieved_at_utc']}"
        )

        updated = frame.attrs.get(
            "eurostat_metadata", {}
        ).get("updated", "Not provided")
        st.write(f"Eurostat updated: {updated}")

        st.markdown(
            f"[Open API response]({frame.attrs['request_url']})"
        )
        st.write(
            "Flags: b = break in time series; e = estimated; "
            "p = provisional; u = low reliability; "
            "d = definition differs. Combined flags are preserved."
        )
        st.caption(
            "Responses are cached for up to one hour. "
            "The retrieval time belongs to the cached response."
        )