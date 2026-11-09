from itertools import product
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import pandas as pd

def _request_json(url):
    """Request Eurostat JSON and record when the response was retrieved."""
    try:
        with urlopen(url, timeout=30) as response:
            data = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Eurostat HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Eurostat request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Eurostat returned invalid JSON.") from exc

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not isinstance(data, dict) or "error" in data or "warning" in data:
        raise RuntimeError(f"Unexpected Eurostat response: {data}")
    return data, retrieved_at



def _read_cells(raw, count, field):
    """Align dense or sparse observations with their cube positions."""
    if field == "status" and isinstance(raw, str):
        raw = [raw] * count
    if field == "status" and raw is None:
        raw = {}
    if not isinstance(raw, (dict, list)):
        raise ValueError(f"Unsupported {field} structure.")
    if isinstance(raw, list) and len(raw) != count:
        raise ValueError(f"Unexpected number of {field} entries.")

    cells = pd.Series(raw)
    try:
        cells.index = cells.index.astype("int64")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} indices.") from exc
    if not cells.index.is_unique or not cells.index.isin(range(count)).all():
        raise ValueError(f"Invalid {field} indices.")

    # Missing cube positions remain missing; zero stays a valid value.
    return cells.reindex(range(count))


def jsonstat_to_frame(data):
    """Decode a filtered JSON-stat dataset without dropping missing cells."""
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON-stat object.")
    if data.get("class") != "dataset" or data.get("version") != "2.0":
        raise ValueError("Expected a JSON-stat 2.0 dataset.")
    if not {"id", "size", "dimension", "value"}.issubset(data):
        raise ValueError("Incomplete JSON-stat dataset.")

    dimensions = data["id"]
    sizes = data["size"]
    if len(dimensions) != len(sizes) or len(set(dimensions)) != len(dimensions):
        raise ValueError("Invalid dimension IDs or sizes.")
    if not sizes or any(not isinstance(size, int) or size < 0 for size in sizes):
        raise ValueError("Invalid dimension sizes.")

    ordered_codes = []
    for dim, size in zip(dimensions, sizes):
        category = data["dimension"][dim]["category"]
        index = category.get("index")
        if isinstance(index, dict):
            if sorted(index.values()) != list(range(size)):
                raise ValueError(f"Invalid category positions for {dim}.")
            codes = sorted(index, key=index.get)
        elif isinstance(index, list):
            codes = index
        elif index is None and size == 1:
            codes = list(category.get("label", {}))
        else:
            raise ValueError(f"Unsupported category index for {dim}.")
        if len(codes) != size or len(set(codes)) != size:
            raise ValueError(f"Category count mismatch for {dim}.")
        ordered_codes.append(codes)

    # JSON-stat changes the last dimension fastest.
    frame = pd.DataFrame(product(*ordered_codes), columns=dimensions)
    for dim in dimensions:
        labels = data["dimension"][dim]["category"].get("label", {})
        frame[f"{dim}_label"] = frame[dim].map(labels)

    values = _read_cells(data["value"], len(frame), "value")
    frame["value"] = pd.to_numeric(values, errors="raise").astype("Float64")
    frame["obs_flag"] = _read_cells(
        data.get("status"), len(frame), "status"
    ).astype("string")

    # Preserve source, update time, dimensions and Eurostat annotations.
    frame.attrs["eurostat_metadata"] = {
        key: value for key, value in data.items()
        if key not in {"value", "status"}
    }
    return frame
    

