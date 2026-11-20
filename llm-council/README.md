# LLM Council – Online-only, 0 EUR

## Zielarchitektur

BEEKEEPER3000 verwendet keine lokalen LLMs und führt keine lokale Modellinferenz aus. Der Council-Runner ist nur ein leichter Orchestrator; die Textgenerierung erfolgt über freigegebene Online-APIs. Das API-Budget bleibt strikt 0 EUR.

- `tools/llm_council.py`: standardbibliotheksbasierter Orchestrator.
- `llm-council/config.json`: lokales Ollama ist deaktiviert; Online-Provider werden einzeln freigegeben.
- `llm-council/REVIEW-PROMPT.md`: gemeinsamer Review-Prompt.
- `tests/test_llm_council.py`: Kosten- und Sicherheits-Gates.

## Erster Online-Pfad: OpenRouter Free

OpenRouter Free ist lediglich als möglicher Adapter vorbereitet und bleibt deaktiviert. Vor einer Aktivierung müssen die aktuelle Kontoberechtigung, Modellverfügbarkeit, Nutzungsbedingungen und ein vom Anbieter tatsächlich erzwungener Ausgabenstopp von exakt 0 EUR nachgewiesen werden. Ein fehlender oder nicht verifizierbarer Hard Cap bedeutet: keine Anfrage. Ein API-Schlüssel allein beweist weder Gratiszugang noch Kostenfreiheit. Keine Zahlungsmethode, Guthabenaufladung oder kostenpflichtigen Fallbacks aktivieren.

## LMArena / Arena

LMArena wird als manuelle Qualitäts- und Modellorientierung genutzt, nicht als automatisierter Council-Endpunkt. Keine Browser-Bots, Scraper oder inoffiziellen Endpunkte. Die offizielle Arena API belastet Requests gegen Workspace-Guthaben; direkte Modellaufrufe benötigen bezahlte oder passende Aktionsmittel. Die Arena-AUP untersagt automatisiertes Benchmarking. Deshalb ist Arena API für den automatischen 0-EUR-Council nicht aktiviert.

## Weitere Anbieter

- Google Gemini API Free Tier: deaktiviert, bis ein Projekt ohne Billing bestätigt ist. Free-Tier-Inhalte können zur Produktverbesserung verwendet werden; nur öffentliche/anonymisierte Daten senden.
- Groq Free Tier: deaktiviert, bis ein Free-only-Konto und ein sicherer nicht kostenpflichtiger Stopp verifiziert sind. Developer Tier benötigt eine Zahlungsmethode.
- Hugging Face Inference Providers: deaktiviert; Free-Accounts haben laut aktueller Dokumentation keine monatlichen Inference-Provider-Credits und Requests sind Pay-as-you-go.
- Weitere Provider nur nach Nachweis einer echten 0-EUR-Sperre und Prüfung der Nutzungsbedingungen.

## Start

1. `OPENROUTER_API_KEY` sicher als Umgebungsvariable setzen. Nicht in Dateien, Issues oder Commits speichern.
2. `python -m unittest tests.test_llm_council -v` ausführen.
3. `python tools/llm_council.py` starten.
4. JSON-Berichte werden lokal im konfigurierten Ausgabeverzeichnis gespeichert.

Der Runner prüft Budget, HTTPS, Providerfreigabe, Terms-Prüfdatum und die bestätigte harte 0-EUR-Sperre. Antworten werden nie automatisch ausgeführt, übernommen, bewertet oder gemerged.

## Datenschutz und Sicherheit

Nur öffentliche, anonymisierte und notwendige technische Inhalte an externe Modelle senden. Keine API-Schlüssel, Passwörter, personenbezogenen Daten, Kamerabilder, Audio, GPS-/Stationskoordinaten oder vertraulichen Sicherheitsdetails. Secret-Pattern-Scans ersetzen keine manuelle Datenschutzprüfung. Kostenstatus unbekannt/abgelaufen/nicht verifizierbar bedeutet: nicht aufrufen. Keine kostenpflichtigen Fallbacks oder Aufladungen.

Der Workflow-Runner führt nur Orchestrierung aus; die Modellinferenz erfolgt vollständig online. Ein geeigneter lokaler LLM-Rechner ist nicht erforderlich.