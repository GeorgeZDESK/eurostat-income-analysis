from eurostat_api import fetch_hicp


df = fetch_hicp(countries=["EL"], start_year=2019, end_year=2023)

columns = ["geo", "geo_label", "time", "unit", "coicop18", "value", "obs_flag"]
preview = df[columns].sort_values(["geo", "time"])
preview = preview.rename(columns={"time": "price_year"})
print(preview.to_string(index=False))

missing = df.attrs["missing_observations"]
print("\nRequested country-year pairs:", df.attrs["requested_observations"])
print("Available observations:", df["value"].notna().sum())
print("Missing country-year pairs:", len(missing))
print("Flagged observations:", df["obs_flag"].fillna("").ne("").sum())
print("Retrieved at UTC:", df.attrs["retrieved_at_utc"])
print("Eurostat updated:", df.attrs["eurostat_metadata"].get("updated"))

if missing:
    print("Missing combinations:", missing)