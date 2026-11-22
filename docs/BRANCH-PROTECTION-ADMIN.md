# Admin-Schritt: main-Branches schützen

Stand: 22.11.2026. Die Repositories besitzen noch keine bestätigten Rulesets bzw. Branch-Protection-Nachweise. Der GitHub-Zugriff, der für die Codeänderungen verwendet wird, kann Repository-Einstellungen nur lesen; die Branch-Protection-Abfrage antwortet mit 403 Resource not accessible by integration. Deshalb darf dieser Adminpunkt nicht als erledigt markiert werden.

## Sichere Konfiguration

Das Skript scripts/Set-VespaGuardBranchProtection.ps1 konfiguriert beide Repositories:

- simonthomas-ai/BeeKeeper3000
- simonthomas-ai/Beekeeper-Monitor

Für main werden Pull Requests verlangt, Statusprüfungen und ein aktueller Zielbranch erzwungen, Admins eingeschlossen, Force-Pushes und Löschung verboten, lineare Historie sowie aufgelöste Review-Kommentare verlangt. Die Zahl erforderlicher Approvals bleibt bewusst bei 0, damit ein einzelner Maintainer nicht durch eine unmögliche Selbstfreigabe ausgesperrt wird. Die Pull-Request-Pflicht bleibt bestehen.

### Erforderliche Statusprüfungen

BeeKeeper3000:
- Python core and safety tests
- Camera runtime safety tests
- Windows camera runtime compatibility tests
- Monitor bridge tests
- Analyze source (python)
- Analyze source (javascript-typescript)

Beekeeper-Monitor:
- gesamttest
- BeeKeeper3000 – Bridge-Integration

Das Skript liest vorhandene Schutzregeln für beide Repositories zuerst ein. Ist auch nur eine main-Branch bereits geschützt, bricht es vor jeder Änderung ab, damit bestehende Ausnahmen, App-Bindungen oder Review-Regeln nicht versehentlich ersetzt werden. In diesem Fall die gewünschten Pflichtchecks manuell in GitHub ergänzen und die übrigen Regeln erhalten. Bei 403, fehlenden Adminrechten oder einem anderen unerwarteten API-Fehler bricht es ebenfalls vor jeder Änderung ab.

## Ausführung auf einem Administrations-PC

Voraussetzungen: GitHub CLI, Windows PowerShell 5.1 oder PowerShell 7, angemeldeter Repository-Administrator und Token mit Repository-Berechtigung Administration: write. Die Skriptdatei ist ASCII-kompatibel; der en dash im Statuscheck-Namen wird als Unicode-Codepunkt erzeugt.

Schritt 1 – Anmelden und Berechtigungen prüfen:

    gh auth login
    gh auth status
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Set-VespaGuardBranchProtection.ps1

Der Standardlauf ist nur eine Vorschau und ändert nichts. Nach Prüfung der angezeigten Statuschecks die Konfiguration explizit anwenden:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Set-VespaGuardBranchProtection.ps1 -Apply

Das Skript liest die Einstellungen nach dem Schreiben erneut ein und prüft die erforderlichen Statuschecks, erzwungene Pull-Requests (0 Approvals), veraltete Review-Verwerfung, lineare Historie, Admin-Durchsetzung, Fast-Forward-Schutz, Löschschutz und Conversation Resolution. Bei einem Fehler bleibt die Aufgabe offen; anschließend in GitHub Settings → Branches beide main-Branches kontrollieren.

## Grenzen

- Es werden keine Secrets in das Repository geschrieben oder ausgegeben.
- Es werden keine Review-Approvals erzwungen, weil für einen einzelnen Maintainer keine zweite Person vorausgesetzt werden darf.
- Das Skript konfiguriert klassischen Branch Protection. Bestehende zusätzliche Rulesets werden nicht gelöscht.
- Diese Einstellung schützt nur GitHub-Merges. Sie ist keine KI-, Rechts-, Kamera- oder Funkfreigabe.

Offizielle API-Referenz: https://docs.github.com/en/rest/branches/branch-protection
