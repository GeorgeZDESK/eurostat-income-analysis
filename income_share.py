from urllib.parse import urlencode


SHARED_FIELDS = (
    "countries", "ages", "sexes", "year_selection",
    "survey_years", "statinfo", "ranking_sample",
)


def build_ranking_link(base_url, filters):
    params = {"rank_v": "1"}
    for field in SHARED_FIELDS:
        params[field] = filters[field]
    return f"{base_url}?{urlencode(params, doseq=True)}"


def read_ranking_link(query_params):
    versions = query_params.get_all("rank_v")
    if not versions:
        return {}
    if versions != ["1"]:
        raise ValueError("Unsupported ranking link version.")

    filters = {field: query_params.get_all(field) for field in SHARED_FIELDS}
    for values in filters.values():
        if not values or "" in values or len(values) != len(set(values)):
            raise ValueError("A filter is missing or duplicated.")

    for field in ("ages", "year_selection", "statinfo", "ranking_sample"):
        if len(filters[field]) != 1:
            raise ValueError(f"Expected one value for {field}.")

    for field in ("year_selection", "statinfo", "ranking_sample"):
        filters[field] = filters[field][0]
    if filters["year_selection"] not in ("Range", "Specific years"):
        raise ValueError("Unknown year selection.")
    if filters["ranking_sample"] not in ("available", "common"):
        raise ValueError("Unknown ranking sample.")

    try:
        years = sorted(int(value) for value in filters["survey_years"])
    except ValueError:
        raise ValueError("Survey years must be whole numbers.") from None

    if len(years) != len(set(years)):
        raise ValueError("Duplicate survey years.")
    if filters["year_selection"] == "Range" and len(years) != years[-1] - years[0] + 1:
        raise ValueError("Expected a continuous survey year range.")

    filters["survey_years"] = years
    return filters