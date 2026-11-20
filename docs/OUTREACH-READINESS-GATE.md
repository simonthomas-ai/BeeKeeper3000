# BeeKeeper3000 outreach readiness gate

**Current state: HOLD — internal preparation only.**  
**External outreach is not authorised.** This gate defines when the project may be considered ready for a separate owner decision. Passing it does not itself authorise messages, registrations, posts or partner contact.

## Phase model

| Phase | Permitted activity | Not permitted |
|---|---|---|
| 0 — Preparation (current) | Public-source partner research, deduplication, project-readiness tracking, technical planning | Messages, contact drafts, DMs, posts, submissions, invitations, registrations or recruitment |
| 1 — Build and verify | Engineering, security, licensing, tests, documentation, internal demonstrations | External recruitment or claims of field readiness |
| 2 — Closed technical pilot | Only after separate approval: invite a small, named pilot cohort; written consent and pilot protocol | Broad public campaign, unreviewed data federation, official-sounding species or nest claims |
| 3 — Public partner outreach | Only after a separate explicit owner decision: approved communications and controlled distribution | Automated mass messaging, scraping or unsolicited repeated contact |
| 4 — Regional / EU expansion | Only after pilot evidence, governance and country-specific review | Assuming cross-border legal permission, coverage or authority integration |

The weekly Partner-Radar stays in Phase 0 until the owner explicitly changes the phase. It must continue research and report readiness gaps, but must not prepare outreach copy, contact lists for bulk distribution or send any communication.

## Mandatory technical and governance gates

A readiness review must link to objective evidence in the repositories or test records. Documentation statements alone do not count as proof of a working feature.

### A. Software delivery and installation
- [ ] Clean checkout and reproducible installation tested on supported Windows and Linux targets.
- [ ] Start, health-check, stop, upgrade, rollback and uninstall procedures tested.
- [ ] Supported hardware / OS / Python / Node versions documented.
- [ ] Resource use, logs, disk limits and service restart behaviour measured.
- [ ] No secrets, private keys, credentials or sensitive media in repositories or CI logs.

### B. Camera and detection quality
- [ ] Real camera ingestion runs locally on declared target hardware.
- [ ] Detector output is connected to the source event journal through a documented adapter.
- [ ] Evaluation uses a licensed, provenance-checked, independently reviewed dataset with separate train / validation / test sets.
- [ ] Report per-class precision, recall, false-positive rate, false-negative rate, calibration and confidence intervals; include confusion between Vespa velutina, Vespa crabro, wasps, bees and bumblebees.
- [ ] Expert review remains distinct from machine predictions; uncertain cases stay candidates.
- [ ] No public accuracy claim without reproducible measured results.

### C. Network, radio and triangulation
- [ ] MeshCore firmware, board, regional radio settings and adapter versions are pinned and reviewed.
- [ ] At least two-node and multi-station hardware tests record packet loss, latency, retry behaviour, power use and reconnect/replay behaviour.
- [ ] Three-or-more-station bearing experiments use known ground truth, clock synchronisation, calibration and documented geometry.
- [ ] Search-area uncertainty is validated against independent field measurements; outputs remain hypotheses, not confirmed nests.
- [ ] LoRa / MeshCore / Meshtastic / IP / any future Freenet adapter remain separate, optional transports with explicit compatibility and licence records.
- [ ] No claim of nationwide coverage without a measured coverage study.

### D. Data, privacy and security
- [ ] Data-flow diagram and threat model reviewed.
- [ ] Data-controller / processor responsibilities, purpose, lawful basis, consent where applicable, retention, deletion, export, access and incident handling documented for the real deployment.
- [ ] Public, trusted-network, expert and operator access are separated and tested.
- [ ] Exact private apiary coordinates, home locations, raw images, audio, camera URLs and credentials are excluded from public / radio payloads by default.
- [ ] Backup and restore drills cover both databases, bridge state, key recovery, retention and deletion semantics.
- [ ] Security checks, dependency / advisory review, SBOM and secret scanning are green and current.
- [ ] Cross-border sharing has a country-specific legal and operational review before activation.