def fetch_income(
    countries, start_year=None, end_year=None, indicator="MED_EI", unit="EUR",
    ages=None, sexes=None, *, survey_years=None,
):
    """Fetch ilc_di03 observations for a range or specific survey years."""
    if not isinstance(countries, (list, tuple)) or not countries:
        raise ValueError("Provide a non-empty list of Eurostat country codes.")
    if any(not isinstance(code, str) or not code.strip() for code in countries):
        raise ValueError("Country codes must be non-empty strings.")

    if survey_years is None:
        if type(start_year) is not int or type(end_year) is not int:
            raise ValueError("Survey years must be integers.")
        if start_year < 2003 or end_year < start_year:
            raise ValueError("Use survey years from 2003 with start_year <= end_year.")
        selected_years = range(start_year, end_year + 1)
        time_params = {
            "sinceTimePeriod": start_year,
            "untilTimePeriod": end_year,
        }
    else:
        if start_year is not None or end_year is not None:
            raise ValueError("Choose a year range or specific survey years.")
        if not isinstance(survey_years, (list, tuple)) or not survey_years:
            raise ValueError("Provide a non-empty list of survey years.")
        if any(type(year) is not int or year < 2003 for year in survey_years):
            raise ValueError("Use integer survey years from 2003.")
        selected_years = sorted(set(survey_years))
        time_params = {"time": selected_years}

    # Default to total age; accept only the groups selected for this explorer.
    if ages is None:
        ages = ["TOTAL"]

    valid_ages = ["TOTAL", "Y_LT18", "Y18-24", "Y25-49", "Y50-64", "Y_GE65"]
    if not isinstance(ages, (list, tuple)) or not ages:
        raise ValueError("Provide a non-empty list of Eurostat age codes.")
    if any(not isinstance(code, str) or code not in valid_ages for code in ages):
        raise ValueError(f"Supported age codes: {valid_ages}")
        
    # Preserve existing callers that omit sex selection.
    if sexes is None:
        sexes = ["T"]

    valid_sexes = ["F", "M", "T"]
    if not isinstance(sexes, (list, tuple)) or not sexes:
        raise ValueError("Provide a non-empty list of Eurostat sex codes.")
    if any(not isinstance(code, str) or code not in valid_sexes for code in sexes):
        raise ValueError(f"Supported sex codes: {valid_sexes}")
    sexes = list(dict.fromkeys(sexes))

    countries = list(dict.fromkeys(code.strip().upper() for code in countries))
    ages = list(dict.fromkeys(ages))

    if "TOTAL" in ages and len(ages) > 1:
        raise ValueError("Request TOTAL separately from the selected age groups.")

    units = [unit] if isinstance(unit, str) else unit
    if not isinstance(units, (list, tuple)) or not units:
        raise ValueError("Provide a unit code or a non-empty list of unit codes.")
    valid_units = ["EUR", "PPS", "NAC"]
    if any(not isinstance(code, str) or code not in valid_units for code in units):
        raise ValueError(f"Supported income units: {valid_units}")
    units = list(dict.fromkeys(units))

    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_di03")
    params = {
        "lang": "EN", "freq": "A", "geo": countries,
        "age": ages, "sex": sexes, "statinfo": indicator, "unit": units}
    params.update(time_params)
    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    years = [str(year) for year in selected_years]
    allowed = {
        "freq": ["A"], "age": ages, "sex": sexes,
        "statinfo": [indicator], "unit": units, "geo": countries, "time": years}
    if set(data.get("id", [])) != set(allowed):
        raise ValueError("Unexpected ilc_di03 dimensions.")

    frame = jsonstat_to_frame(data)
    for dim, codes in allowed.items():
        if not frame[dim].isin(codes).all():
            raise ValueError(f"Response does not match the {dim} filter.")

    # Keep every dimension in the observation key.
    key = ["freq", "age", "sex", "statinfo", "unit", "geo", "time"]
    if frame.duplicated(key).any():
        raise ValueError("Duplicate income observations.")
    if frame.empty or frame["value"].isna().all():
        raise ValueError("No income observations are available for these filters.")

    requested = pd.MultiIndex.from_product(
        [["A"], ages, sexes, [indicator], units, countries, years],
        names=key)
    coverage = frame.set_index(key)["value"].reindex(requested)
    missing = coverage[coverage.isna()].index.to_frame(index=False)

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "requested_observations": len(requested),
        "missing_observations": missing.to_dict("records"),
    })
    return frame


def fetch_income_catalogue():
    """Load codes, labels and coverage for the total-age country explorer."""
    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_di03"
    )

    # Keep all published indicators and units within this filtered slice.
    params = {
        "lang": "EN", "freq": "A", "age": "TOTAL", "sex": "T",
        "geoLevel": "country", "sinceTimePeriod": 2003,
    }
    url = endpoint + "?" + urlencode(params)
    data, retrieved_at = _request_json(url)

    expected = {"freq", "age", "sex", "statinfo", "unit", "geo", "time"}
    if set(data.get("id", [])) != expected:
        raise ValueError("Unexpected ilc_di03 catalogue dimensions.")

    frame = jsonstat_to_frame(data)
    for dim, code in {"freq": "A", "age": "TOTAL", "sex": "T"}.items():
        if not frame[dim].eq(code).all():
            raise ValueError(f"Catalogue does not match the {dim} filter.")
    if not frame["time"].astype(int).ge(2003).all():
        raise ValueError("Catalogue contains survey years before 2003.")

    key = ["geo", "time", "statinfo", "unit"]
    if frame.duplicated(key).any():
        raise ValueError("Duplicate catalogue observations.")
    if frame.empty or frame["value"].isna().all():
        raise ValueError("No income observations are available in the catalogue.")

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "geo_level": "country",
    })
    return frame


