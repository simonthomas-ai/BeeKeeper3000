# Security and operational baseline

- Keep all services bound to loopback or a trusted private network by default.
- Use separate, randomly generated credentials for each service.
- Never commit secrets, camera credentials, personal data, private captures, audio, or GPS traces.
- Remote access requires a private VPN or HTTPS reverse proxy. Never expose plain-HTTP listeners directly to the public internet.
- The current bridge forwards metadata only and deliberately omits image, audio, and GPS data.
- The current monitor receiver validates and logs accepted events but does not yet persist them into the PWA dashboard.
- The reviewed source baseline does not provide a complete automatic retention/deletion workflow. Define and test retention before operational use.
- ONNX Runtime was unavailable in the checked build environment; AI inference must not be assumed active.
- Keep dependencies and model assets pinned and record their licenses and provenance.
- Security review and deployment-specific privacy assessment are release gates, not optional claims of certification.
