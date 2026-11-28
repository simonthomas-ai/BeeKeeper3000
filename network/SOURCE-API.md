# Dauerhaftes Hornet3000-Quelljournal (Source API)

Dies ist ein kleiner, eigenständig ausführbarer Ereignisspeicher für Installationen, bei denen der ursprüngliche Hornet3000-HTTP-Server nicht in diesem Repository vorliegt. Er implementiert die von `monitor-bridge/bridge.mjs` erwartete API. Er **ergänzt nicht** nachträglich den fehlenden C++-Dienst der Version 1.6.0 und verbindet auch nicht automatisch Kamera oder KI-Modell. Ein vertrauenswürdiger Ereignislieferant muss geprüfte Erkennungen per HTTP POST an diesen Dienst senden.

## Unter Windows PowerShell starten
Für Quell-API-Schlüssel und Cursor-Signaturgeheimnis **zwei getrennte Zufallswerte** erzeugen:

```powershell
$apiBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($apiBytes)
$env:HORNET3000_API_KEY = [Convert]::ToBase64String($apiBytes)

$cursorBytes = New-Object byte[] 32
$rng.GetBytes($cursorBytes)
$rng.Dispose()
$env:HORNET3000_CURSOR_SECRET = [Convert]::ToBase64String($cursorBytes)

$env:HORNET3000_EVENT_DB = "$env:LOCALAPPDATA\BeeKeeper3000\source-events.sqlite3"
$env:HORNET3000_EVENT_RETENTION_DAYS = "30"
$env:HORNET3000_EVENT_MAX_ROWS = "250000"
python -m network.source_api
```

Erforderlich ist Python 3.11 oder neuer; die Quell-API verwendet ausschließlich die Python-Standardbibliothek. Ein lokales Anwendungsdatenverzeichnis mit Zugriffsrechten des Windows-Dienstkontos einrichten. Die Anwendung setzt NTFS-Berechtigungen nicht selbst und verschlüsselt SQLite nicht. BitLocker oder ein verschlüsseltes Laufwerk verwenden.

Unter Linux/macOS:

```sh
export HORNET3000_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export HORNET3000_CURSOR_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export HORNET3000_EVENT_DB="$HOME/.local/share/beekeeper3000/source-events.sqlite3"
mkdir -p "$HOME/.local/share/beekeeper3000"
chmod 700 "$HOME/.local/share/beekeeper3000"
python -m network.source_api
```

Der Dienst bindet ausschließlich an `127.0.0.1:8787`. Den HTTP-Port **nicht öffentlich freigeben**. Fernzugriff erfordert ein separat geprüftes, authentifiziertes VPN-/TLS-Gateway. Schlüssel, Datenbankdateien, Kameramaterial und GPS-Bewegungsdaten niemals in Git speichern.

## API-Vertrag
Jede Anfrage muss den Header `X-API-Key` enthalten.

- `POST /api/events` speichert genau eine Beobachtung mit streng begrenzten Metadaten. Eine identische Wiederholung liefert `200` mit `duplicate: true`; ein neuer Eintrag `201`.
- `GET /api/events?limit=100&cursor=start` beginnt beim ältesten Ereignis, das innerhalb der festgelegten Aufbewahrungsfrist noch vorhanden ist. Ohne `cursor` gilt dasselbe.
- `GET /api/events?limit=100&cursor=<opaque-token>` setzt nach einem signierten Cursor fort.
- Ein identischer POST liefert `200`; die Wiederverwendung einer unveränderlichen ID mit verändertem Inhalt liefert `409`; bei vollem Journal wird `503` ausgegeben, ohne gespeicherte Ereignisse zu verwerfen.
- Seiten enthalten 1 bis 100 Ereignisse, aufsteigend nach Alter, mit `events`, `next_cursor` und `has_more`, passend zum Bridge-Vertrag.
- Cursor verwenden HMAC-SHA256 und sind an diesen Ereignisstrom gebunden. Fehlerhafte oder gefälschte Cursor liefern HTTP 400. Ein Cursor, der hinter die Aufbewahrungsgrenze zurückfällt, liefert HTTP 410 mit `earliest_sequence` und einem signierten `earliest_cursor`. Der Betreiber muss die Datenlücke ausdrücklich akzeptieren, bevor er fortfährt. Ein alter Cursor wird **niemals stillschweigend zurückgesetzt**. Neue Empfänger beginnen mit `start` beim ältesten noch gespeicherten Datensatz.

Das strenge Ereignisschema verlangt genau sieben Felder: `id`, `observed_at`, `station_id`, `species`, `confidence`, `prey_detected` und ein explizites `origin`. Fehlendes `origin` wird abgewiesen und niemals stillschweigend als `camera` interpretiert. Zulässige Werte sind ausschließlich `camera` und `manual_observation`. Die Mobile-PWA exportiert v2 mit explizitem `manual_observation`; der Importer weist Kamera- und unbekannte Ursprünge ab. Die Bridge verwirft Ereignisse ohne explizite Herkunftsangabe und bildet manuelle Sichtungen auf einen eigenen Monitor-Ereignistyp ab, der keine KI-Warnungen auslösen darf. `origin` bleibt ein vom Client geliefertes Routing-Merkmal und ist keine kryptografische Producer-Authentifizierung; ein explizites `camera` allein beweist daher keine echte Kameraerkennung. Bereits gespeicherte Legacy-Ereignisse werden durch diese Änderung nicht rückwirkend umklassifiziert und müssen vor einer Alarmnutzung gesondert geprüft werden. Bild-/Audiodaten, Dateipfade, GPS-Koordinaten, Zugangsdaten, beliebige Freitexte und Behauptungen fachkundiger Bestätigung werden abgewiesen. Kameraereignisse bleiben unbestätigte Kandidaten.

