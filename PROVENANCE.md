# Provenance and source baseline

The staged source baseline is derived from the supplied Hornet3000 Wächter 1.6.0 source package. Its archive SHA-256 was verified on 2026-11-20 against the accompanying `SHA256SUMS.txt`: `ffb4040bf1facf2d08f880b73c06c3933f801e5de2a97a497bfabaa9ca9c007a`. The hardened 1.6.1 derivative archive was separately verified against its checksum file: `44ec3d919b5dcf668d12591814733d315916f42b5b1af3dbc225e8867094cf98`. The repository name BEEKEEPER3000 does not imply a clean-room rewrite or a new license for inherited code. See [the archive provenance audit](docs/ARCHIVE-PROVENANCE-AUDIT-2026-11-20.md).

Preserve the inherited GPL-3.0-or-later license and all upstream notices. Review LICENSES.md and THIRD_PARTY_NOTICES.md before redistribution. Do not add datasets, trained weights, photographs, audio, firmware binaries, or other third-party assets unless their exact source, license, and redistribution rights have been verified.

The Beekeeper-Monitor connector is new adapter code authored for this integration and targets the public event contract in simonthomas-ai/Beekeeper-Monitor. It intentionally sends metadata only.


## Upstream component review

The dated license and security register for optional upstream components is maintained at [docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md](docs/UPSTREAM-SECURITY-LICENSE-REGISTER-2026-11-20.md). It is an engineering evidence record and does not replace an artifact-level provenance or legal review.
