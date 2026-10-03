# Crypto Derivatives Analyzer

Option-chain and Greeks analysis for **Bitcoin (BTC)** and **Ethereum (ETH)**.

## Providers

- **Deribit**: live crypto options, expiries, IV, OI, volume, bid/ask and market prices.
- **QuickNode**: optional BTC/Ethereum blockchain RPC connectivity and block-health metadata.

QuickNode does not provide the crypto options chain itself, so the options market data remains on Deribit.

## Run

```bash
python -m pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open `http://127.0.0.1:8000`.

## Configuration

Set `DERIBIT_URL` if using another Deribit-compatible endpoint. QuickNode URLs are optional and are only used for blockchain health metadata.

## Greeks

Select one or more expiries with the expiry checkboxes. For each expiry, the live chain returns the nearest available ATM strike and available CE/PE OTM strikes from that expiry's actual option contracts. The **OTM strikes** setting controls how many strikes beyond ATM are included on each side (5, 10, 15, or 20); when fewer contracts are available, the chain limits the selection to those available. Greeks aggregate the selected expiry tables while calculating each expiry's strike set independently.

The option-chain view displays ATM and OTM CE/PE contracts for each selected expiry, including live bid/ask, LTP, volume, OI, and Greeks. The existing live-chain and Greeks endpoints are used; the live-chain endpoint includes selection metadata in addition to its complete chain rows.

Historical option-chain mode is not exposed for BTC/ETH yet; live mode is used for the current integration.
