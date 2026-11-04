from eurostat_api import fetch_urban_income


def main():
    frame = fetch_urban_income(
        countries=["EL"],
        start_year=2022,
        end_year=2024,
        indicator="MED_EI",
        unit="EUR",
    )

    table = frame.rename(columns={"time": "survey_year"})
    columns = [
        "geo",
        "deg_urb",
        "deg_urb_label",
        "survey_year",
        "value",
        "obs_flag",
    ]
    table = table.sort_values(
        ["geo", "deg_urb", "survey_year"]
    )

    print("Median equivalised income | EUR | All ages | Total sex")
    print(table[columns].to_string(index=False))

    flagged = frame["obs_flag"].fillna("").str.strip().ne("")

    print(
        "\nRequested country-area-year combinations:",
        frame.attrs["requested_observations"],
    )
    print(
        "Available observations:",
        int(frame["value"].notna().sum()),
    )
    print(
        "Missing combinations:",
        len(frame.attrs["missing_observations"]),
    )
    print("Flagged observations:", int(flagged.sum()))
    print("Retrieved at UTC:", frame.attrs["retrieved_at_utc"])
    print(
        "Eurostat updated:",
        frame.attrs["eurostat_metadata"].get("updated"),
    )


if __name__ == "__main__":
    main()