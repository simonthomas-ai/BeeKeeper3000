# LLM Council – Online-only, 0 EUR

Status: Architektur auf Online-LLMs umgestellt. Lokale Ollama-Inferenz ist deaktiviert. OpenRouter Free ist als erster API-Pfad konfiguriert; ein erfolgreicher Modellaufruf ist erst nach Einrichtung eines Free-Kontos und API-Schlüssels nachgewiesen.

## Leitentscheidung

Es gibt keine lokale Modellinferenz. Der Council-Runner ist nur ein leichter Orchestrator. Sämtliche LLM-Antworten kommen von externen Online-Diensten. Harte Obergrenze für Modell-/API-Kosten: 0 EUR. Keine kostenpflichtigen Fallbacks, Aufladungen oder Pay-as-you-go-Aufrufe.

## LMArena / Arena

LMArena wird für manuelle menschliche Vergleiche, Modellranglisten und Qualitätsorientierung genutzt. Die offizielle Arena API ist eine gesonderte API unter api.arena.ai; sie belastet Requests gegen Workspace-Guthaben. Direkte Modellaufrufe benötigen bezahltes oder passendes Aktionsguthaben. Die Arena Acceptable Use Policy untersagt automatisiertes Benchmarking und Scraping. Deshalb wird die Arena API nicht in den automatisierten 0-EUR-Council integriert. Keine inoffiziellen Browser-Bots oder undokumentierten Endpunkte verwenden.

## Provider-Matrix

| Provider | Rolle | Status | Entscheidung |
|---|---|---|---|
| OpenRouter Free | Erster Online-Review-Pfad; openrouter/free wählt kostenlose Modelle | Konfiguriert, Schlüssel erforderlich | Nur Free-Tarif und kostenlose Modellroute; keine Zahlung/Guthabenaufladung. Kein Paid-Fallback |
| Google Gemini API Free Tier | Zusätzlicher unabhängiger Reviewer | Deaktiviert | Nur mit Projekt ohne Billing; Free-Tier-Inhalte können zur Produktverbesserung genutzt werden |
| Groq Free Tier | Zusätzlicher Reviewer | Deaktiviert | Developer Tier benötigt Zahlungsmethode und ist Pay-as-you-go; nur bei Free-only-Konto aktivieren |
| Hugging Face Inference Providers | Modellkatalog/optionale Inferenz | Deaktiviert | Free-Accounts erhalten aktuell keine monatlichen Inference-Provider-Credits; Routing ist Pay-as-you-go |
| Arena API | API-Zugriff auf Arena-Modelle | Nicht integriert | Workspace-Guthaben/Bezahlung und AUP-Beschränkungen |
| Lokales Ollama | Modellinferenz | Deaktiviert | Kein geeigneter lokaler LLM-Rechner vorhanden |

## Kostenregeln

1. budget_eur muss exakt numerisch 0 sein.
2. Jeder externe Provider benötigt HTTPS, ausdrückliche Aktivierung, aktuelles Terms-Prüfdatum, bestätigten kostenlosen Zugang und eine echte harte 0-EUR-Sperre.
3. Konfigurationsfelder sind Betreiberattestierungen, keine unabhängige Abrechnungsprüfung. Wenn der Provider kostenpflichtige Requests zulässt, bleibt er deaktiviert.
4. OpenRouter nur mit Free-Tarif und Free-Modellroute nutzen. Laut Anbieter gelten im Free-Tarif 50 Requests/Tag; höhere Limits setzen Credits-Kauf voraus. Keine Credits kaufen.
5. HTTP 402, unklare Preise, fehlender Free-Status oder geänderte Terms führen zum sofortigen Skip.
6. API-Schlüssel nur als Umgebungsvariablen/Secrets speichern.

## Review und Datenschutz

Alle freigegebenen Modelle erhalten dieselbe öffentliche, anonymisierte Aufgabe. Ergebnisse werden mit Provider, Modell-ID, Zeitpunkt, Prompt-Hash, Antwort-Hash und Status dokumentiert. Modellantworten sind Vorschläge, keine Fakten oder Stimmen. Widersprüche werden durch Quellen, reproduzierbare Tests und menschliche Prüfung aufgelöst. Kein automatischer Codeimport, PR-Merge oder Deployment.

Externe Modelle erhalten ausschließlich notwendige, öffentliche oder anonymisierte Projektinformationen. Nie übermitteln: API-Keys, Passwörter, private Repository-Geheimnisse, personenbezogene Daten, Kamerabilder, Audio, exakte GPS-/Stationskoordinaten oder unveröffentlichte Sicherheitslücken. Anbieter können Eingaben speichern oder anderweitig verarbeiten.

## Noch nicht nachgewiesen

- Kein erfolgreicher OpenRouter-API-Aufruf mit dem Nutzerkonto wurde durchgeführt.
- Kein weiterer Online-Provider wurde aktiviert oder befragt.
- Es liegt noch kein tatsächlicher Mehrmodellvergleich oder Honey-Score vor.
- LMArena wurde nicht automatisiert abgefragt.
- Die Unit-Tests wurden bei dieser Änderung nicht ausgeführt.