### E. Licences, provenance and operations
- [ ] Inherited source baseline, complete authoritative licence texts, copyright notices and redistribution rights are resolved.
- [ ] Direct and transitive dependencies, firmware, models, datasets, photographs, audio, map tiles and generated artefacts have separate provenance and licence records.
- [ ] CI gates reject known vulnerable dependencies and unreviewed assets.
- [ ] Operator handbook, troubleshooting guide, support boundary, upgrade policy and responsible-maintainer process exist.
- [ ] Official reporting routes and competent authorities are mapped per country; BeeKeeper3000 is clearly described as complementary, not an official reporting service.

### F. Pilot evidence
- [ ] Closed pilot protocol defines scope, participants, station roles, safety, consent, data handling, exit and incident procedures.
- [ ] At least three independent apiaries or stations complete a documented pilot installation and operation cycle.
- [ ] Source-to-bridge-to-Monitor end-to-end tests pass through outages, restarts, backlog recovery and deletion/export checks.
- [ ] A real pilot report documents errors, limitations, costs, maintenance burden and unresolved risks.
- [ ] Independent expert / research review is recorded where species or nest-location claims are evaluated.

## Decision rule

1. Keep Phase 0 active while any critical gate is incomplete.
2. Label each item **verified**, **in progress**, **blocked** or **not applicable**, with a direct evidence link and review date.
3. Never infer completion from a merged documentation-only PR or green synthetic unit tests.
4. When all critical gates have evidence, the Partner-Radar may report **readiness review requested**. It must not switch phase or produce outreach drafts.
5. Only a separate explicit instruction from the project owner may activate Phase 2 or Phase 3.
6. Even after activation, every external communication must be individually approved; no bulk, unsolicited or autonomous contact.

## Current known hold reasons

Based on the publicly documented repository boundary, the project still has open dependencies on:
- a real camera / detector producer connected to the source API;
- independently measured and expert-reviewed model performance;
- MeshCore multi-node hardware and field validation;
- a validated field triangulation protocol;
- complete source and asset licensing clearance;
- end-to-end backup / restore and operational acceptance;
- privacy and governance review for the actual deployment.

Update this list only when new evidence is checked. This file is an engineering readiness checklist, not a legal opinion or certification.


## Evidence snapshot — 20 November 2026

This snapshot distinguishes **software tests** from **field acceptance**. A green synthetic test proves only the tested software path; it does not prove camera classification, radio range, biological accuracy, privacy compliance or operational readiness. These statuses do not change Phase 0 and do not authorise outreach.

