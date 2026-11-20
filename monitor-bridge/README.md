# Hornet3000 → Beekeeper-Monitor bridge

This adapter polls Hornet3000 `GET /api/events?limit=100` and forwards new detection metadata to the monitor's existing authenticated ingestion contract `POST /api/v1/events`. It does not transfer images, audio, GPS coordinates, API keys, or other location data. Species labels are prefixed `unverified_candidate:`; model confidence is not proof of species identity.

## Requirements and setup

- Node.js 20+; no third-party npm packages.
- Hornet3000 running locally with an API key configured.
- The `integrations/local_ingest.py` service from [Beekeeper-Monitor](https://github.com/simonthomas-ai/Beekeeper-Monitor) running on loopback port 8765.
- A separate random ingestion token of at least 24 characters. Never reuse the Hornet3000 API key.

Copy `.env.example` to `.env`, fill the values locally, then run the bridge with those environment variables loaded:

```bash
# In the Beekeeper-Monitor checkout, start its receiver:
VESPAGUARD_INGEST_TOKEN='your-long-random-token' python -m integrations.local_ingest

# In this repository, after loading monitor-bridge/.env:
cd monitor-bridge
npm test
npm start
```

The receiver binds to `127.0.0.1:8765`. The bridge saves forwarded event IDs to a private local state file. It polls the most recent 100 source events; first start therefore imports at most that recent window.

## Integration boundary

The monitor receiver currently validates and logs metadata; it does **not** yet persist received events into the PWA's IndexedDB observation list or render them in the dashboard. This is a transport adapter, not a complete visible dashboard integration. A follow-up change in the Beekeeper-Monitor repository is still required for persistence/UI, followed by an end-to-end deployment test.

For non-loopback deployment, use HTTPS and a private VPN/reverse proxy. Never expose either plain-HTTP service directly to the public internet.
