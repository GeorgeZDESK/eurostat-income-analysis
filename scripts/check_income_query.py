from eurostat_api import fetch_income


df = fetch_income(
    countries=["EL", "DE", "FR"],
    start_year=2022,
    end_year=2024,
    indicator="MED_EI",
    unit="EUR",
)

columns = ["geo", "geo_label", "time", "statinfo", "unit", "value", "obs_flag"]
preview = df[columns].sort_values(["geo", "time"])
preview = preview.rename(columns={"time": "survey_year"})
print(preview.to_string(index=False))

missing = df.attrs["missing_observations"]
print("\nRequested country-year pairs:", df.attrs["requested_observations"])
print("Available observations:", df["value"].notna().sum())
print("Missing country-year pairs:", len(missing))
print("Flagged observations:", df["obs_flag"].fillna("").ne("").sum())
print("Retrieved at UTC:", df.attrs["retrieved_at_utc"])
print("Eurostat updated:", df.attrs["eurostat_metadata"].get("updated"))

if missing:
    print("Missing pairs:", missing)