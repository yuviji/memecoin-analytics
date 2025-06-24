# import json
# addresses = []
# with open('logs.json', 'r') as f:
#     data = json.load(f)
#     for item in data['result']['value']:
#         addresses.append(item['uiAmount'])


# print(len(set(addresses)))
# print(len(addresses))


import requests

addresses = []
amounts = []

API_KEY = "8d686aaf-e5f0-4282-89ab-43f1348a6588"
url = "https://mainnet.helius-rpc.com/?api-key=" + API_KEY
payload = {
    "jsonrpc": "2.0",
    "id": "1",
    "method": "getTokenLargestAccounts",
    "params": ["9BB6NFEcjBCtnNLFko2FqVQBq8HHM13kCyYcdQbgpump"]
}
headers = {"Content-Type": "application/json"}

response = requests.request("POST", url, json=payload, headers=headers).json()

print(len(response['result']['value']))

for item in response['result']['value']:
    addresses.append(item['address'])
    amounts.append(item['uiAmount'])

print(len(set(addresses)))
print(len(set(amounts)))

print(sum(amounts))