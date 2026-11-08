from urllib.parse import urlencode
from urllib.request import urlopen
import json
import sys
import pandas as pd
from eurostat_api import fetch_income, jsonstat_to_frame


params = {
    "lang": "EN",
    "freq": "A",
    "geo": "EL",
    "sex": ["F", "M"],
    "age": "TOTAL",
    "statinfo": "MED_EI",
    "unit": "EUR",
    "time": 2024,
}
query = urlencode(params, doseq=True)

print(query)
print(type(query))

endpoint = (
    "https://ec.europa.eu/eurostat/api/dissemination/"
    "statistics/1.0/data/ilc_di03"
)

url = endpoint + "?" + query
print(url)

with urlopen(url, timeout=30) as response:
    print("Response type:", type(response))
    print("HTTP status:", response.status)
    data = json.load(response)

print("Parsed type:", type(data))
print("Top-level keys:", data.keys())
print("Source:", data["source"])
print("Dimensions:", data["id"])
print("Income values:", data["value"])

print("Sizes:", data["size"])
print("Sex metadata:", data["dimension"]["sex"])
sex_metadata = data["dimension"]["sex"]
sex_category = sex_metadata["category"]
sex_index = sex_category["index"]

position = sex_index["F"]
value_key = str(position)
female_median = data["value"][value_key]

print("Female median (EUR):", female_median)
dimensions = data["dimension"]

for name in data["id"]:
    metadata = dimensions[name]
    categories = metadata["category"]
    print(name, categories)

print("JSON-stat class:", data["class"])
print("JSON-stat version:", data["version"])
print("Status field present:", "status" in data)
print("Observation flags:", data.get("status"))

print("Python:", sys.version)
print("pandas:", pd.__version__)

frame = jsonstat_to_frame(data)

columns = [
    "freq", "age", "sex", "statinfo", "unit", "geo", "time",
    "value", "obs_flag",
]

print("Frame type:", type(frame))
print(frame.to_string(columns=columns, index=False))
old_key = ["geo", "age", "time"]
full_key = data["id"]

old_mask = frame.duplicated(subset=old_key, keep=False)
full_mask = frame.duplicated(subset=full_key, keep=False)

print("Old key mask:")
print(old_mask)

print("Full key mask:")
print(full_mask)

income = fetch_income(
    ["EL"], 2024, 2024,
    indicator="MED_EI", unit="EUR",
    ages=["TOTAL"], sexes=["F", "M"],
)

print("Parameterized API result:")
print(income.to_string(columns=columns, index=False))




