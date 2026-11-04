def build_year_summary(table, year, unit, measure, groups):
    """Describe the selected year using the same rows as the chart."""
    if unit == "NAC":
        return ["Select EUR or PPS for this comparison."]

    # Use the selected end year, even if an earlier year has more coverage.
    selected = table.loc[table["time"].eq(year)]
    available = selected.loc[selected["value"].notna()]
    lines = [
        f"{measure}, survey year {year}: "
        f"{len(available)} of {len(selected)} selected {groups} have data."
    ]

    missing_names = selected.loc[selected["value"].isna(), "series"]
    if not missing_names.empty:
        lines.append(
            f"No value for {', '.join(missing_names.astype(str))} in {year}."
        )

    if available.empty:
        lines.append("No comparison is available for this survey year.")
    elif len(available) == 1:
        row = available.iloc[0]
        lines.append(f"{row['series']}: {row['value']:,.2f} {unit}.")
    else:
        low = available["value"].min()
        high = available["value"].max()

        if low == high:
            lines.append(f"All available values are equal: {high:,.2f} {unit}.")
        else:
            # Include every tied group rather than choosing the first row.
            highest = available.loc[available["value"].eq(high), "series"]
            lowest = available.loc[available["value"].eq(low), "series"]
            lines.append(
                f"Highest: {', '.join(highest.astype(str))} ({high:,.2f} {unit})."
            )
            lines.append(
                f"Lowest: {', '.join(lowest.astype(str))} ({low:,.2f} {unit})."
            )

            gap = high - low
            gap_text = f"Difference between highest and lowest: {gap:,.2f} {unit}."
            if low > 0:
                gap_text += (
                    f" The highest value is {gap / low * 100:.1f}% "
                    "above the lowest."
                )
            lines.append(gap_text)

    # Flag counts refer to the full selected period, not only its final year.
    flags = table["obs_flag"].fillna("")
    flagged = flags.ne("")
    if flagged.any():
        codes = ", ".join(sorted(flags.loc[flagged].unique()))
        lines.append(
            f"Flagged rows across the selected period: {int(flagged.sum())} "
            f"({codes}). Consult the Flag column."
        )

    return lines