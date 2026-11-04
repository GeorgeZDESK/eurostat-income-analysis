import altair as alt
import pandas as pd
import streamlit as st

from eurostat_api import fetch_urban_catalogue, fetch_urban_income


AREA_LABELS = {
    "DEG1": "Cities",
    "DEG2": "Towns and suburbs",
    "DEG3": "Rural areas",
}


@st.cache_data(ttl=3600, show_spinner=False)
def load_urban_catalogue():
    return fetch_urban_catalogue()


@st.cache_data(ttl=3600, show_spinner=False)
def load_urban_data(country, start, end, indicator, unit):
    return fetch_urban_income(
        [country], start, end, indicator=indicator, unit=unit
    )


def urban_chart(table, unit, single_year):
    area_order = list(AREA_LABELS.values())

    color = alt.Color(
        "area:N",
        title="Area type",
        scale=alt.Scale(domain=area_order),
        legend=alt.Legend(orient="bottom"),
    )
    tooltip = [
        alt.Tooltip("country:N", title="Country"),
        alt.Tooltip("area:N", title="Area type"),
        alt.Tooltip("year:O", title="Survey year"),
        alt.Tooltip(
            "value:Q",
            title=f"Income ({unit})",
            format=",.2f",
        ),
        alt.Tooltip("flag:N", title="Eurostat flag"),
    ]
    base = alt.Chart(table).encode(
        color=color,
        tooltip=tooltip,
    )

    if single_year:
        bars = base.mark_bar().encode(
            x=alt.X(
                "value:Q",
                title=f"Income ({unit})",
                scale=alt.Scale(zero=True),
            ),
            y=alt.Y(
                "area:N",
                title=None,
                sort=area_order,
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

    else:
        # Keep missing rows and start a new line segment at each b flag.
        plot = table.copy()
        breaks = plot["flag"].str.contains("b", regex=False)
        segments = breaks.groupby(plot["deg_urb"]).cumsum()
        plot["segment"] = (
            plot["deg_urb"] + "_" + segments.astype(str)
        )

        position = alt.Chart(plot).encode(
            color=color,
            tooltip=tooltip,
            x=alt.X(
                "year:O",
                title="Survey year",
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y(
                "value:Q",
                title=f"Income ({unit})",
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

    return chart.properties(height=360)


def show_urban_summary(table, year, unit):
    st.subheader(f"Summary for survey year {year}")

    latest = table.loc[table["year"].eq(year)]
    available = latest.dropna(subset=["value"])

    st.write(
        f"{len(available)} of {len(latest)} area types have data."
    )

    missing = latest.loc[
        latest["value"].isna(), "area"
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
        st.caption(
            "Some values in this summary carry Eurostat flags."
        )

    highest = float(available["value"].max())
    lowest = float(available["value"].min())

    if highest == lowest:
        areas = ", ".join(available["area"])
        st.write(f"{areas}: {highest:,.2f} {unit}.")
        return

    top = ", ".join(
        available.loc[available["value"].eq(highest), "area"]
    )
    bottom = ", ".join(
        available.loc[available["value"].eq(lowest), "area"]
    )

    st.write(f"Highest: {top} ({highest:,.2f} {unit}).")
    st.write(f"Lowest: {bottom} ({lowest:,.2f} {unit}).")
    st.write(
        "Difference between highest and lowest: "
        f"{highest - lowest:,.2f} {unit}."
    )

    if lowest > 0:
        st.write(
            f"The highest value is "
            f"{(highest / lowest - 1) * 100:.1f}% above the lowest."
        )


def render_urban_income_view():
    st.title("EURO_DATA | Urbanisation")
    st.caption(
        "Equivalised disposable income | All ages | Total sex"
    )
    st.caption(
        "Years are survey years. Income reference periods can differ "
        "by country and period."
    )

    try:
        catalogue = load_urban_catalogue()
    except (RuntimeError, ValueError) as exc:
        st.error(f"Could not load urbanisation options: {exc}")
        return

    available = catalogue.dropna(subset=["value"])
    labels = {
        dim: (
            available.drop_duplicates(dim)
            .set_index(dim)[f"{dim}_label"]
            .to_dict()
        )
        for dim in ["geo", "statinfo", "unit"]
    }

    countries = sorted(labels["geo"], key=labels["geo"].get)
    years = sorted(
        available["time"].astype(int).unique().tolist()
    )
    measures = [
        code for code in ["MED_EI", "MEAN_EI"]
        if code in labels["statinfo"]
    ]
    units = [
        code for code in ["EUR", "NAC", "PPS"]
        if code in labels["unit"]
    ]
    period = (
        (2022, 2024)
        if {2022, 2024}.issubset(years)
        else (years[max(0, len(years) - 3)], years[-1])
    )

    with st.sidebar:
        st.header("Filters")

        with st.form("urban_income_filters"):
            country = st.selectbox(
                "Country",
                countries,
                index=countries.index("EL") if "EL" in countries else 0,
                format_func=labels["geo"].get,
                key="urban_country",
            )
            st.caption(
                "The three area types within this country "
                "are shown separately."
            )
            start, end = st.select_slider(
                "Survey years",
                options=years,
                value=period,
                key="urban_years",
            )
            indicator = st.selectbox(
                "Income measure",
                measures,
                format_func=labels["statinfo"].get,
                key="urban_measure",
            )
            unit = st.selectbox(
                "Unit",
                units,
                format_func=labels["unit"].get,
                key="urban_unit",
            )
            submitted = st.form_submit_button(
                "Load data", type="primary"
            )

        st.caption("Select Load data to apply your choices.")

    if not submitted:
        st.info("Choose your filters and select Load data.")
        return

    try:
        frame = load_urban_data(
            country, start, end, indicator, unit
        )
    except (RuntimeError, ValueError) as exc:
        st.error(f"Could not load urban income data: {exc}")
        return

    # Include every requested combination, even if the API omits it.
    requested = pd.MultiIndex.from_product(
        [
            [country],
            list(AREA_LABELS),
            [str(y) for y in range(start, end + 1)],
        ],
        names=["geo", "deg_urb", "time"],
    )
    table = (
        frame.set_index(["geo", "deg_urb", "time"])
        [["value", "obs_flag"]]
        .reindex(requested)
        .reset_index()
    )

    table["country"] = labels["geo"][country]
    table["area"] = table["deg_urb"].map(AREA_LABELS)
    table["year"] = table["time"].astype(int)
    table["flag"] = table["obs_flag"].fillna("").astype(str)
    table = table.sort_values(
        ["deg_urb", "year"]
    ).reset_index(drop=True)

    st.subheader(f"{labels['statinfo'][indicator]} ({unit})")
    st.caption(
        f"{labels['geo'][country]} | "
        f"Applied survey years: {start}-{end}"
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
            f"{missing} requested area-year pairs "
            "have no published value."
        )

    if unit == "PPS":
        st.caption(
            "PPS adjusts for price-level differences between countries. "
            "It does not by itself measure real income growth."
        )
    else:
        st.caption(
            f"{unit} values are nominal and have not been "
            "adjusted for inflation."
        )

    single_year = start == end

    st.subheader(
        "Urbanisation comparison" if single_year else "Income over time"
    )
    st.altair_chart(
        urban_chart(table, unit, single_year),
        width="stretch",
    )

    note = "Diamonds mark flagged observations."
    if not single_year:
        note += " Lines stop at missing values and restart at b flags."
    st.caption(note)

    show_urban_summary(table, end, unit)

    display = table[
        ["country", "geo", "area", "year", "value", "flag"]
    ].rename(columns={
        "country": "Country",
        "geo": "Code",
        "area": "Area type",
        "year": "Survey year",
        "value": f"Income ({unit})",
        "flag": "Flag",
    })

    st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        column_config={
            "Survey year": st.column_config.NumberColumn(format="%d"),
            f"Income ({unit})": st.column_config.NumberColumn(
                format="%.2f"
            ),
        },
    )

    with st.expander("Source and notes"):
        st.write("Source: Eurostat, ilc_di17.")
        st.write(
            "The categories describe area types within the selected "
            "country: Cities, Towns and suburbs, Rural areas."
        )
        st.markdown(
            "[Degree of urbanisation methodology]"
            "(https://ec.europa.eu/eurostat/en/web/"
            "degree-of-urbanisation/methodology)"
        )

        if unit == "NAC":
            st.write(
                "Check historical currency changes before interpreting "
                "national-currency growth across years."
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