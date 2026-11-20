# Community and partner participation plan (Germany / EU)

**Status:** internal preparation only. Do not contact, invite, publish, recruit or distribute until the readiness gate is passed and the project owner explicitly authorizes outreach. The prospect register is not evidence of endorsements or signed partnerships.  
**Project:** BeeKeeper3000 / Beekeeper-Monitor  
**Purpose:** recruit independent beekeepers, volunteer observers, regional associations, biodiversity groups and research partners for a privacy-preserving, open and locally operable monitoring network for *Vespa velutina*.

## Operating mode: preparation only

The current phase is **internal preparation**. This document is a research and planning aid, not permission to start external communication. Maintain public-source partner research, deduplicate organisations, verify published organisational contact routes and track project readiness. Do not send or submit emails, forms, messages, posts, newsletters, invitations or event registrations. Do not ask partner organisations to circulate material. Dormant communication examples in `community/OUTREACH-KIT.md` are not approved for use. Moving to external outreach requires a separate explicit instruction from the project owner after the readiness gate in [OUTREACH-READINESS-GATE.md](OUTREACH-READINESS-GATE.md) is reviewed.

## 1. What the project offers

BeeKeeper3000 should be presented as a complementary, open technical toolkit—not as a replacement for official species reporting, expert identification or statutory management.

- A local-first station runtime and event journal, with owner-controlled data and replaceable camera / inference / radio adapters.
- A documented metadata path into Beekeeper-Monitor; images, audio, exact GPS and credentials are not transmitted by default.
- Optional station-to-station communications and bearing experiments, kept separate from the public sighting feed.
- A reproducible way to validate detections, station bearings, uncertainty and data provenance.
- A low-barrier path for private beekeepers to test one station without joining a nationwide service.

**Do not claim:** a validated Vespa velutina AI model, nationwide LoRa coverage, guaranteed nest location, expert determination by AI, official authority status, or full GDPR compliance. A signature proves control of a key, not the insect species. Triangulation outputs are search hypotheses until independently checked in the field.

## 2. Priority public partner prospects

The following organisations and public project contacts are plausible first conversations because their published work or remit directly overlaps with beekeeping, Asian-hornet monitoring, citizen science or invasive-species data. They have **not** confirmed interest or endorsed BeeKeeper3000. Contact only through their published organisational channels.

