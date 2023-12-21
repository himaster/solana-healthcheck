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

solana_health = Gauge("solana_health", "Solana node healthcheck", ["address", "server_group"])
solana_wallet_balance = Gauge("solana_wallet_balance", "Solana wallet balance", ["address", "name"])

def healthcheck(server: str):
    request = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
    response = requests.post(server, json=request)

    if response.status_code == 200:
        #print(server + ' - ' + response.json()['result'])
        return 0
    elif 'numSlotsBehind' in response.json()['error']['data']:
        print(response.json()['error']['message'])
        return response.json()['error']['data']['numSlotsBehind']
    else:
        print(response.json()['error']['message'])
        return -1

def check_balance(wallet: str):
    request =   {"jsonrpc": "2.0", "id": 1, "method": "getBalance",
      "params": [
        wallet
      ]
    }
    response = requests.post('https://api.mainnet-beta.solana.com', json=request)

    return int(response.json()["result"]["value"])/1000000000

def main():
    killer = GracefulKiller()

    while True:
        try:
            for server_group in data["solana_servers"]:
                for server in server_group["servers"]:
                    result = healthcheck(server)
                    solana_health.labels(address=server, server_group=server_group["group_name"]).set(result)
            for wallet in data["wallets"]:
                result = check_balance(wallet["value"])
                solana_wallet_balance.labels(address=wallet["value"], name=wallet["name"]).set(result)
            if killer.kill_now:
                break
            time.sleep(5)
        except KeyboardInterrupt:
            sys.exit()
        except Exception as f:
            print('main error: ', f)            

if __name__ == '__main__':
    with open("config.yaml", "r") as yamlfile:
        data = yaml.load(yamlfile, Loader=yaml.FullLoader)
        print("Read successful")
    start_http_server(9000)
    main()
