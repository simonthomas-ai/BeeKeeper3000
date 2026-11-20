# Security notes

- Keep Hornet3000 and monitor ingestion bound to loopback where possible.
- Set separate, random API credentials. Never commit .env files, tokens, camera passwords, private captures, GPS traces, or audio.
- The bridge forwards event metadata only; it does not forward images, audio, or GPS.
- Use HTTPS and a private VPN/reverse proxy for any remote connection. Do not expose the plain-HTTP listeners to the public internet.
- The current source baseline has no complete automated retention/deletion workflow. Review storage and retention before operational use.
- Report security issues privately to the repository maintainer; do not publish credentials or exploitable personal data in issues.
