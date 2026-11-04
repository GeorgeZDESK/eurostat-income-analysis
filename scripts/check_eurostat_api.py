"""Inspect one small Eurostat response before building the app adapter."""

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from eurostat_api import jsonstat_to_frame


endpoint = (
    "https://ec.europa.eu/eurostat/api/dissemination/"
    "statistics/1.0/data/ilc_di03"
)
params = {
    "lang": "EN",
    "freq": "A",
    "geo": "EL",
    "sex": "T",
    "age": "TOTAL",
    "statinfo": "MED_EI",
    "unit": "EUR",
    # These filters select survey years, not income reference years.
    "sinceTimePeriod": "2022",
    "untilTimePeriod": "2024",
}
url = endpoint + "?" + urlencode(params)
print("Request URL:", url)

try:
    with urlopen(url, timeout=30) as response:
        raw = response.read().decode("utf-8")
        print("HTTP:", response.status)
        print("Content-Type:", response.headers.get("Content-Type"))
except HTTPError as exc:
    detail = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
except (URLError, TimeoutError) as exc:
    raise SystemExit(f"Request failed: {exc}") from exc

print("Retrieved at UTC:", datetime.now(timezone.utc).isoformat(timespec="seconds"))
try:
    data = json.loads(raw)
except json.JSONDecodeError as exc:
    raise SystemExit("The response is not valid JSON.") from exc

if not isinstance(data, dict):
    raise SystemExit("Unsupported JSON response: expected an object.")
if "error" in data or "warning" in data:
    raise SystemExit(json.dumps(data, indent=2, ensure_ascii=False))
if data.get("class") != "dataset" or data.get("version") != "2.0":
    raise SystemExit("Unsupported response: expected a JSON-stat 2.0 dataset.")

# Keep cube indices, labels and complete flags untouched for inspection.
fields = ["class", "version", "label", "source", "updated", "id", "size",
          "dimension", "value", "status"]
report = {key: data.get(key) for key in fields}
report["status_field_present"] = "status" in data
print(json.dumps(report, indent=2, ensure_ascii=False))

df = jsonstat_to_frame(data)
columns = ["geo", "geo_label", "time", "statinfo", "unit", "value", "obs_flag"]
preview = df[columns].rename(columns={"time": "survey_year"})

print("\nDecoded observations:")
print(preview.to_string(index=False))
print("Rows:", len(df))
print("Missing values:", df["value"].isna().sum())
print("Flagged observations:", df["obs_flag"].fillna("").ne("").sum())