def fetch_hicp(countries, start_year, end_year):
    """Fetch annual average, all-items HICP for selected calendar years."""
    if not isinstance(countries, (list, tuple)) or not countries:
        raise ValueError("Provide a non-empty list of Eurostat country codes.")
    if any(not isinstance(code, str) or not code.strip() for code in countries):
        raise ValueError("Country codes must be non-empty strings.")
    if type(start_year) is not int or type(end_year) is not int:
        raise ValueError("Calendar years must be integers.")
    if start_year > end_year:
        raise ValueError("Use start_year <= end_year.")

    countries = list(dict.fromkeys(code.strip().upper() for code in countries))
    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/prc_hicp_ainr"
    )
    params = {
        "lang": "EN", "freq": "A", "geo": countries,
        "unit": "INX_A_AVG", "coicop18": "TOTAL",
        "sinceTimePeriod": start_year, "untilTimePeriod": end_year,
    }
    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    years = [str(year) for year in range(start_year, end_year + 1)]
    allowed = {
        "freq": ["A"], "unit": ["INX_A_AVG"], "coicop18": ["TOTAL"],
        "geo": countries, "time": years,
    }
    if set(data.get("id", [])) != set(allowed):
        raise ValueError("Unexpected HICP dimensions.")

    frame = jsonstat_to_frame(data)
    for dim, codes in allowed.items():
        if not frame[dim].isin(codes).all():
            raise ValueError(f"HICP response does not match the {dim} filter.")

    if frame.duplicated(["geo", "time"]).any():
        raise ValueError("Duplicate HICP country-year observations.")
    if frame.empty or frame["value"].isna().all():
        raise ValueError("No HICP observations are available for these filters.")
    if frame["value"].dropna().le(0).any():
        raise ValueError("HICP index values must be positive.")

    # The year is a price calendar year; no survey-year conversion happens here.
    requested = pd.MultiIndex.from_product(
        [countries, years], names=["geo", "time"]
    )
    coverage = frame.set_index(["geo", "time"])["value"].reindex(requested)
    missing = coverage[coverage.isna()].index.to_frame(index=False)

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "requested_observations": len(requested),
        "missing_observations": missing.to_dict("records"),
    })
    return frame

def fetch_housing_overburden(
    countries, start_year, end_year, poverty_status="TOTAL"
):
    """Fetch housing cost overburden rates for total age and total sex."""
    if not isinstance(countries, (list, tuple)) or not countries:
        raise ValueError("Provide a non-empty list of Eurostat country codes.")
    if any(not isinstance(code, str) or not code.strip() for code in countries):
        raise ValueError("Country codes must be non-empty strings.")
    if type(start_year) is not int or type(end_year) is not int:
        raise ValueError("Years must be integers.")
    if start_year < 2003 or end_year < start_year:
        raise ValueError("Use years from 2003 with start_year <= end_year.")

    valid_statuses = ["TOTAL", "A_60", "B_60"]
    if not isinstance(poverty_status, str) or poverty_status not in valid_statuses:
        raise ValueError(f"Supported poverty status codes: {valid_statuses}")

    countries = list(dict.fromkeys(code.strip().upper() for code in countries))
    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_lvho07a"
    )
    params = {
        "lang": "EN", "freq": "A", "unit": "PC",
        "age": "TOTAL", "sex": "T", "rskpovth": poverty_status,
        "geo": countries,
        "sinceTimePeriod": start_year, "untilTimePeriod": end_year,
    }
    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    years = [str(year) for year in range(start_year, end_year + 1)]
    allowed = {
        "freq": ["A"], "unit": ["PC"], "rskpovth": [poverty_status],
        "age": ["TOTAL"], "sex": ["T"], "geo": countries, "time": years,
    }
    if set(data.get("id", [])) != set(allowed):
        raise ValueError("Unexpected housing dataset dimensions.")

    frame = jsonstat_to_frame(data)
    for dim, codes in allowed.items():
        if not frame[dim].isin(codes).all():
            raise ValueError(f"Housing response does not match the {dim} filter.")

    if frame.duplicated(["geo", "time"]).any():
        raise ValueError("Duplicate housing country-year observations.")
    if frame.empty or frame["value"].isna().all():
        raise ValueError("No housing observations are available for these filters.")

    # Rates are population percentages; zero is a valid published value.
    if not frame["value"].dropna().between(0, 100).all():
        raise ValueError("Housing rates must be percentages between 0 and 100.")

    # Keep Eurostat's published years without applying an income-year shift.
    requested = pd.MultiIndex.from_product(
        [countries, years], names=["geo", "time"]
    )
    coverage = frame.set_index(["geo", "time"])["value"].reindex(requested)
    missing = coverage[coverage.isna()].index.to_frame(index=False)

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "requested_observations": len(requested),
        "missing_observations": missing.to_dict("records"),
    })
    return frame

