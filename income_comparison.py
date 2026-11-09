import pandas as pd


def build_eur_pps_pairs(frame, country_codes):
    """Build one EUR/PPS pair per income series and survey year."""
    units = ["EUR", "PPS"]
    pair_key = ["freq", "age", "sex", "statinfo", "geo", "time"]
    observation_key = pair_key + ["unit"]
    unit_mask = frame["unit"].isin(units)
    rows = frame.loc[unit_mask, observation_key + ["value", "obs_flag"]].copy()

    if rows[observation_key].isna().any().any():
        raise ValueError("EUR/PPS observations must have all dimension codes.")
    if rows.duplicated(observation_key).any():
        raise ValueError("Duplicate EUR/PPS observations.")

    missing_keys = pd.DataFrame.from_records(
        frame.attrs.get("missing_observations", []), columns=observation_key,
    )
    requested_units = set(rows["unit"]) | set(missing_keys["unit"])
    if not set(units).issubset(requested_units):
        raise ValueError("Request both EUR and PPS before building pairs.")

    missing_unit_mask = missing_keys["unit"].isin(units)
    expected_missing = missing_keys.loc[missing_unit_mask, pair_key]
    pair_rows = pd.concat([rows[pair_key], expected_missing], ignore_index=True)
    unique_pairs = pair_rows.drop_duplicates()
    pair_index = pd.MultiIndex.from_frame(unique_pairs)

    rows["coverage"] = "Available"
    missing_value = rows["value"].isna()
    rows.loc[missing_value, "coverage"] = "Missing value"

    wide_tables = []
    for field, prefix in [
        ("value", "value_"), ("obs_flag", "flag_"), ("coverage", "coverage_"),
    ]:
        wide = rows.pivot(index=pair_key, columns="unit", values=field)
        wide = wide.reindex(index=pair_index, columns=units)
        wide_tables.append(wide.add_prefix(prefix))

    pairs = pd.concat(wide_tables, axis=1).reset_index()
    pairs.columns.name = None
    coverage_columns = ["coverage_EUR", "coverage_PPS"]
    pairs[coverage_columns] = pairs[coverage_columns].fillna("Outside API cube")

    has_eur = pairs["value_EUR"].notna()
    has_pps = pairs["value_PPS"].notna()
    is_country = pairs["geo"].isin(country_codes)
    pairs["pair_status"] = "Paired"
    pairs.loc[~has_eur & has_pps, "pair_status"] = "Missing EUR"
    pairs.loc[has_eur & ~has_pps, "pair_status"] = "Missing PPS"
    pairs.loc[~has_eur & ~has_pps, "pair_status"] = "Missing EUR and PPS"
    pairs.loc[~is_country, "pair_status"] = "Outside country scope"
    pairs.attrs = frame.attrs.copy()
    return pairs


def rank_eur_pps_pairs(pairs, *, mode="available", survey_years=None):
    """Rank paired countries per year or over a common country sample."""
    if mode not in ("available", "common"):
        raise ValueError("Ranking mode must be 'available' or 'common'.")

    series_dimensions = ["freq", "age", "sex", "statinfo"]
    group_key = series_dimensions + ["time"]
    pair_key = group_key + ["geo"]
    value_columns = ["value_EUR", "value_PPS"]
    ranked = pairs.reset_index(drop=True)

    if ranked[pair_key].isna().any().any():
        raise ValueError("Ranking rows must have all dimension codes.")
    if ranked.duplicated(pair_key).any():
        raise ValueError("Duplicate country rows within a ranking group.")

    selected_year_codes = set()
    if mode == "common" or survey_years is not None:
        if not isinstance(survey_years, (list, tuple)) or not survey_years:
            raise ValueError("Provide a non-empty list of survey years.")
        if any(type(year) is not int or year < 2003 for year in survey_years):
            raise ValueError("Use integer survey years from 2003.")
        selected_year_codes = {str(year) for year in survey_years}
        if not ranked["time"].isin(selected_year_codes).all():
            raise ValueError("Ranking rows must use only the selected survey years.")

    ranked["rank_status"] = ranked["pair_status"].astype("string")
    paired_mask = ranked["pair_status"].eq("Paired")
    eligible = ranked.loc[paired_mask]
    if eligible[value_columns].isna().any().any():
        raise ValueError("Rows marked Paired must have both income values.")

    if mode == "common":
        series_key = series_dimensions + ["geo"]
        paired_year_counts = eligible.groupby(series_key, sort=False)["time"].transform(
            "nunique"
        )
        common_mask = paired_year_counts.eq(len(selected_year_codes))
        excluded_index = eligible.index[~common_mask]
        ranked.loc[excluded_index, "rank_status"] = (
            "Incomplete paired coverage across selected years"
        )
        eligible = eligible.loc[common_mask]

    ranks = eligible.groupby(group_key, sort=False)[value_columns].rank(
        method="min", ascending=False,
    )
    ranked["rank_EUR"] = ranks["value_EUR"].astype("Int64")
    ranked["rank_PPS"] = ranks["value_PPS"].astype("Int64")
    ranked["rank_change"] = ranked["rank_EUR"] - ranked["rank_PPS"]
    ranked.loc[eligible.index, "rank_status"] = "Ranked"

    groups = ranked.groupby(group_key, sort=False)
    ranked["rank_sample_size"] = groups["rank_EUR"].transform("count")
    return ranked