# BeeKeeper-Station – Linux / Raspberry Pi

**Status:** Installierbare Basisdienste. Kamera und Funk sind optionale Komponenten und müssen separat eingerichtet werden.

Der Installer richtet drei Dienste ein:
1. **Monitor:** lokale PWA und authentifizierter SQLite-Empfänger unter `127.0.0.1:8765`.
2. **Quell-API:** authentifiziertes SQLite-Quelljournal unter `127.0.0.1:8787`.
3. **Bridge:** über Cursor gesteuerte Metadatenübertragung vom Quelljournal zum Monitor.

Verwendet werden systemd, ein eigener unprivilegierter Benutzer `beekeeper`, ein privates Datenverzeichnis, eine betriebssystemgeschützte Konfigurationsdatei und versionierte Programmstände im Besitz von root. Alle Dienste binden ausschließlich an die lokale Loopback-Schnittstelle und dürfen nicht direkt ins Internet gestellt werden.

## Voraussetzungen
- Linux mit systemd (empfohlen: Debian Bookworm / Raspberry Pi OS Bookworm oder neuer).
- Python 3.11 oder neuer.
- Node.js 20 oder neuer.
- Administratorrechte (root) zur Installation.
- Lokale Kopien beider GitHub-Repositories.

Die Basisdienste nutzen die Standardbibliotheken von Python und Node.js. Zusätzliche Kamera- und MeshCore-Abhängigkeiten werden nicht automatisch installiert.

## Installation
Im Verzeichnis `BeeKeeper3000` ausführen; daneben muss `Beekeeper-Monitor` liegen:

~~~sh
sudo bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor"
~~~

Der Installer legt folgende Pfade an:

| Pfad | Bedeutung |
|---|---|
| `/opt/beekeeper3000/current` | Aktive BeeKeeper3000-Version |
| `/opt/beekeeper-monitor/current` | Aktive Monitor-Version |
| `/opt/beekeeper3000/releases` und `/opt/beekeeper-monitor/releases` | Versionierte, schreibgeschützte Programmstände; ältere Versionen bleiben erhalten |
| `/var/lib/beekeeper3000` | SQLite-Datenbanken und Bridge-Prüfpunkt |
| `/etc/beekeeper3000/station.env` | API-Schlüssel und lokale Einstellungen; Eigentümer root, nur für Gruppe `beekeeper` lesbar (0640) |

Zufällige Geheimnisse für Quell-API, Cursor-Signatur und Monitor-Empfänger werden lokal erzeugt und **niemals ausgegeben**. Bei Aktualisierungen wird die vorhandene Schlüsseldatei weiterverwendet. Datenbanken und Bridge-Cursor bleiben erhalten.

Nach der Installation prüft der Installer die Monitor-Startseite und die authentifizierte, per Cursor paginierte Quell-API. Dienststatus und Protokolle prüfen:

~~~sh
systemctl status beekeeper-monitor beekeeper-source-api beekeeper-bridge
journalctl -u beekeeper-monitor -u beekeeper-source-api -u beekeeper-bridge
~~~

Lokale PWA öffnen: http://127.0.0.1:8765/

## Aktualisierung
Den Installer erneut mit aktualisierten lokalen Repository-Kopien ausführen. Er stoppt nur die BeeKeeper-Dienste, legt neue versionierte Programmdateien ab, wechselt die aktiven symbolischen Links atomar, lädt systemd neu und startet die Dienste. Frühere Versionen unter `/opt` und Stationsdatenbanken bleiben erhalten.

Die vorhandene `station.env` wird weiterverwendet. **Den Cursor-Signaturschlüssel niemals bei erhaltenem Bridge-Prüfpunkt neu erzeugen:** Der bestehende signierte Quell-Cursor wäre danach ungültig.

## Dienste stoppen oder entfernen
Alle Dienste anhalten und deaktivieren:

~~~sh
sudo systemctl disable --now beekeeper-bridge beekeeper-source-api beekeeper-monitor
~~~

Nur die Dienstdefinitionen entfernen, ohne Datenbanken, Schlüssel oder Programmversionen zu löschen:

~~~sh
sudo rm -f /etc/systemd/system/beekeeper-monitor.service \
  /etc/systemd/system/beekeeper-source-api.service \
  /etc/systemd/system/beekeeper-bridge.service
