from real_income import calculate_real_change, fetch_greek_real_income


df = fetch_greek_real_income(
    start_survey_year=2020,
    end_survey_year=2024,
    indicator="MED_EI",
    age="TOTAL",
)

columns = [
    "geo", "age", "survey_year", "income_year",
    "nominal_income", "hicp", "income_flag", "hicp_flag",
]
print(df[columns].to_string(index=False))
print("\nJoined rows:", len(df))
print("Unmatched HICP rows:", df["hicp_match"].eq("left_only").sum())
print("Missing income values:", df["nominal_income"].isna().sum())
print("Missing HICP values:", df["hicp"].isna().sum())

result = calculate_real_change(df)
print(
    "\nCumulative changes for income years:",
    result["start_income_year"], "to", result["end_income_year"],
)
print(f"Nominal income change: {result['nominal_change_pct']:+.4f}%")
print(f"HICP change: {result['hicp_change_pct']:+.4f}%")
print(f"HICP-adjusted income change: {result['real_change_pct']:+.4f}%")
print("Flags:", result["flags"])

for name, metadata in df.attrs["sources"].items():
    print(f"\n{name} retrieved at UTC:", metadata["retrieved_at_utc"])
    print(f"{name} Eurostat updated:", metadata["eurostat_metadata"].get("updated"))