# LLM Council – offene, kostenfreie und demokratische Projektberatung

Status: Governance dokumentiert; Runner und GitHub-Actions-Workflow eingecheckt. Der Runner ist erst nach Einrichtung eines passenden Self-hosted-Runners und lokaler Modelle tatsächlich ausführbar.

## Zweck

BEEKEEPER3000 kann mehrere unabhängige Sprachmodelle als beratende Prüfer für Architektur, Implementierung, Tests, Sicherheit, Datenschutz, Barrierefreiheit und Dokumentation einsetzen. Ziel ist ein offener, reproduzierbarer Review-Prozess für gemeinnützige Nutzung. Kein Modell erhält Schreibrechte auf den Hauptzweig oder entscheidet allein über Releases.

## Harte Kosten- und Datenschutzregeln

1. **Kostenobergrenze: 0 EUR.** Keine Pay-as-you-go-Aufrufe, keine kostenpflichtigen Tokens, keine automatische Aufladung und keine kostenpflichtigen Provider-Fallbacks.
2. Ein Provider wird nur aktiviert, wenn sein aktueller Tarif tatsächlich kostenfrei ist, die Nutzungsbedingungen die geplante Nutzung erlauben und ein Betreiber die Aktivierung ausdrücklich konfiguriert.
3. Hugging Face Inference Providers ist eine Aggregations-/Routingplattform, keine Garantie für kostenlose Inferenz. Die aktuelle Preisdokumentation weist für Free-Accounts keine monatlichen Inference-Provider-Credits aus; Inference Providers sind pay-as-you-go. Daher bleibt HF-Inferenz standardmäßig deaktiviert und wird nur zugelassen, wenn ein Anbieter eine technisch durchsetzbare Ausgabenobergrenze von exakt 0 EUR garantiert. Lokale Open-Weight-Modelle auf eigener Hardware sind der bevorzugte kostenfreie Weg.
4. LMArena ist für menschliche, öffentliche Vergleichs-/Benchmark-Teilnahme vorgesehen. Keine Bots, automatisierten Browseraktionen, Scraping oder nicht dokumentierte Endpunkte. Arena-Ranglisten sind Kontext, kein Ersatz für reproduzierbare Projektbenchmarks.
5. Keine privaten Schlüssel, Tokens, Passwörter, Kamerabilder, Audio, personenbezogenen Daten, exakten Stationskoordinaten oder vertraulichen Sicherheitsdetails an externe Modelle senden.
6. Vor jeder externen Anfrage wird der Prompt auf Geheimnisse und personenbezogene Daten geprüft und auf ein minimales, öffentlich teilbares technisches Paket reduziert.
7. Jeder Anbieter muss explizit in einer lokalen Allowlist freigeschaltet sein. Fehlt eine gültige kostenlose Nutzungsmöglichkeit, wird er übersprungen und im Bericht als „nicht verfügbar/kostenfrei nicht verifiziert“ geführt.

## Modellinventar und Status

Das Inventar ist dynamisch. Es werden keine Modelle als „befragt“ markiert, bevor eine echte, dokumentierte Antwort vorliegt.

| Anbieter/Quelle | Rolle | Aktivierung |
|---|---|---|
| Lokale Open-Weight-Modelle (z. B. Qwen, Gemma, Mistral, DeepSeek, Llama-kompatible Modelle) | Gleichberechtigte Review-Teilnahme, sofern lokal ausführbar und Lizenz geprüft | Lokal durch Betreiber |
| Hugging Face Hub / Inference Providers | Modellkatalog, Metadaten und optionale Inferenz | Aus; nur bei nachgewiesenem 0-EUR-Tarif und Betreiberfreigabe |
| LMArena | Menschlich gesteuerter, vergleichender Benchmark und Community-Feedback | Manuell; keine automatisierten Abfragen |
| Weitere Provider (OpenAI, Anthropic, Google, DeepSeek, Mistral, etc.) | Optionale unabhängige Reviews | Nur bei explizit bestätigtem kostenlosem Kontingent und API-Zugang; sonst überspringen |

Für jedes tatsächlich befragte Modell werden Modell-ID, Anbieter, Modellrevision soweit verfügbar, Datum/Uhrzeit, Lizenz/Terms-Prüfdatum, Kostenstatus, Prompt-Hash, Antwort-Hash, Fehler/Rate-Limit und Reviewergebnis dokumentiert. Nicht verfügbare oder nicht kontaktierte Modelle werden nicht als Teilnehmer gezählt.

## „Honig“-Bewertung (0–100)

