#!/usr/bin/env python

import time
import yaml
import signal
import requests
import sys
import os
import redis
import concurrent.futures

from prometheus_client import start_http_server, Gauge, Counter

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self,signum, frame):
    self.kill_now = True

# Prometheus metrics for Solana RPC and wallets
solana_health = Gauge("solana_health", "Solana node healthcheck", ["address", "server_group"])
solana_wallet_balance = Gauge("solana_wallet_balance", "Solana wallet balance", ["address", "name"])

# Get Redis URL from environment variable
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
r = redis.Redis.from_url(REDIS_URL)

# Get NEON_PROGRAM_ID and SOLANA_RPC from environment variables
NEON_PROGRAM_ID = os.environ.get('NEON_PROGRAM_ID', 'NeonVMyRX5GbCrsAHnUwx1nYYoJAtskU1bWUo6JGNyG')
SOLANA_RPC = os.environ.get('SOLANA_RPC', 'https://api.mainnet-beta.solana.com')

neon_tx_success_ratio = Gauge("neon_tx_success_ratio", "Success ratio of Neon EVM transactions")
neon_tx_count = Counter("neon_tx_count", "Total number of Neon EVM transactions")
neon_tx_fail_count = Counter("neon_tx_fail_count", "Total number of failed Neon EVM transactions")
neon_exporter_last_update_timestamp = Gauge("neon_exporter_last_update_timestamp", "Last successful update timestamp")

neon_proxy_block_lag = Gauge(
    "neon_proxy_block_lag",
    "Block lag between Neon Proxy and Solana RPC",
    ["neon_name", "solana_name", "chain"]
)

def exponential_backoff(base=5, factor=2, max_delay=300):
    """
    Generator for exponential backoff delays
    """
    delay = base
    while True:
        yield delay
        delay = min(delay * factor, max_delay)

def get_neon_transactions(limit=15):
    """
    Get recent Neon EVM transactions from Solana by program id
    """
    try:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [NEON_PROGRAM_ID, {"limit": limit}]
        }
        resp = requests.post(SOLANA_RPC, json=req, timeout=10)
        resp.raise_for_status()
        return resp.json().get('result', [])
    except Exception as e:
        print(f'get_neon_transactions error: {e}')
        return []

def check_transaction(signature):
    """
    Check if transaction is successful and get its blockTime
    """
    try:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [signature, {"encoding": "json"}]
        }
        resp = requests.post(SOLANA_RPC, json=req, timeout=10)
        resp.raise_for_status()
        tx = resp.json().get('result', None)
        if not tx:
            return None, None
        block_time = tx.get('blockTime', None)
        success = tx['meta']['err'] is None
        return success, block_time
    except Exception as e:
        print(f'check_transaction error: {e}')
        return None, None

def export_neon_metrics():
    """
    Export Neon EVM transaction metrics to Prometheus, using Redis for state
    """
    backoff = exponential_backoff()
    while True:
        try:
            txs = get_neon_transactions()
            print(f"[DEBUG] txs: {txs}", flush=True)
            new_sigs = []
            sig_blocktime_map = {}
            if txs:
                for tx in txs:
                    sig = tx['signature']
                    block_time = tx.get('blockTime')
                    sig_blocktime_map[sig] = block_time
                    if not r.sismember('neon_signatures', sig):
                        new_sigs.append(sig)
                if new_sigs:
                    total = len(new_sigs)
                    success_count = 0
                    fail_count = 0
                    for sig in new_sigs:
                        success, block_time = check_transaction(sig)
                        if success is None or block_time is None:
                            continue
                        submit_time = sig_blocktime_map.get(sig)
                        if submit_time and block_time:
                            if success:
                                success_count += 1
                            else:
                                fail_count += 1
                                r.sadd('neon_failed_signatures', sig)  # Save failed tx signature
                            r.sadd('neon_signatures', sig)
                    # Обновляем метрики после подсчёта
                    neon_tx_count.inc(success_count + fail_count)
                    neon_tx_fail_count.inc(fail_count)
                    if total > 0:
                        neon_tx_success_ratio.set(success_count / total)
            # В конце каждого успешного цикла обновляем timestamp
            neon_exporter_last_update_timestamp.set(time.time())
            time.sleep(30)
            backoff = exponential_backoff()  # reset backoff on success
        except Exception as e:
            print('export_neon_metrics error:', e)
            time.sleep(next(backoff))

def restore_counters():
    """
    Restore Prometheus counters from Redis state on exporter startup
    """
    processed_count = r.scard('neon_signatures')
    failed_count = r.scard('neon_failed_signatures')
    if processed_count > 0:
        neon_tx_count.inc(processed_count)
    if failed_count > 0:
        neon_tx_fail_count.inc(failed_count)

