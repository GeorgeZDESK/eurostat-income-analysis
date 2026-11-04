import pandas as pd

from eurostat_api import fetch_hicp, fetch_income


def fetch_greek_real_income(
    start_survey_year, end_survey_year, indicator="MED_EI", age="TOTAL"
):
    """Align one Greek income series in EUR with annual all-items HICP."""
    income = fetch_income(
        ["EL"], start_survey_year, end_survey_year,
        indicator=indicator, unit="EUR", ages=[age],
    )
    hicp = fetch_hicp(
        ["EL"], start_survey_year - 1, end_survey_year - 1
    )

    # Build the full requested period, including years omitted by either API.
    frame = pd.DataFrame({
        "survey_year": range(start_survey_year, end_survey_year + 1)
    })
    frame["geo"] = "EL"
    frame["age"] = age
    frame["income_year"] = frame["survey_year"] - 1

    income_rows = income[
        ["geo", "age", "time", "value", "obs_flag"]
    ].rename(columns={
        "time": "survey_year",
        "value": "nominal_income",
        "obs_flag": "income_flag",
    })
    income_rows["survey_year"] = income_rows["survey_year"].astype(int)

    price_rows = hicp[["geo", "time", "value", "obs_flag"]].rename(columns={
        "time": "income_year",
        "value": "hicp",
        "obs_flag": "hicp_flag",
    })
    price_rows["income_year"] = price_rows["income_year"].astype(int)

    frame = frame.merge(
        income_rows,
        on=["geo", "age", "survey_year"],
        how="left",
        validate="one_to_one",
    )
    frame = frame.merge(
        price_rows,
        on=["geo", "income_year"],
        how="left",
        validate="many_to_one",
        indicator="hicp_match",
    )
    frame["statinfo"] = indicator
    frame["unit"] = "EUR"
    frame.attrs["sources"] = {
        "income": income.attrs.copy(),
        "hicp": hicp.attrs.copy(),
    }
    return frame


def calculate_real_change(frame):
    """Calculate cumulative changes for one complete Greek income series."""
    series_key = ["geo", "age", "statinfo", "unit"]
    if frame.empty or len(frame[series_key].drop_duplicates()) != 1:
        raise ValueError("Provide exactly one income series.")
    if not frame["geo"].eq("EL").all() or not frame["unit"].eq("EUR").all():
        raise ValueError("This calculation currently supports Greece in EUR.")

    ordered = frame.sort_values("income_year")
    if len(ordered) < 2 or ordered["income_year"].duplicated().any():
        raise ValueError("Provide at least two distinct income years.")
    if ordered[["nominal_income", "hicp"]].isna().any().any():
        raise ValueError("Income or HICP values are missing; review the joined table.")
    if ordered["hicp"].le(0).any() or ordered["nominal_income"].iloc[0] <= 0:
        raise ValueError("HICP and the starting income must be positive.")

    flags_used = {}
    for column in ["income_flag", "hicp_flag"]:
        flags = ordered[column].fillna("")

        # A break at the start marks a new segment; later breaks interrupt it.
        if flags.iloc[1:].str.contains("b", regex=False).any():
            raise ValueError(f"Time-series break within the period: {column}.")
        if flags.str.contains("d", regex=False).any():
            raise ValueError(f"Review definition-differs flags: {column}.")

        flags_used[column] = sorted(
            flags.loc[flags.ne("")].unique().tolist()
        )

    first = ordered.iloc[0]
    last = ordered.iloc[-1]
    income_ratio = float(last["nominal_income"] / first["nominal_income"])
    price_ratio = float(last["hicp"] / first["hicp"])

    return {
        "start_income_year": int(first["income_year"]),
        "end_income_year": int(last["income_year"]),
        "nominal_change_pct": (income_ratio - 1) * 100,
        "hicp_change_pct": (price_ratio - 1) * 100,
        "real_change_pct": (income_ratio / price_ratio - 1) * 100,
        "flags": flags_used,
    }