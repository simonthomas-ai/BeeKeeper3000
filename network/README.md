# Network reference implementation

This folder contains the first portable, dependency-free software building block for multi-station bearing triangulation.

- `triangulation.py`: weighted least-squares intersection of geographic bearings.
- `test_triangulation.py`: synthetic tests for a known target, invalid geometry and backwards rays.
- `protocol-v1.schema.json`: canonical event envelope for future LoRa/IP/Freenet adapters.

Run locally with Python 3.10+:

```sh
python -m unittest discover -s network -p 'test_*.py' -v
```

The solver is a search-area estimator, not an automatic nest confirmation. It requires at least three independent, time-compatible bearings and rejects weak geometry. Production deployment still requires calibration, real-world error budgets, signature/key management, privacy controls and field validation.

LoRa adapters should encode only compact metadata; never send images/audio over LoRa. Freenet is an optional IP peer-to-peer synchronization layer, not a LoRa radio protocol.