sudo systemctl daemon-reload
~~~

Ein Befehl zum unwiederbringlichen Löschen von Daten wird bewusst nicht bereitgestellt. Daten- und Konfigurationsverzeichnisse mit Datenträgerverschlüsselung, Zugriffsrechten und Sicherungsregeln schützen.

## Optionale Kamera
Der Basisinstaller installiert **weder OpenCV noch ONNX Runtime**, startet keine Kamera und schaltet keine KI-Erkennung ein. So werden Raspberry-Pi-Ressourcen geschont und unberechtigte Sicherheitserwartungen vermieden.

Erst nachdem ein lokal beschafftes Modell die individuelle Herkunfts-/Lizenzprüfung, SHA-256-Prüfung, Ein-/Ausgabeschnittstellenprüfung und menschliche Freigabe bestanden hat:

1. Geschütztes Modellverzeichnis anlegen und ONNX-Datei samt Manifest ablegen. Das Manifest muss die Lizenzprüfung als genehmigt oder gemeinfrei kennzeichnen und den exakten Modell-Hash enthalten; ungeprüfte Lizenzen und ungültige Hashes werden abgewiesen.
2. `docs/camera.env.example` nach `/etc/beekeeper3000/camera.env` kopieren. Mit `sudoedit` Stationspseudonym und Kameraquelle setzen, Eigentümer `root:beekeeper` und Berechtigung `0640` vergeben. RTSP-Zugangsdaten nur in dieser geschützten Datei aufbewahren.
3. `sudo bash scripts/install-camera-linux.sh` ausführen. Das Skript richtet eine eigene virtuelle Kameraumgebung ein, installiert versionsgebundene OpenCV-/ONNX-Runtime-Abhängigkeiten und prüft das Modellmanifest. Der zusätzliche systemd-Dienst wird installiert, aber **nicht automatisch gestartet**.
4. Erst nach Prüfung von Kameraquelle und experimentellem Modellstatus aktivieren: `sudo systemctl enable --now beekeeper-camera`. Bei einer lokalen `/dev/video`-Kamera fügt der Installer das Dienstkonto der Gruppe `video` hinzu. Bei RTSP ist diese Gruppe nicht erforderlich.
5. Mit `journalctl -u beekeeper-camera -f` Bildaufnahme, CPU-Auslastung, Versandwarteschlange und Fehlererholung prüfen, bevor die Station unbeaufsichtigt betrieben wird.

Der optionale Dienst nutzt V4L2 für lokale Linux-Kameras, DirectShow unter Windows und FFmpeg für Netzwerk-/Dateiquellen. Der Installer lädt weder Modellgewichte noch Kamerabilder herunter. Erkennungen bleiben bis zur menschlichen Prüfung **unbestätigte Kandidaten**, keine gesicherte Art- oder Nestbestimmung.

## Netzwerk, Datenschutz und Funk
- Beide HTTP-Dienste hören ausschließlich lokal. Für Fernzugriff ist ein separat geprüfter, authentifizierter TLS-VPN-/Reverse-Proxy-Zugang nötig; Ports 8765 und 8787 **niemals per Portweiterleitung freigeben**.
- Die Bridge überträgt begrenzte Metadaten, keine Rohbilder, Videos, Audiodaten oder genauen GPS-Koordinaten.
- Stationsereignisse sind schutzbedürftig. Datenträgerverschlüsselung und Sicherungswerkzeuge verwenden; Backups werden von der Anwendung selbst nicht verschlüsselt.
- MeshCore wird durch den Basisinstaller weder installiert noch gestartet. Funkhardware, Antennen, Sendezeiten, Reichweite, Frequenzregeln, Richtungskalibrierung und echte Triangulation benötigen gesonderte Feldprüfungen.
- Ein Triangulationsergebnis ist eine **Suchhypothese**, kein bestätigter Neststandort.

## Prüfen ohne Installation
Dieser Modus prüft Repository-Struktur sowie Python-/Node-Versionen, ohne root-Rechte, Schlüssel oder gestartete Prozesse:

~~~sh
bash scripts/install-linux.sh \
  --beekeeper-repo "$PWD" \
  --monitor-repo "../Beekeeper-Monitor" \
  --validate-only
~~~
