from eurostat_api import fetch_income_catalogue


catalogue = fetch_income_catalogue()

# Availability uses published values, including flagged observations.
available = catalogue.loc[catalogue["value"].notna()].copy()
years = sorted(available["time"].astype(int).unique())
countries = available[["geo", "geo_label"]].drop_duplicates()

print("Countries with observations:", len(countries))
print("Available survey years:", years[0], "to", years[-1])
print("Available observations:", len(available))

print("\nIndicators:")
print(
    available[["statinfo", "statinfo_label"]]
    .drop_duplicates().to_string(index=False)
)

print("\nUnits:")
print(
    available[["unit", "unit_label"]]
    .drop_duplicates().to_string(index=False)
)

sample = available.loc[
    available["statinfo"].eq("MED_EI") & available["unit"].eq("EUR")
]
coverage = (
    sample.groupby(["geo", "geo_label"])["time"]
    .agg(first_year="min", last_year="max", years_available="nunique")
    .reset_index()
)

print("\nCoverage examples: MED_EI / EUR / TOTAL / T")
print(
    coverage.loc[coverage["geo"].isin(["EL", "DE", "CH", "UK"])]
    .to_string(index=False)
)
print("\nRetrieved at UTC:", catalogue.attrs["retrieved_at_utc"])
print("Eurostat updated:", catalogue.attrs["eurostat_metadata"].get("updated"))