| Priority | Prospect / public route | Why relevant | First ask |
|---|---|---|---|
| Germany 1 | [Deutscher Imkerbund (D.I.B.)](https://deutscherimkerbund.de/kontakt/) — info@imkerbund.de; [member associations](https://deutscherimkerbund.de/mitgliedsverbaende/) | National umbrella and regional association distribution | Request a technical presentation slot and permission to share a pilot call with interested Landesverbände |
| Germany 1 | [Deutscher Berufs- und Erwerbsimkerbund (DBIB)](https://berufsimker.de/kontakt/) — cooperation contact listed as Thorsten Wilkens, thorsten.wilkens@berufsimker.de; general mail@berufsimker.de | Professional apiaries, practical deployment and field feedback | Recruit 2–3 professional apiaries for a clearly bounded pilot |
| Germany 1 | [Projekt VELUTINA contact overview](https://www.velutina.de/kontakt-uebersicht/) | Public regional directory of volunteer hornet / wasp advisers and beekeepers | Ask for independent feedback on species-verification workflow and regional pilot referral |
| Germany 1 | [Velutina Netzwerk Niederrhein e.V.](https://velutina-netzwerk-niederrhein.de/vespa-velutina-melden/) | Regional volunteer network in NRW, near the initial pilot geography | Invite a local demonstration; coordinate with official reporting channels rather than duplicate them |
| EU 1 | [EASIN / European Commission JRC – contribute](https://easin.jrc.ec.europa.eu/easin/Contribute) — JRC-EASIN@ec.europa.eu | Accepts enquiries from projects and organisations about data-partner routes and geospatial information | Ask for the appropriate data-partner route and metadata requirements; do not send personal or precise private location data unsolicited |
| EU 1 | [INBO / Vespa-Watch](https://www.vlaanderen.be/inbo/en-GB/projects/vespa-watch-invasiemonitoring-van-aziatische-hoornaar-met-hobbyimkers-en-het-publiek-evinbo) — project contact route vespawatch@inbo.be | Established citizen-science monitoring with beekeepers and public participation; project records name Jasmijn Hillaert as project lead | Ask for a technical exchange on interoperability, data quality and complementary station telemetry |
| EU 2 | [European Beekeeping Association (EBA)](https://ebaeurope.eu/members/) — eba@ebaeurope.eu | Publishes member organisations across multiple European countries, including the D.I.B. | Request circulation to member organisations and identify one cross-border pilot partner |
| EU 2 | [BeeLife European Beekeeping Coordination](https://www.bee-life.eu/become-a-member) — info@bee-life.eu | Publicly states it represents beekeeper / farmer associations in 12 EU countries | Ask whether a non-commercial technical pilot or webinar could be relevant to members |
| EU 2 | [Vespa-Alert Belgium](https://www.vespa-alert.org/eng/vespa-alert-non-profit.php) | Citizen-led non-profit focused on Belgian Asian-hornet awareness, monitoring and coordination | Offer an interoperability discussion; avoid building a competing reporting silo |

**Named public expert lead:** the INBO project record identifies Jasmijn Hillaert as project leader for the Vespa-Watch expansion. Approach through the published project contact route, not private channels. A public role is a relevant lead, not evidence that the person wishes to join.

## 3. Regional and European rollout

### Stage A — local/private pilot (first 60–90 days)
1. Recruit 3–5 voluntary apiaries in one compact region (preferably NRW / Lower Rhine first).
2. Each participant owns their station, camera, local database and credentials. No compulsory cloud account.
3. Begin with manual photo review and metadata-only events; do not activate autonomous species claims.
4. Test a single local MeshCore link only after checking device / firmware compatibility and lawful radio configuration.
5. Record time synchronisation, camera field of view, station calibration, packet loss, false positives and operator effort.
6. Use at least three independent, geometrically useful bearings for triangulation experiments. Mark all outputs as search hypotheses; have a qualified person verify in the field.
7. Participants can stop sharing, export their own records and request deletion from systems under project control.

### Stage B — Germany
- Invite regional Imkervereine and Landesverbände through D.I.B. and DBIB channels.
- Build a directory of state reporting portals and regional expert routes. Link to them; do not silently copy their data.
- Offer short association webinars, local apiary demonstrations and a one-page pilot brief.
- Publish aggregate coverage only where there are enough stations and contributors to avoid re-identification.
- Keep official sightings reporting with the responsible state portals / authorities. BeeKeeper's own dataset is complementary and clearly labelled.

### Stage C — EU interoperability
- Start with neighbouring countries with active Asian-hornet monitoring and published citizen-science work (Belgium / Flanders and France are natural first research conversations).
- Use language-neutral event fields, UTC timestamps, explicit taxon status, source provenance, license metadata and uncertainty fields.
- Map country-specific reporting portals and legal / data-controller responsibilities before enabling cross-border transfers.
- Ask EASIN about its formal data-partner process. Do not assume that an informal API or direct upload is available.
- Keep each country's official reporting workflow intact. Do not publish precise nest coordinates or apiary coordinates to a public map.

### Stage D — private and community use
- A private beekeeper can run a station locally and keep all raw images and exact locations on their own equipment.
- Sharing is opt-in: default to species candidate, coarse region, observation time bucket and station pseudonym.
- A regional group can operate its own relay / coordinator and choose what metadata to federate.
- Research or authority partners can receive more precise data only under a documented purpose, access agreement, retention schedule and lawful basis.

## 4. Participation levels

1. **Observer:** submits a suspected sighting through the relevant official portal and optionally helps review public project documentation.
2. **Apiary pilot:** tests a local camera / station and contributes anonymised quality metrics.
3. **Regional coordinator:** onboards voluntary stations, checks operating procedures and routes reports to competent local authorities.
4. **Expert reviewer:** reviews species identification and nest evidence; AI scores remain advisory.
5. **Research / authority partner:** defines data quality, exchange schema, validation and evaluation requirements.
6. **Developer / maker:** contributes transport adapters, installer improvements, tests, translations or documentation.

No one must buy hardware or provide exact hive / home coordinates to join a discussion.

## 5. Repeatable outreach loop

This loop is currently **research-only**. Its external communication steps are future-stage procedures and are not authorised now. The pilot-interest issue form is retained only at `community/dormant-templates/pilot-interest.yml`; it is deliberately not enabled as a public GitHub issue template. Do not publish or activate it before the readiness gate and a separate owner decision.

Run a weekly discovery and review cycle:

1. Find new public associations, clubs, beekeeper events, research projects, funding calls and citizen-science initiatives.
2. Verify that each source is current; record the source URL, date checked, public contact route and why it is relevant.
3. Deduplicate organisations and contacts against the existing partner register.
4. Score relevance, reach, technical fit, geographic fit and evidence of active Vespa velutina work.
5. Prepare one tailored invitation per organisation; do not mass-mail or scrape private addresses.
6. A human reviews and sends each message. Record only organisation, public role, public contact channel, date, response and opt-out / do-not-contact state.
7. Send at most one polite follow-up after 14 days. If no response, pause contact for at least 90 days.
8. Convert positive replies into a bounded pilot with named responsibilities, data agreement, exit process and success measures.
9. Publish a monthly, non-identifying adoption summary: organisations approached, replies, pilot stations active, data-quality metrics and unresolved risks.

### Outreach channels
- Association newsletters and member circulars (permission requested from the editor).
- Association meetings, beekeeping fairs, local training days and webinars.
- Research institute / citizen-science project seminars.
- Open-source project pages, GitHub releases and public issue tracker.
- Mastodon / community forums / social channels: post useful technical updates and invite voluntary participation; obey each platform's rules and avoid unsolicited DMs.
- QR one-pager for apiary events, with a clear project purpose and privacy statement.

## 6. Pilot acceptance criteria

A pilot is a success only when:
- 3–5 stations can be installed and operated by their owners from written instructions.
- Raw camera media stays local unless a contributor explicitly opts in to a separate evidence-sharing path.
- Metadata events are authenticated, bounded, idempotent and recover after an outage.
- False-positive / false-negative samples are reviewed by a qualified human and measured on a held-out dataset with documented licenses.
- Any bearing result includes calibration metadata, time window, geometry and uncertainty; field searches are independently recorded.
- Official reporting channels remain usable and are not bypassed.
- A participant can stop participation, export project-held data and request deletion.

## 7. Data protection, safety and trust

- Do not scrape closed groups, personal profiles, member lists or private contact details.
- Do not add a person to a mailing list without a valid opt-in.
- Use published organisational contact channels and keep outreach relevant, one-to-one and transparent.
- Do not expose private apiary / residential locations, exact nest coordinates, access credentials, camera feeds or contributor identity in public dashboards.
- Separate public candidate sightings, vetted observations and expert-confirmed records.
- Obtain explicit permission and provenance for every image, audio clip, model weight and dataset before storing, publishing or training.
- Do not encourage untrained users to approach, disturb or remove nests. Route nest action to competent and authorised local services.
- Before a pilot, document controller / processor roles, purposes, lawful basis, retention, data-subject requests, security controls and cross-border transfers. This plan is not a legal compliance certification.

## 8. Current official reporting / reference routes

- EU invasive alien species and EASIN: https://environment.ec.europa.eu/topics/nature-and-biodiversity/invasive-alien-species_en
- EASIN data-partner contribution process: https://easin.jrc.ec.europa.eu/easin/Contribute
- Germany: D.I.B. state member associations: https://deutscherimkerbund.de/mitgliedsverbaende/
- NRW official Neobiota portal: https://neobiota.naturschutzinformationen.nrw.de/neobiota/de/fundpunkte/webformular
- NRW official guidance: https://neobiota.naturschutzinformationen.nrw.de/neobiota/de/arten/tiere/190771/massnahmen
- NABU overview of state reporting routes: https://www.nabu.de/natur-und-artenwissen/insekten/insektenportraets/die-asiatische-hornisse-breitet-sich-aus

These channels are references for reporting and partnership discovery. BeeKeeper3000 must not present itself as an official reporting authority.