def fetch_housing_catalogue():
    """Load country, year and population-group options for housing rates."""
    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_lvho07a"
    )
    params = {
        "lang": "EN",
        "freq": "A",
        "unit": "PC",
        "age": "TOTAL",
        "sex": "T",
        "rskpovth": ["TOTAL", "A_60", "B_60"],
        "geoLevel": "country",
        "sinceTimePeriod": 2003,
    }
    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    expected = {"freq", "unit", "rskpovth", "age", "sex", "geo", "time"}
    if set(data.get("id", [])) != expected:
        raise ValueError("Unexpected housing catalogue dimensions.")

    frame = jsonstat_to_frame(data)

    for dim, code in {
        "freq": "A",
        "unit": "PC",
        "age": "TOTAL",
        "sex": "T",
    }.items():
        if not frame[dim].eq(code).all():
            raise ValueError(
                f"Housing catalogue does not match the {dim} filter."
            )

    if not frame["rskpovth"].isin(["TOTAL", "A_60", "B_60"]).all():
        raise ValueError("Unexpected population groups in housing catalogue.")

    if not frame["time"].astype(int).ge(2003).all():
        raise ValueError("Housing catalogue contains years before 2003.")

    if frame.duplicated(["geo", "rskpovth", "time"]).any():
        raise ValueError("Duplicate housing catalogue observations.")

    if frame.empty or frame["value"].isna().all():
        raise ValueError(
            "No housing observations are available in the catalogue."
        )

    if not frame["value"].dropna().between(0, 100).all():
        raise ValueError(
            "Housing rates must be percentages between 0 and 100."
        )

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "geo_level": "country",
    })
    return frame


def fetch_urban_income(
    countries, start_year, end_year,
    indicator="MED_EI", unit="EUR", urban_classes=None,
):
    """Fetch income by degree of urbanisation, for all ages and total sex."""
    if not isinstance(countries, (list, tuple)) or not countries:
        raise ValueError("Provide a non-empty list of Eurostat country codes.")

    if any(not isinstance(code, str) or not code.strip() for code in countries):
        raise ValueError("Country codes must be non-empty strings.")

    if type(start_year) is not int or type(end_year) is not int:
        raise ValueError("Years must be integers.")

    if start_year < 2003 or end_year < start_year:
        raise ValueError("Use years from 2003 with start_year <= end_year.")

    if indicator not in ["MED_EI", "MEAN_EI"]:
        raise ValueError("Supported indicators: MED_EI, MEAN_EI.")

    if unit not in ["EUR", "NAC", "PPS"]:
        raise ValueError("Supported units: EUR, NAC, PPS.")

    valid_classes = ["DEG1", "DEG2", "DEG3"]

    if urban_classes is None:
        urban_classes = valid_classes.copy()

    if (
        not isinstance(urban_classes, (list, tuple))
        or not urban_classes
        or any(code not in valid_classes for code in urban_classes)
    ):
        raise ValueError(
            f"Supported urbanisation classes: {valid_classes}"
        )

    countries = list(dict.fromkeys(
        code.strip().upper() for code in countries
    ))
    urban_classes = list(dict.fromkeys(urban_classes))

    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_di17"
    )
    params = {
        "lang": "EN",
        "freq": "A",
        "unit": unit,
        "statinfo": indicator,
        "deg_urb": urban_classes,
        "sex": "T",
        "age": "TOTAL",
        "geo": countries,
        "sinceTimePeriod": start_year,
        "untilTimePeriod": end_year,
    }

    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    years = [str(year) for year in range(start_year, end_year + 1)]
    allowed = {
        "freq": ["A"],
        "unit": [unit],
        "statinfo": [indicator],
        "deg_urb": urban_classes,
        "sex": ["T"],
        "age": ["TOTAL"],
        "geo": countries,
        "time": years,
    }

    if set(data.get("id", [])) != set(allowed):
        raise ValueError("Unexpected urban income dataset dimensions.")

    frame = jsonstat_to_frame(data)

    for dim, codes in allowed.items():
        if not frame[dim].isin(codes).all():
            raise ValueError(
                f"Urban income response does not match the {dim} filter."
            )

    if frame.duplicated(["geo", "deg_urb", "time"]).any():
        raise ValueError("Duplicate urban income observations.")

    if frame.empty or frame["value"].isna().all():
        raise ValueError(
            "No urban income observations are available for these filters."
        )

    # Count every requested combination, including absent API rows.
    requested = pd.MultiIndex.from_product(
        [countries, urban_classes, years],
        names=["geo", "deg_urb", "time"],
    )
    coverage = frame.set_index(
        ["geo", "deg_urb", "time"]
    )["value"].reindex(requested)

    missing = coverage[coverage.isna()].index.to_frame(index=False)

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "requested_observations": len(requested),
        "missing_observations": missing.to_dict("records"),
    })

    return frame

