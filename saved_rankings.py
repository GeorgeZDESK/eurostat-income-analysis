from copy import deepcopy

import altair as alt
import streamlit as st


SAVED_KEY = "saved_eur_pps_rankings"
MAX_SAVED = 3


def _save_ranking(result):
    saved = st.session_state.get(SAVED_KEY, [])
    if len(saved) >= MAX_SAVED or any(item["id"] == result["id"] for item in saved):
        return
    st.session_state[SAVED_KEY] = [*saved, deepcopy(result)]


def _remove_ranking(result_id):
    saved = st.session_state.get(SAVED_KEY, [])
    st.session_state[SAVED_KEY] = [item for item in saved if item["id"] != result_id]


@st.fragment
def render_save_ranking(result):
    saved = st.session_state.get(SAVED_KEY, [])
    already_saved = any(item["id"] == result["id"] for item in saved)
    st.button(
        "Save ranking for comparison",
        key=f"save_ranking_{result['id']}",
        on_click=_save_ranking,
        args=(result,),
        disabled=already_saved or len(saved) >= MAX_SAVED,
    )
    st.caption(f"{len(saved)} of {MAX_SAVED} saved. Compare under Analysis → Saved rankings.")


def _render_card(result, number):
    filters = result["metadata"]["filters"]
    source = result["metadata"]["source"]
    years = filters["survey_years"]
    years_text = ", ".join(map(str, years))
    sex_text = ", ".join(section["label"] for section in result["sections"])

    st.subheader(f"Saved result {number}")
    st.write(filters["statinfo_label"])
    st.caption(
        f"{filters['year_selection']} | Survey years {years_text} | "
        f"Age {result['age_text']} | {sex_text}"
    )
    st.caption(f"EUR and PPS | {filters['ranking_sample_label']}")
    st.caption("Countries | " + ", ".join(result["country_names"]))
    st.markdown(f"**Summary for survey year {years[-1]}**")
    for section in result["sections"]:
        st.markdown(f"**{section['label']}**")
        st.write(section["summary"])

    table_columns = {
        "time": st.column_config.NumberColumn("Year", format="%d"),
        "geo_label": "Country",
        "sex_label": "Sex",
        "rank_EUR": "EUR rank",
        "rank_PPS": "PPS rank",
        "rank_change": "Rank change",
        "value_EUR": st.column_config.NumberColumn("Income (EUR)", format="%.2f"),
        "value_PPS": st.column_config.NumberColumn("Income (PPS)", format="%.2f"),
        "rank_status": "Ranking status",
        "coverage_EUR": "EUR coverage",
        "coverage_PPS": "PPS coverage",
        "flag_EUR": "EUR flag",
        "flag_PPS": "PPS flag",
    }
    rows = result["data"].sort_values("time", ascending=False, kind="stable")
    st.dataframe(
        rows, column_order=list(table_columns), column_config=table_columns,
        hide_index=True, height=250, width="stretch",
    )

    chart_sections = [section for section in result["sections"] if section["chart"] is not None]
    if chart_sections:
        with st.expander(f"Charts for saved result {number}"):
            for section in chart_sections:
                st.markdown(f"**{section['label']}**")
                for panel in section["chart"].hconcat:
                    fitted = panel.properties(
                        autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
                    ).configure_axisX(tickCount=4)
                    fitted.width = alt.Undefined
                    st.altair_chart(fitted, width="stretch")

    st.caption(f"{source['provider']} | {source['dataset']} | {source['delivery']}")
    st.caption(f"Retrieved UTC {source['retrieved_at_utc']}")
    updated_at = source.get("updated_at") or "Unavailable"
    st.caption(f"Eurostat updated {updated_at}")
    st.link_button("Open Eurostat response", source["request_url"])
    st.button(
        f"Remove saved result {number}",
        key=f"remove_ranking_{result['id']}",
        on_click=_remove_ranking,
        args=(result["id"],),
    )


def render_saved_rankings():
    saved = st.session_state.get(SAVED_KEY, [])
    st.title("EURO_DATA | Saved rankings")
    if not saved:
        st.info("Load a country ranking in Euro and PPS, then select Save ranking for comparison.")
        return

    st.caption(f"{len(saved)} of {MAX_SAVED} saved. Ranks depend on the selected sample in each result.")
    columns = st.columns(len(saved))
    for number, (column, result) in enumerate(zip(columns, saved), start=1):
        with column.container(border=True):
            _render_card(result, number)