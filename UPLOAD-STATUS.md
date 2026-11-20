# Upload and integration status

- The new GitHub repository has been initialized.
- The Monitor adapter source and setup documentation are being published here.
- The adapter maps Hornet3000 events to the existing Beekeeper-Monitor authenticated ingestion schema and omits image/audio/GPS data.
- The Beekeeper-Monitor receiver currently validates and logs events but does not yet persist them into the PWA or display them in the dashboard. Full end-to-end UI integration is not complete.
- The original source baseline remains Hornet3000 Wächter 1.6.0; this is not a complete validated multi-species product.
- No trained model weights/datasets are included; ONNX Runtime, camera fleet operation, radio/Freenet, notification delivery, and field accuracy require separate validation.
- Privacy retention/deletion implementation and complete SBOM/license audit remain release gates.