Die Honig-Punktzahl misst den belegten Nutzen eines konkreten Beitrags für BEEKEEPER3000, nicht die allgemeine Qualität oder Popularität eines Modells.

| Kriterium | Gewicht |
|---|---:|
| Technische Korrektheit, reproduzierbare Belege und Testbarkeit | 25 |
| Sicherheit, Datenschutz und Bedrohungsmodell | 20 |
| Funktionaler Nutzen und Integrationsfähigkeit | 15 |
| Stabilität, Wartbarkeit und Modularität | 15 |
| Lizenz-/Urheberrechtsklarheit | 10 |
| Kostenfreiheit und gemeinnützige Zugänglichkeit | 10 |
| Verständlichkeit und vollständige Quellenangaben | 5 |
| **Summe** | **100** |

Honig-Stufen: 0–39 „Nektar“ (nicht belastbar), 40–59 „Pollen“ (interessanter Ansatz), 60–74 „Honigkandidat“ (prüfenswert), 75–89 „Goldener Honig“ (durch Tests gestützt), 90–100 „Wabenstandard“ (unabhängig reproduziert und freigegeben).

Ein Vorschlag erhält zunächst nur eine vorläufige Punktzahl. Punkte für Korrektheit, Sicherheit und Stabilität werden erst nach Prüfung und Tests vergeben. Nicht belegte Behauptungen, fehlende Quellen, Lizenzunklarheit oder bezahlte Abhängigkeiten reduzieren den Wert. Ein Modell darf sich nicht selbst bewerten. Anbieter- und Modellnamen bleiben sichtbar; Bewertungen werden nicht durch Anbieter gesponsert.

Lokale und externe Modelle erhalten bei gleicher Aufgabe, gleichem Kontext und gleicher Bewertungsmethodik gleichberechtigte Review-Gelegenheiten. Es gibt keine Bevorzugung nach Anbieter oder Modellgröße. Externe Modelle werden nur dann tatsächlich aufgerufen, wenn die 0-EUR-Sperre technisch beim Anbieter durchgesetzt werden kann. Ein Zeitplan kann keine Gratis-Kontingente herbeiführen; Provider-Quoten und Abrechnungsbedingungen besitzen keine universelle, verlässliche Schnittstelle.\n\n## Demokratischer Entscheidungsprozess

1. Ein gemeinsamer, versionierter Aufgaben-Prompt und ein öffentliches, anonymisiertes Kontextpaket werden erstellt.
2. Alle aktivierten Modelle erhalten dieselbe Aufgabe und dieselben relevanten Informationen. Antworten werden unabhängig gesammelt.
3. Ein Moderator extrahiert einzelne Vorschläge, Risiken, Quellen und überprüfbare Behauptungen in ein neutrales Vorschlagsregister.
4. Gleichberechtigte menschliche Projektprüfer bewerten die Vorschläge anhand der Honig-Kriterien. Modellstimmen sind beratend, keine demokratischen Stimmen.
5. Technische Vorschläge werden als Issue/PR mit Tests, Lizenznachweis und Sicherheitsauswirkung eingereicht.
6. Übernahme erfolgt erst nach CI, Code Review und menschlicher Freigabe. Sicherheitskritische Änderungen benötigen mindestens zwei unabhängige menschliche Reviews.
7. Minderheitsmeinungen und begründete Ablehnungen bleiben im Entscheidungsprotokoll erhalten.

Es gibt keine Abstimmung „Modell gegen Modell“ über die Wahrheit. Mehrheitskonsens ersetzt weder Messdaten noch Fachprüfung.

## Implementierter Runner und Autarkie

- `tools/llm_council.py` implementiert einen standardbibliotheksbasierten Runner für lokale Ollama-Modelle und ausdrücklich freigegebene OpenAI-kompatible HTTPS-Endpunkte.
- `llm-council/config.json` setzt `budget_eur: 0`; Ollama ist auf Loopback begrenzt. Lokale Modelle müssen in `llm-council/config.json` explizit freigegeben sein; Cloud-Modellkennungen werden abgewiesen.
- Externe Endpunkte bleiben standardmäßig deaktiviert. Erforderlich sind eine aktuelle (maximal 30 Tage alte) Nutzungsbedingungenprüfung, explizit bestätigter kostenloser Zugriff und ein vom Anbieter durchgesetztes hartes Ausgabenlimit von exakt 0 EUR. Fehlt eine Bedingung, wird der Anbieter übersprungen.
- `tests/test_llm_council.py` prüft Kosten-Gates, HTTPS, Loopback-Bindung, Secret-Blockierung und Promptgrößenlimit.
- `.github/workflows/llm-council.yml` startet wöchentlich oder manuell ausschließlich auf einem selbstverwalteten Runner mit den Labels `self-hosted`, `windows`, `x64`, `llm-council`. Es werden keine kostenpflichtigen GitHub-gehosteten Runner verwendet.
- Der Workflow lädt einen Bericht als Artefakt hoch; er erstellt keine PRs, verändert keine Projektdateien und merged niemals automatisch.
- Berichte enthalten Antwort-Hashes und Status. Honig-Punkte werden nicht automatisch vergeben, sondern erst nach unabhängiger menschlicher Prüfung.

