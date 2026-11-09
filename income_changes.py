import pandas as pd


def compare_income_years(table, start_year, end_year):
    """Compare two survey-year endpoints for each EUR income series."""
    if type(start_year) is not int or type(end_year) is not int or start_year >= end_year:
        raise ValueError("Provide two distinct survey years in chronological order.")
    if not table["unit"].isin(["EUR"]).all():
        raise ValueError("This change calculation requires EUR observations.")

    series_key = ["freq", "age", "sex", "statinfo", "unit", "geo"]
    if table[series_key + ["time"]].isna().any().any():
        raise ValueError("Income observations must have all dimension codes.")

    columns = series_key + ["value", "obs_flag"]
    if "coverage" in table:
        columns.append("coverage")

    years = pd.to_numeric(table["time"], errors="raise")
    start_mask = years.eq(start_year)
    end_mask = years.eq(end_year)
    start = table.loc[start_mask, columns]
    end = table.loc[end_mask, columns]
    result = start.merge(
        end, on=series_key, how="outer", suffixes=("_start", "_end"),
        validate="one_to_one", indicator="endpoint_match",
    )
    result["start_year"] = start_year
    result["end_year"] = end_year
    result["elapsed_years"] = end_year - start_year

    # A break at the starting year begins a new segment.
    flags = table["obs_flag"].fillna("")
    within_period = years.between(start_year, end_year)
    break_after_start = years.gt(start_year) & flags.str.contains("b", regex=False)
    definition_differs = flags.str.contains("d", regex=False)
    blocking_rows = within_period & (break_after_start | definition_differs)
    blocked_series = table.loc[blocking_rows, series_key]
    blocked_keys = pd.MultiIndex.from_frame(blocked_series)
    result_keys = pd.MultiIndex.from_frame(result[series_key])
    result["blocked_by_flag"] = result_keys.isin(blocked_keys)

    start_value = result["value_start"]
    difference = result["value_end"] - start_value
    comparable = ~result["blocked_by_flag"]
    result["change_eur"] = difference.where(comparable)

    positive_start = start_value.gt(0)
    denominator = start_value.where(positive_start)
    result["change_pct"] = result["change_eur"].div(denominator).mul(100)
    return result