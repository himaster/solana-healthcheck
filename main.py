#!/usr/bin/env python

import time
import yaml
import requests

from pprint import pprint
from prometheus_client import start_http_server, Gauge

solana_health = Gauge("solana_health", "Solana node healthcheck", ["address"])

def healthcheck(server: str):
    request = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
    response = requests.post(server, json=request)

    if response.status_code == 200:
        pprint(response.json()['result'])
        return 0
    else:
        pprint(response.json()['error']['message'])
        return response.json()['error']['data']['numSlotsBehind']

with open("config.yaml", "r") as yamlfile:
    data = yaml.load(yamlfile, Loader=yaml.FullLoader)
    print("Read successful")

def main():
    while True:
        for server in data["solana_servers"]:
            result = healthcheck(server)
            solana_health.labels(address=server).set(result)
        time.sleep(5)

if __name__ == '__main__':
    start_http_server(9000)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
    except Exception as f:
        print('main error: ', f)
