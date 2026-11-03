def merge_hicp(income, hicp, keys):
    """Left-join prepared income and HICP tables using explicit key columns."""
    for name, data in [("Income", income), ("HICP", hicp)]:
        if data[keys].isna().any().any():
            raise ValueError(f"{name}: missing merge keys")

    # Each HICP key must identify at most one price observation.
    merged = income.merge(
        hicp,
        on=keys,
        how="left",
        validate="many_to_one",
        indicator=True
    )

    # Report absent matches while retaining all income rows.
    unmatched = merged.loc[
        merged["_merge"].eq("left_only"), keys
    ].drop_duplicates()

    print(f"HICP merge: {len(merged)} rows; {len(unmatched)} unmatched keys")
    if not unmatched.empty:
        print(unmatched.to_string(index=False))

    return merged.drop(columns="_merge")