## Zuverlässigkeit und Speicherung
- SQLite-Schreibtransaktionen vergeben fortlaufende `AUTOINCREMENT`-Sequenznummern.
- Quellereignis-IDs sind eindeutig. Identische Inhalte werden wiederholbar ohne doppelte Speicherung verarbeitet; dieselbe ID mit verändertem Inhalt wird abgewiesen.
- Cursor-Sequenz und Aufbewahrungsgrenze werden dauerhaft gespeichert. Sequenznummern werden nicht zurückgesetzt, selbst wenn die Aufbewahrungsregel sämtliche Zeilen entfernt.
- Die Aufbewahrung ist zeitlich begrenzt und wird beim Schreiben sowie Lesen von Seiten durchgesetzt; die maximale Zeilenzahl ist ebenfalls begrenzt. Bei voller Kapazität verweigert der Dienst weitere Einträge, statt Ereignisse zu löschen, die die Bridge noch nicht gelesen hat.
- Maximale Anfragegröße: 32 KiB; maximale Antwortseite: 2 MiB. Anfrageprozesse, Warteschlange, Lesezeitgrenze und Zustand der IP-basierten Ratenbegrenzung sind begrenzt.
- SQLite wird von der Anwendung nicht verschlüsselt. Unter POSIX müssen Datenverzeichnisse dem Dienstkonto gehören und Modus 0700 besitzen; SQLite-Dateien und Nebendateien erhalten 0600. Unter Windows müssen NTFS-Zugriffsrechte ausdrücklich gesetzt werden.

## Bridge verbinden
Im BeeKeeper3000-Verzeichnis die vorhandene Bridge auf `http://127.0.0.1:8787` einstellen, `HORNET3000_API_KEY` auf den Schlüssel der Quell-API setzen und die davon unabhängige Monitor-Empfängeradresse samt Token konfigurieren. `BRIDGE_REQUIRE_CURSOR=true` verwenden. Die Bridge verweigert dann unsicheren Betrieb, statt unbemerkt auf eine verlustbehaftete Liste der letzten 100 Ereignisse zurückzufallen.

Ein eigenständiger Ereignislieferant bzw. Erkennungsprozess muss weiterhin zulässige Kandidaten per POST an diese API senden. Dieses Modul verbindet **keine** Livekamera und keinen Klassifikator automatisch.

## Tests

```sh
python -m unittest network.test_source_api -v
python -m unittest network.test_source_api network.test_triangulation -v
```

Die Tests decken Paginierung mit 250 Ereignissen, Neustart/Fortsetzung, manipulierte oder veraltete Cursor, Aufbewahrung, Duplikate, Kapazitätsgrenzen, Authentifizierung und Ablehnung privater Datenfelder ab. Es sind **Softwaretests**, keine Nachweise für Funkreichweite oder Feldtauglichkeit.

## Authentifiziertes Löschen von Quellereignissen
Das Quelljournal unterstützt einen authentifizierten Löschaufruf durch den Betreiber:

`DELETE /api/events?id=<URL-encoded-event-id>`

Denselben Header `X-API-Key` wie beim Einfügen und Lesen verwenden. Der Endpunkt akzeptiert genau eine druckbare ASCII-Ereignis-ID, lehnt Anfragekörper ab und liefert `{"deleted":true}` nur, wenn die Zeile tatsächlich gelöscht wurde. Eine wiederholte Löschung ist ohne zusätzliche Wirkung und liefert `{"deleted":false}`. Ungültige Parameter werden abgewiesen; ein nicht authentifizierter Löschversuch liefert HTTP 401.

Eine Löschung erzeugt einen **Löschvermerk** (Tombstone), der nur Ereignis-ID und Löschzeitpunkt enthält. Er verhindert, dass ein verspäteter Wiederholungsversuch das gelöschte Ereignis während der Aufbewahrungsfrist des Quelljournals erneut erzeugt. Der Löschvermerk läuft mit derselben Frist ab. Die Zahl der Löschvermerke ist auf das Doppelte des eingestellten Ereignislimits begrenzt. Ist dieses gesonderte Verzeichnis voll, verweigert der Dienst die Löschung mit HTTP 503, statt eine spätere Wiederholung stillschweigend zu ermöglichen.

Eine ausdrückliche Löschung verschiebt weder die Cursor-Aufbewahrungsgrenze noch verwendet sie Sequenznummern erneut. Die Bridge kann die bewusst entstandene Lücke überspringen. Die normale zeitliche Aufbewahrung verschiebt die Grenze dagegen weiterhin und führt bei veralteten Cursorn zu HTTP 410. Backups enthalten die Löschvermerke.

**Wichtig:** Die Löschung betrifft nur das lokale Quelljournal. Sie löscht kein bereits beim Monitor gespeichertes Ereignis, keine Kopie in Backup oder Export, kein bereits übertragenes Funkpaket und keinen Browserexport. Betreiber müssen nachgelagerte Monitor-Kopien gesondert löschen und andere Kopien entsprechend dem genehmigten Datenlebenszyklus löschen oder ablaufen lassen. Eine bereits geladene, noch nicht verarbeitete Bridge-Seite kann das Ereignis weiterhin enthalten; die nachgelagerte Löschung nach Abschluss laufender Übertragungen erneut kontrollieren.
