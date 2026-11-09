import json
from pathlib import Path

import altair as alt
import streamlit as st


COUNTRY_PICKER_KEY = "income_draft_countries"
MAP_CLICK_KEY = "income_country_map_clicks"
PICK_NAME = "country_pick"
MAP_PATH = Path(__file__).resolve().parent / "data" / "maps" / "ne_50m_admin_0_countries.geojson"
EUROSTAT_CODE = {"GR": "EL", "GB": "UK"}


@st.cache_data(show_spinner=False)
def _load_shapes(country_codes):
    with MAP_PATH.open(encoding="utf-8") as file:
        collection = json.load(file)
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection.")

    available = set(country_codes)
    shapes = {}
    for feature in collection.get("features", []):
        iso_code = feature["properties"]["ISO_A2_EH"]
        code = EUROSTAT_CODE.get(iso_code, iso_code)
        if code in available and feature.get("geometry"):
            if code in shapes:
                raise ValueError(f"Duplicate country outline for {code}.")
            shapes[code] = feature["geometry"]
    return shapes


@st.fragment
def render_country_picker(map_area, country_options, country_labels, default_countries):
    if COUNTRY_PICKER_KEY not in st.session_state:
        st.session_state[COUNTRY_PICKER_KEY] = list(default_countries)
    countries = st.multiselect(
        "Countries",
        options=country_options,
        format_func=country_labels.get,
        key=COUNTRY_PICKER_KEY,
    )

    panel = map_area.expander("Select countries on the map", key="income_map_open", on_change="rerun")
    if not panel.open:
        return

    try:
        shapes = _load_shapes(tuple(country_options))
    except (OSError, ValueError, KeyError):
        panel.info("Country outlines are unavailable. Choose countries in the sidebar.")
        return

    if not shapes:
        panel.info("No outlines are available for the listed countries.")
        return

    features = [
        {
            "type": "Feature",
            "geometry": geometry,
            "properties": {},
            "geo_code": code,
            "country_name": country_labels[code],
            "fill": "#2689D6" if code in countries else "#9BA9B7",
        }
        for code, geometry in shapes.items()
    ]
    pick = alt.selection_point(
        name=PICK_NAME, fields=["geo_code"], toggle=False, clear=False,
    )
    chart = (
        alt.Chart(alt.Data(values=features))
        .mark_geoshape(stroke="#ECF4FC", strokeWidth=0.65, clip=True)
        .encode(
            color=alt.Color("fill:N", scale=None, legend=None),
            tooltip=[alt.Tooltip("country_name:N", title="Country")],
        )
        .project(
            type="mercator", center=[13, 57],
            scale=alt.ExprRef(expr="min(360, width / 1.65)"),
        )
        .add_params(pick)
        .properties(height=450, padding=0)
        .configure_view(stroke=None)
    )

    # Reset the map widget's click selection after each applied toggle.
    click_number = st.session_state.get(MAP_CLICK_KEY, 0)
    map_key = f"income_country_map_{click_number}"

    def toggle_country():
        event = st.session_state[map_key]["selection"]
        picked = event.get(PICK_NAME, [])
        if not picked:
            return
        code = picked[0].get("geo_code")
        if code not in shapes:
            return
        draft = list(st.session_state[COUNTRY_PICKER_KEY])
        if code in draft:
            draft.remove(code)
        else:
            draft.append(code)
        st.session_state[COUNTRY_PICKER_KEY] = draft
        st.session_state[MAP_CLICK_KEY] = click_number + 1

    panel.caption("Click a country to add or remove it. Blue means selected. Use Load data to apply.")
    panel.altair_chart(
        chart, width="stretch", key=map_key,
        selection_mode=PICK_NAME, on_select=toggle_country,
    )
    panel.caption("Boundaries | Natural Earth, Admin 0 countries, 1:50m, v5.1.2.")
    list_only = [country_labels[code] for code in country_options if code not in shapes]
    if list_only:
        panel.caption("Available in the list | " + ", ".join(list_only))