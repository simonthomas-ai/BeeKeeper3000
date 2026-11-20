# LLM Council – Betrieb mit 0 EUR

## Was ist bereits im Repository?

- `tools/llm_council.py`: Runner ohne Drittanbieter-Pythonpakete.
- `llm-council/config.json`: harte Budgetvorgabe 0 EUR, Ollama lokal, externe Provider standardmäßig aus.
- `llm-council/REVIEW-PROMPT.md`: identischer Review-Prompt für alle Modelle.
- `tests/test_llm_council.py`: Sicherheits- und Kosten-Gates.
- `.github/workflows/llm-council.yml`: wöchentlicher/manueller Lauf nur auf eigenem Runner.

## Lokal starten

1. Ollama installieren und starten: https://ollama.com/
2. Ein lokal ausführbares Modell laden, z. B. `ollama pull qwen2.5:7b`. Modellgröße an RAM/VRAM anpassen; die Lizenz des konkreten Modells vor Nutzung/Weitergabe prüfen.
3. Tests aus dem Repository-Hauptverzeichnis ausführen:

   ```sh
   python3 -m unittest tests.test_llm_council -v
   ```

4. Council starten:

   ```sh
   python3 tools/llm_council.py
   ```

5. Berichte erscheinen unter `llm-council/runs/`. Antworten werden nicht automatisch als wahr oder als Honig-Score bewertet.

## Externe kostenlose Modelle

Externe Anbieter sind absichtlich deaktiviert. Ein Provider darf nur aktiviert werden, wenn alle Bedingungen erfüllt sind:

- kostenloser Zugang ist für genau dieses Konto und Modell aktuell verifiziert;
- Nutzungsbedingungen wurden in den letzten 30 Tagen geprüft;
- der Anbieter erzwingt serverseitig eine harte Ausgabenobergrenze von exakt 0 EUR;
- die API ist OpenAI-chat-completions-kompatibel und verwendet HTTPS;
- Zugangsdaten liegen ausschließlich in einer lokalen Umgebungsvariable bzw. in einem geschützten Secret Store.

Die Konfigurationsfelder `free_access_verified`, `provider_enforced_hard_cap_eur` und `terms_reviewed_on` sind eine Betreiberbestätigung, keine automatische Prüfung der Anbieterabrechnung. Nicht aktivieren, wenn der Anbieter keine echte harte 0-EUR-Sperre anbietet. Insbesondere sind kostenlose Testguthaben und Pay-as-you-go-Credits keine Kostenfreiheit. Hugging Face Inference Providers sind standardmäßig gesperrt.

## GitHub-Actions-Zeitplan

Der Workflow läuft ausschließlich auf einem eigenen Linux-x64-Runner mit den Labels:

`self-hosted`, `linux`, `x64`, `llm-council`

Das Gerät muss eingeschaltet sein, Ollama muss laufen und das Modell lokal vorhanden sein. Es wird kein GitHub-gehosteter Runner verwendet. Um einen Runner einzurichten, folge den offiziellen GitHub-Schritten unter https://docs.github.com/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners und registriere ihn nur für dieses Repository. Runner nicht öffentlich oder ungeschützt betreiben.

Der Workflow ist wöchentlich (Montag 05:17 UTC) und manuell startbar. Er erzeugt nur ein Artefakt. Keine automatischen Issues, PRs, Commits oder Merges.

## Sicherheitsgrenzen

- Nur Loopback für Ollama; kein externer Ollama-Bind.
- Keine privaten Repositorydaten, Secrets, Bilder, Audio oder Standortkoordinaten in Prompts.
- Antworten sind nicht vertrauenswürdige Daten; nie als Shell-Befehle ausführen.
- Kein automatischer Codeimport, Merge oder Selbstbewertung.
- Vor externen Modellaufrufen Datenminimierung und Betreiberfreigabe.
- Bei Unsicherheit: Provider überspringen, nicht auf kostenpflichtige Alternative ausweichen.
