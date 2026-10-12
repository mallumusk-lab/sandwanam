import requests
import json

url = "http://localhost:8001/add_collection/100-1"
headers = {
    "Content-Type": "application/json",
    "x-api-key": "12345"
}
data = {
    "amountPaid": 1111.0,
    "date": "2026-03-16",
    "transactionType": "addColl"
}

try:
    response = requests.post(url, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Error: {e}")