def healthcheck(server: str):
    """
    Check Solana node health using getHealth RPC method
    """
    try:
        request = {"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
        response = requests.post(server, json=request, timeout=10)
        resp_json = response.json()
        if "result" in resp_json and resp_json["result"] == "ok":
            return 1
        elif "error" in resp_json:
            data = resp_json["error"].get("data", {})
            if isinstance(data, dict) and "numSlotsBehind" in data:
                print(resp_json["error"]["message"])
                return data["numSlotsBehind"]
            else:
                print(resp_json["error"]["message"])
                return -1
        else:
            return -1
    except Exception as e:
        print(f'healthcheck error: {e}')
        return -1

def check_balance(wallet: str):
    """
    Get Solana wallet balance using getBalance RPC method
    """
    try:
        request = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet]}
        response = requests.post('https://api.mainnet-beta.solana.com', json=request, timeout=10)
        return int(response.json()["result"]["value"]) / 1000000000
    except Exception as e:
        print(f'check_balance error: {e}')
        return 0

def get_neon_block_number(neon_url):
    try:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_blockNumber",
            "params": []
        }
        resp = requests.post(neon_url, json=req, timeout=10)
        result = resp.json()["result"]
        # result — hex string, например '0x1a2b3c'
        return int(result, 16)
    except Exception as e:
        print(f"get_neon_block_number error: {e}")
        return None

def get_solana_block_number(solana_url):
    try:
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSlot",
            "params": [{"commitment": "confirmed"}]
        }
        resp = requests.post(solana_url, json=req, timeout=10)
        return int(resp.json()["result"])
    except Exception as e:
        print(f"get_solana_block_number error: {e}")
        return None

def healthcheck_block_lag(neon_services, solana_services):
    # Собираем все нужные пары (neon, solana) по chain
    pairs = []
    for neon in neon_services:
        neon_chain = neon.get("chain")
        neon_name = neon.get("name")
        neon_url = neon.get("url")
        if not (neon_chain and neon_name and neon_url):
            print(f"Invalid neon_service entry: {neon}")
            continue
        solana = next((s for s in solana_services if s.get("chain") == neon_chain and s.get("url") and s.get("name")), None)
        if not solana:
            print(f"No solana_service for chain {neon_chain}. solana_services: {solana_services}")
            continue
        solana_name = solana.get("name")
        solana_url = solana.get("url")
        pairs.append((neon_name, neon_url, solana_name, solana_url, neon_chain))

    def fetch_blocks(neon_url, solana_url):
        neon_block = get_neon_block_number(neon_url)
        solana_block = get_solana_block_number(solana_url)
        return neon_block, solana_block

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_pair = {
            executor.submit(fetch_blocks, neon_url, solana_url): (neon_name, solana_name, chain)
            for (neon_name, neon_url, solana_name, solana_url, chain) in pairs
        }
        for future in concurrent.futures.as_completed(future_to_pair):
            neon_name, solana_name, chain = future_to_pair[future]
            try:
                neon_block, solana_block = future.result()
                if neon_block is not None and solana_block is not None:
                    lag = solana_block - neon_block
                    print(f"[DEBUG] neon_name={neon_name}, solana_name={solana_name}, chain={chain}, neon_block={neon_block}, solana_block={solana_block}, lag={lag}", flush=True)
                    neon_proxy_block_lag.labels(
                        neon_name=neon_name,
                        solana_name=solana_name,
                        chain=chain
                    ).set(lag)
                else:
                    print(f"Block number unavailable for {neon_name} or {solana_name}")
            except Exception as e:
                print(f"Exception in block lag check for {neon_name}/{solana_name}: {e}")

def main():
    killer = GracefulKiller()
    import threading
    restore_counters()  # Restore counter from Redis before starting metrics export
    t = threading.Thread(target=export_neon_metrics, daemon=True)
    t.start()
    # Читаем config.yaml
    try:
        with open("config.yaml", "r") as yamlfile:
            data = yaml.load(yamlfile, Loader=yaml.FullLoader)
            print("Read successful", flush=True)
    except Exception as e:
        print(f"Failed to read config.yaml: {e}", flush=True)
        data = {"solana_servers": [], "wallets": [], "neon_services": [], "solana_services": []}
    while True:
        try:
            # Старая логика
            for server_group in data.get("solana_servers", []):
                for server in server_group.get("servers", []):
                    result = healthcheck(server)
                    solana_health.labels(address=server, server_group=server_group["group_name"]).set(result)
            for wallet in data.get("wallets", []):
                result = check_balance(wallet["value"])
                solana_wallet_balance.labels(address=wallet["value"], name=wallet["name"]).set(result)
            # Новая логика для neon_proxy_block_lag
            healthcheck_block_lag(data.get("neon_services", []), data.get("solana_services", []))
            if killer.kill_now:
                break
            time.sleep(10)
        except KeyboardInterrupt:
            sys.exit()
        except Exception as f:
            print('main error: ', f)

if __name__ == '__main__':
    start_http_server(9000)
    main()
