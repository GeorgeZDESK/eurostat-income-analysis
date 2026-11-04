import pandas as pd

from eurostat_api import fetch_income


age_order = ["Y_LT18", "Y18-24", "Y25-49", "Y50-64", "Y_GE65"]

df = fetch_income(
    countries=["EL"],
    start_year=2022,
    end_year=2024,
    indicator="MED_EI",
    unit="EUR",
    ages=age_order,
)

preview = df[["geo", "age", "age_label", "time", "value", "obs_flag"]].copy()

# Display the published age groups in ascending age order.
preview["age"] = pd.Categorical(
    preview["age"], categories=age_order, ordered=True
)
preview = preview.sort_values(["age", "time"])
preview = preview.rename(columns={"time": "survey_year"})
print(preview.to_string(index=False))

missing = df.attrs["missing_observations"]
print("\nRequested age-year pairs:", df.attrs["requested_observations"])
print("Available observations:", df["value"].notna().sum())
print("Missing age-year pairs:", len(missing))
print("Flagged observations:", df["obs_flag"].fillna("").ne("").sum())
print("Retrieved at UTC:", df.attrs["retrieved_at_utc"])
print("Eurostat updated:", df.attrs["eurostat_metadata"].get("updated"))

if missing:
    print("Missing combinations:", missing)