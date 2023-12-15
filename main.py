#!/usr/bin/env python

import time
import yaml
import signal
import requests

from prometheus_client import start_http_server, Gauge

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True

solana_health = Gauge("solana_health", "Solana node healthcheck", ["address"])

def healthcheck(server: str):
    request = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
    response = requests.post(server, json=request)

    if response.status_code == 200:
        print(server + ' - ' + response.json()['result'])
        return 0
    elif 'numSlotsBehind' in response.json()['error']['data']:
        print(response.json()['error']['message'])
        return response.json()['error']['data']['numSlotsBehind']
    else:
        print(response.json()['error']['message'])
        return -1

with open("config.yaml", "r") as yamlfile:
    data = yaml.load(yamlfile, Loader=yaml.FullLoader)
    print("Read successful")

def main():
    killer = GracefulKiller()

    while True:
        for server in data["solana_servers"]:
            result = healthcheck(server)
            solana_health.labels(address=server).set(result)
        if killer.kill_now:
            break
        time.sleep(5)

if __name__ == '__main__':
    start_http_server(9000)
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
    except Exception as f:
        print('main error: ', f)
