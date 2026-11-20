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
