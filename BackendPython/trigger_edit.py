import requests
import json

url = "http://localhost:8000/edit_loan/SAN1L1"
headers = {
    "x-api-key": "12345",
    "Content-Type": "application/json"
}
data = {
    "principleAmount": "0",
    "transactionType": "modify"
}

response = requests.post(url, headers=headers, json=data)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
