# Neon EVM Solana Healthcheck

A Prometheus exporter for monitoring Neon EVM and Solana blockchain infrastructure health, transaction success rates, and block synchronization.

## Features

- **Neon EVM Transaction Monitoring**: Track transaction counts, success rates, and failures across multiple networks
- **Block Lag Monitoring**: Monitor synchronization lag between Neon Proxy and Solana RPC endpoints  
- **Solana RPC Health Checks**: Monitor Solana node health and slot synchronization
- **Wallet Balance Monitoring**: Track Solana wallet balances across different networks
- **Multi-Network Support**: Support for mainnet, devnet, and custom networks
- **Redis State Persistence**: Maintain transaction state across restarts
- **Parallel Processing**: Concurrent processing for improved performance

## Architecture

The exporter runs as a Python service that:
1. Reads configuration from `config.yaml`
2. Connects to Redis for state persistence
3. Polls Solana RPC endpoints and Neon Proxy services
4. Exports metrics via HTTP endpoint for Prometheus scraping

## Configuration

Create a `config.yaml` file with the following structure:

```yaml
solana_services:
  - name: mainnet
    chain: mainnet
    program_id: NeonVMyRX5GbCrsAHnUwx1nYYoJAtskU1bWUo6JGNyG
    url: https://api.mainnet-beta.solana.com
  - name: devnet
    chain: devnet
    program_id: eeLSJgWzzxrqKv1UxtRVVH8FX3qCQWUs9QuAjJpETGU
    url: https://api.devnet.solana.com

neon_services:
  - name: neon-mainnet
    chain: mainnet
    url: https://neon-proxy-mainnet.solana.p2p.org
  - name: neon-devnet
    chain: devnet
    url: https://devnet.neonevm.org

wallets:
  - name: service-wallet
    value: DysZYNJHzPjT38hSE529i8xAdahUXmfjQCwKyHZZsx5F
    chain: mainnet

solana_servers:
  - group_name: mainnet-rpcs
    servers:
      - https://api.mainnet-beta.solana.com
      - https://rpc.ankr.com/solana
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |

## Metrics

### Neon EVM Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `neon_tx_count_total` | Counter | Total Neon EVM transactions processed | `chain`, `program_id`, `solana_url` |
| `neon_tx_fail_count_total` | Counter | Total failed Neon EVM transactions | `chain`, `program_id`, `solana_url` |
| `neon_tx_success_ratio` | Gauge | Success ratio of Neon EVM transactions (0-1) | `chain`, `program_id`, `solana_url` |

### Block Synchronization Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `neon_proxy_block_lag` | Gauge | Block lag between Neon Proxy and Solana RPC | `neon_name`, `solana_name`, `chain` |

### Solana Infrastructure Metrics

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `solana_health` | Gauge | Solana node health status (1=healthy, 0=unhealthy, >0=slots behind) | `address`, `server_group` |
| `solana_wallet_balance` | Gauge | Solana wallet balance in SOL | `address`, `name` |

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `neon_exporter_last_update_timestamp` | Gauge | Timestamp of last successful metrics update |

## Installation

### Docker Compose (Recommended)

```bash
git clone <repository-url>
cd solana_healthcheck
cp config.yaml.example config.yaml
# Edit config.yaml with your endpoints and wallets
docker-compose up -d
```

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REDIS_URL=redis://localhost:6379/0

# Run the exporter
python main.py
```

## Usage

1. **Configure endpoints**: Edit `config.yaml` with your Solana RPC endpoints, Neon Proxy services, and wallets
2. **Start services**: Run `docker-compose up -d`
3. **Verify metrics**: Check `http://localhost:9000/metrics`
4. **Configure Prometheus**: Add the exporter as a scrape target

### Prometheus Configuration

```yaml
scrape_configs:
  - job_name: 'neon-healthcheck'
    static_configs:
      - targets: ['localhost:9000']
    scrape_interval: 30s
```

## Monitoring Setup

### Key Alerts

```yaml
# Neon Proxy lag alert
- alert: NeonProxyHighLag
  expr: neon_proxy_block_lag > 100
  for: 5m
  labels:
    severity: warning

# Transaction failure rate alert  
- alert: NeonHighFailureRate
  expr: rate(neon_tx_fail_count_total[5m]) / rate(neon_tx_count_total[5m]) > 0.1
  for: 2m
  labels:
    severity: critical

# Exporter health alert
- alert: NeonExporterDown
  expr: time() - neon_exporter_last_update_timestamp > 120
  for: 2m
  labels:
    severity: critical
```

## Development

### Project Structure

```
├── main.py              # Main exporter application
├── config.yaml          # Configuration file (not in git)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container image definition
├── docker-compose.yaml  # Development environment
└── README.md           # This file
```

### Key Functions

- `monitor_neon_transactions()`: Processes Neon EVM transactions for all configured networks
- `healthcheck_block_lag()`: Compares block heights between Neon Proxy and Solana
- `restore_counters()`: Restores Prometheus counters from Redis state on startup
- `check_balance()`: Monitors wallet balances across networks

### State Management

The exporter uses Redis to maintain state:
- `neon_signatures_{chain}_{program_id}`: Processed transaction signatures
- `neon_failed_signatures_{chain}_{program_id}`: Failed transaction signatures

This ensures metrics continuity across restarts and prevents duplicate processing.

## Troubleshooting

### Common Issues

**Metrics not updating**:
- Check Redis connectivity
- Verify config.yaml syntax
- Ensure RPC endpoints are accessible

**High error rates**:
- Monitor RPC rate limits (429 errors)
- Check network connectivity
- Verify program IDs are correct

**Missing metrics**:
- Ensure chain parameters match between services and wallets
- Check Prometheus scrape configuration
- Verify endpoint URLs are correct

### Debug Mode

Enable debug logging by checking container logs:
```bash
docker-compose logs -f app
```

## License

MIT License - see LICENSE file for details. 