**Wichtige Grenze:** Eine Konfigurationsangabe allein kann die Abrechnung eines fremden Anbieters nicht technisch garantieren. Externe Anbieter dürfen nur aktiviert werden, wenn deren eigene Kontoeinstellungen/Vertrag eine echte harte 0-EUR-Sperre durchsetzen. Ist das nicht verfügbar, bleibt der externe Anbieter deaktiviert. Die aktuelle Hugging-Face-Inference-Provider-Route erfüllt diese Voraussetzung nicht automatisch.

## Autarker Ausführungsentwurf

- GitHub Actions kann zeitgesteuert einen Review-Lauf starten, sofern Actions im Repository aktiviert und die benötigten Runner verfügbar sind.
- Standardmäßig läuft der Zeitplan wöchentlich und zusätzlich manuell per workflow_dispatch; keine Dauerpolling-Schleifen.
- Vor jedem Lauf: Modellkatalog aktualisieren, Lizenz-/Kostenstatus prüfen, Allowlist laden, Budgetlimit 0 EUR erzwingen.
- Nur lokale Runner oder ausdrücklich kostenfreie, freigegebene Provider dürfen Anfragen ausführen.
- Wenn kein kostenfreier Provider verfügbar ist oder ein Secret fehlt: sauberer Skip, Statusbericht, keine kostenpflichtige Ausweichroute.
- Ausgaben gehen zunächst als Artefakt oder Entwurf in einen Review-Zweig/Issue. Kein automatischer Merge und keine direkten Änderungen am Hauptzweig.
- Rate Limits, Retry-After, exponentielles Backoff mit Jitter, Zeitlimits, maximale Antwortgröße und ein hartes Tages-/Lauflimit schützen die Infrastruktur.
- Secrets nur als GitHub Actions Secrets; niemals in Logs, Artefakten, Prompts oder Commits.

Ein Zeitplan kann nur bereits konfigurierte Provider aufrufen. Er kann weder die Verfügbarkeit kostenloser Kontingente erzwingen noch beliebige geschlossene Chat-Webseiten automatisch befragen.

## Aufgabenbereiche für unabhängige Reviews

- Systemarchitektur, Installer, Windows/Linux/ARM-Builds
- Kamera-/RTSP-/USB-Pipeline, ONNX und Modellprovenienz
- Vespa velutina vs. Vespa crabro: Datenqualität, Fehlalarme und fachliche Verifikation
- Triangulation, Zeit-/Winkelkalibrierung und Fehlerellipse
- MeshCore-Funkprotokoll, Reichweite, Schlüsselverwaltung und regulatorische Grenzen
- Freenet-Adapter als optionales, getrenntes P2P-Overlay
- Monitor-Bridge, API, SQLite, Idempotenz und Wiederherstellung
- DSGVO, IT-Sicherheit, Threat Modeling und Lieferkette
- Lizenz-Compliance, SBOM, Dokumentation und Barrierefreiheit

## Reproduzierbarkeit und Erfolgskriterien

Jeder Review-Lauf speichert:
- Commit-SHA und Prompt-/Kontextversion
- genaue Modell-ID und Revision (falls verfügbar)
- Zeitstempel und Provider
- Kosten-/Nutzungsstatus und geschätzte/abgerechnete Kosten, sofern bekannt
- Antwortdatei bzw. deren Hash und Quellen
- Honig-Bewertung mit Einzelkriterien und Begründung
- daraus entstandene Issues/PRs und deren Teststatus

Erfolg bedeutet nicht möglichst viele Modellaufrufe. Erfolg bedeutet, dass kostenfreie, rechtmäßige und nachprüfbare Beiträge zu getesteten Verbesserungen führen.

## Offene Mitwirkung

Beiträge sind willkommen: Bitte Issues mit konkreten technischen Vorschlägen, reproduzierbaren Tests, Lizenzinformationen und Quellen eröffnen. Keine Zugangsdaten oder privaten Standort-/Kameradaten posten.