def fetch_urban_catalogue():
    """Load country, year, measure and unit options for urban income."""
    endpoint = (
        "https://ec.europa.eu/eurostat/api/dissemination/"
        "statistics/1.0/data/ilc_di17"
    )
    filters = {
        "freq": ["A"],
        "unit": ["EUR", "NAC", "PPS"],
        "statinfo": ["MED_EI", "MEAN_EI"],
        "deg_urb": ["DEG1", "DEG2", "DEG3"],
        "sex": ["T"],
        "age": ["TOTAL"],
    }
    params = {
        "lang": "EN",
        **filters,
        "geoLevel": "country",
        "sinceTimePeriod": 2003,
    }

    url = endpoint + "?" + urlencode(params, doseq=True)
    data, retrieved_at = _request_json(url)

    expected = set(filters) | {"geo", "time"}
    if set(data.get("id", [])) != expected:
        raise ValueError("Unexpected urban income catalogue dimensions.")

    frame = jsonstat_to_frame(data)

    for dim, codes in filters.items():
        if not frame[dim].isin(codes).all():
            raise ValueError(
                f"Urban income catalogue does not match the {dim} filter."
            )

    if not frame["time"].astype(int).ge(2003).all():
        raise ValueError(
            "Urban income catalogue contains years before 2003."
        )

    if frame.duplicated(
        ["geo", "deg_urb", "time", "statinfo", "unit"]
    ).any():
        raise ValueError("Duplicate urban income catalogue observations.")

    if frame.empty or frame["value"].isna().all():
        raise ValueError("No urban income observations are available.")

    frame.attrs.update({
        "request_url": url,
        "retrieved_at_utc": retrieved_at,
        "geo_level": "country",
    })
    return frame

def fetch_income_for_changes(
    countries, survey_years, indicator="MED_EI", unit="EUR",
    ages=None, sexes=None, *,
    include_previous_years=False, include_period_years=False,
):
    """Fetch selected years and the inputs for requested changes together."""
    if not isinstance(survey_years, (list, tuple)) or not survey_years:
        raise ValueError("Provide a non-empty list of survey years.")
    if any(type(year) is not int or year < 2003 for year in survey_years):
        raise ValueError("Use integer survey years from 2003.")

    selected_years = sorted(set(survey_years))
    annual_auxiliary_years = []
    out_of_scope_years = []
    if include_previous_years:
        previous_years = {year - 1 for year in selected_years}
        annual_auxiliary_years = sorted(
            year for year in previous_years
            if year >= 2003 and year not in selected_years
        )
        out_of_scope_years = sorted(year for year in previous_years if year < 2003)

    period_auxiliary_years = []
    if include_period_years:
        if len(selected_years) < 2:
            raise ValueError("Select at least two distinct survey years for a period.")
        period_auxiliary_years = [
            year for year in range(selected_years[0] + 1, selected_years[-1])
            if year not in selected_years
        ]

    auxiliary_years = sorted(set(annual_auxiliary_years + period_auxiliary_years))
    query_years = sorted(selected_years + auxiliary_years)
    frame = fetch_income(
        countries, indicator=indicator, unit=unit, ages=ages, sexes=sexes,
        survey_years=query_years,
    )
    selected_year_codes = [str(year) for year in selected_years]
    selected_mask = frame["time"].isin(selected_year_codes)
    frame["year_role"] = "Auxiliary"
    frame.loc[selected_mask, "year_role"] = "Selected"
    frame.attrs.update({
        "selected_survey_years": selected_years,
        "auxiliary_survey_years": auxiliary_years,
        "annual_auxiliary_survey_years": annual_auxiliary_years,
        "period_auxiliary_survey_years": period_auxiliary_years,
        "out_of_scope_previous_years": out_of_scope_years,
    })
    return frame


def fetch_income_with_previous_years(
    countries, survey_years, indicator="MED_EI", unit="EUR",
    ages=None, sexes=None,
):
    """Fetch selected survey years and their previous-year inputs together."""
    return fetch_income_for_changes(
        countries, survey_years, indicator=indicator, unit=unit,
        ages=ages, sexes=sexes, include_previous_years=True,
    )