| Area | Current evidence status | Verified in software | Still required before field use |
|---|---|---|---|
| Station installation and operations | **IN PROGRESS** | Windows/Linux launch and backup tooling is present; the read-only `scripts/station_doctor.py` checks repository layout, runtime versions, local authenticated APIs, cursor safety and optional model/hardware preflight. CI validates scripts and launchers. | Clean install/upgrade/rollback/uninstall runs on real supported Windows and Linux machines; resource, log, restart and failure measurements. |
| Camera and detector pipeline | **PARTIAL — transport path tested** | `LocalCameraRuntime`, persistent SQLite outbox, Source API client and ONNX adapter are present. The end-to-end Monitor test drives 205 synthetic frames through the real camera runtime and outbox. | Physical camera tests on target hardware and a cleared, real ONNX model with production camera configuration. The end-to-end detector in that test is deliberately synthetic. |
| Detection quality | **BLOCKED** | Seven-class training schema, per-image provenance gate, annotation validator and candidate-source metadata queues exist. | A lawful, expert-reviewed, independently split image corpus; trained and hashed model; per-class precision/recall, confusion matrix, false positives per station-day, false negatives, calibration, confidence intervals and independent field set. No model accuracy has been established. |
| Monitor connection | **SOFTWARE E2E VERIFIED; FIELD USE NOT VERIFIED** | 205 synthetic camera events passed through runtime → durable outbox → authenticated source API → cursor-aware bridge → authenticated Monitor receiver → SQLite. Restart and replay deduplication are asserted; image, audio and exact coordinates are absent from the transmitted metadata. | A deployed station using a real detector and camera, outage/backlog recovery on target hardware, real monitoring and operator acceptance. |
| MeshCore radio | **SOFTWARE PROTOCOL TESTED; HARDWARE BLOCKED** | Signed protocol, receiver and optional hardware probe are covered by software tests. The probe defaults to dry run; connect-only mode transmits nothing. | Compatible physical radios/firmware, a second receiver, signed remote receipt, packet loss/latency/retries/power and legal regional radio review. Local send success is not remote reception. |
| Bearing triangulation | **NUMERICAL TOOLING PRESENT; FIELD VALIDATION BLOCKED** | Solver, uncertainty ellipse, synthetic geometry tests and confidential known-target field-report tooling exist. | At least 30 surveyed known-target trials across the deployment range, device/mount calibration, clock validation, independent uncertainty-coverage review and geography-specific validation. |
| Licences, security and privacy | **PARTIAL** | Source/asset registers, CC0 and exact CC BY 4.0 per-file image gate, dependency/SBOM workflows, CodeQL, metadata-only discovery and sanitized image intake are present. The importer removes EXIF, stores source and sanitized hashes, and leaves all candidates unreviewed. | Complete inherited-source/copyright baseline and third-party asset clearance; deployment-specific data-flow/threat/privacy review; controller/processor roles, lawful basis, retention/deletion, access, incident process and cross-border review. CodeQL success is not a legal or GDPR certification. |
| Backup, restore and pilot | **SOFTWARE BACKUP TOOLING PRESENT; OPERATIONAL PILOT BLOCKED** | Source-journal and Monitor database backup modules, Windows backup runner, integrity checks, SHA-256 manifest and automated restore tests exist. | Real restore drill on the intended station and databases, key recovery, deletion/retention verification, outage recovery and at least three independent apiary/station pilot installations with signed operator evidence. |

### Evidence links for this snapshot

- [Read-only station preflight](STATION-DOCTOR.md), added in [BeeKeeper3000 PR #63](https://github.com/simonthomas-ai/BeeKeeper3000/pull/63), then security-hardened in [PR #64](https://github.com/simonthomas-ai/BeeKeeper3000/pull/64).
- [MeshCore connect-only / single-packet probe](../network/meshcore/HARDWARE-PROBE.md), [PR #61](https://github.com/simonthomas-ai/BeeKeeper3000/pull/61).
- [Triangulation measurement limits](../network/TRIANGULATION-VALIDATION.md) and [known-target field report protocol](../network/TRIANGULATION-FIELD-REPORT.md).
- [Camera runtime → Monitor end-to-end test](https://github.com/simonthomas-ai/Beekeeper-Monitor/pull/52): 205 synthetic events; the detector fixture is not an accuracy benchmark.
- [Sanitized authorized-image import](https://github.com/simonthomas-ai/Beekeeper-Monitor/pull/53): EXIF removal and hash/provenance controls; candidate images remain unapproved for training.
- [Source journal backup/restore](https://github.com/simonthomas-ai/BeeKeeper3000/pull/43) and [Windows station backup runner](https://github.com/simonthomas-ai/BeeKeeper3000/pull/45).

### Priority order for the next build cycle

1. Run the station doctor and clean-install/rollback protocol on the actual target PC, without exposing credentials or private camera URLs.
2. Connect a real camera to the local runtime and acquire a lawful, expert-reviewed Vespa velutina dataset; do not train until every image clears the per-file provenance and annotation gates.
3. Measure model quality on an independent test set before connecting its predictions to operational alerts.
4. Run MeshCore with two physical nodes, then controlled known-target triangulation trials; collect remote receipts and field evidence.
5. Perform a restore drill from the generated station backup and verify actual deletion/retention behavior.
6. Complete the deployment-specific privacy, license and support review before inviting any pilot participant.

All external activity remains blocked. Passing this evidence checklist can only trigger an internal readiness review request; it cannot change the phase or send communications.
