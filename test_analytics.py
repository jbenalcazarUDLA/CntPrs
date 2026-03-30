import requests
import json

url = "http://127.0.0.1:8000/api/analytics/dashboard?start_date=2026-03-24&end_date=2026-03-24&time_slots="
try:
    response = requests.get(url)
    print("Status:", response.status_code)
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Error:", e)
