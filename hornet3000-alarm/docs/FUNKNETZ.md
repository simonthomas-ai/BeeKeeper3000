# Funknetz – Stationen melden sich gegenseitig (Hornet3000 1.3.0)

Sieht eine Station die Asiatische Hornisse, meldet sie das automatisch an die Nachbarstationen. Dafür gibt es zwei
voneinander unabhängige Wege, die einzeln oder zusammen laufen können:

| Weg | Reichweite | Braucht | Stand |
|---|---|---|---|
| **LoRa über MeshCore** (868 MHz) | je nach Gelände 2 – 15 km, über Zwischenstationen mehr | ein MeshCore-Funkgerät am USB-Anschluss | Software gegen eine **Geräte-Attrappe** und die offizielle `meshcore`-Bibliothek geprüft, **nicht an echter Funkhardware** |
| **Freenet (River-Chatraum)** | weltweit, über das Internet | laufender Freenet-Knoten + `riverctl` | gegen einen **echten lokalen Freenet-Knoten** geprüft (Freenet ist selbst noch Alpha-Software) |

Eine Funkmeldung ist **immer ungeprüft**. Sie ersetzt nie den eigenen Blick auf den Bienenstand und löst bei den
Nachbarn nur eine Textmeldung aus – keinen Foto-/Video-Alarm.

## Was gesendet wird

Nur wenn die eigene Station eine **neue** Sichtung oder eine **Verstärkung** (mehr Tiere) bestätigt hat und nicht
stummgeschaltet ist. Testalarme und stummgeschaltete Zeiten gehen nie ins Funknetz. Kein Foto, kein Ton, keine
Kameradaten, keine Adressen: nur Stationsname, Anzahl, Sicherheit (%), Ergebnis der KI-Prüfung, auf Wunsch der auf ca. 1 km
gerundete Standort und eine kurze Notiz.

Format (eine Textzeile, höchstens 118 Byte, damit sie in eine LoRa-Nachricht passt):

```
H3K1|<Typ>|<Kennung>|<Station>|<Anzahl>|<Sicherheit>|<KI>|<Breite>|<Länge>|<Notiz>
Typ: A Sichtung · U Verstärkung · T Test · R Quittung      KI: - nicht geprüft · J bestätigt · N widerspricht · ? unklar
```

## Einrichtung LoRa (MeshCore)

1. Funkgerät mit der **MeshCore-„Companion USB“-Firmware** versehen (Flasher auf meshcore.io; Kompatibilität des Boards dort
   prüfen) und per USB am Rechner anstecken. Frequenzvoreinstellung der Region wählen (EU: 868-MHz-Voreinstellung).
2. In der App: **Einrichtung → Funknetz – LoRa**: Anschluss wählen („Angeschlossene Geräte suchen“ oder `auto`), Haken setzen.
3. **Kanalschlüssel**: alle Stationen eines Netzes brauchen denselben 32-stelligen Hex-Schlüssel. Einmal erzeugen und
   an die Nachbarn geben (nicht öffentlich posten):
   `python3 -c "import secrets; print(secrets.token_hex(16))"`
   Das Programm legt damit am Gerät einen eigenen Kanal („hornet3000“, Platz 1–7) an. Der öffentliche Kanal 0 wird **nie** benutzt.
4. Reiter **Funknetz → „Funknetz-Test senden“**. Antwortet eine Nachbarstation, erscheint eine Quittung im Protokoll.

Sendezeit: In Europa darf im 868-MHz-Band je nach Teilband meist nur 1 % der Zeit gesendet werden. Das Programm rechnet die
Sendedauer jeder Nachricht aus (Semtech-Formel) und hält 1 % ein (einstellbar bis höchstens 10 %). Ist das Budget leer,
wartet die Nachricht (Alarme vor Quittungen) oder verfällt nach 5 – 30 Minuten.

## Einrichtung Freenet (River)

Freenet läuft als eigener Knoten neben dem Programm; River ist der Chatraum darauf. Beides ist **nicht** im Installer enthalten.

1. Freenet-Knoten und `riverctl` installieren (Anleitung auf freenet.org; mit Rust: `cargo install freenet riverctl`).
2. Knoten starten (lokal, z. B. `freenet local --ws-api-address 127.0.0.1 --ws-api-port 7509 …`).
3. Eine Station legt einen **privaten Raum** an (`riverctl room create --name hornet3000 --nickname <Station> --private`) und
   erzeugt Einladungen (`riverctl invite create <Raum>`). Die anderen treten mit `riverctl invite accept …` bei – oder in
   der App unter **Einrichtung → Funknetz – Freenet → „Einladung annehmen“**.
4. In der App: Raum-Schlüssel (Owner-Key), Knotenadresse (`ws://127.0.0.1:7509`) und Pfad zu `riverctl` eintragen, Haken setzen.

Private River-Räume sind Ende-zu-Ende verschlüsselt (AES-256-GCM). Nur Mitglieder lesen und schreiben.

## Schutz vor Missbrauch und Überflutung

Alles aus dem Funknetz ist Fremdtext und wird so behandelt:

* **Streng geprüftes Format**: alles, was nicht exakt dem H3K1-Format entspricht, wird verworfen. Steuer-, Richtungs- und
  unsichtbare Zeichen, `|`, `@`, Links, Mailadressen und IP-Adressen werden entfernt; Längen und Zahlenbereiche sind begrenzt.
* **Mengenbegrenzung**: je Station höchstens 40 Nachrichten und 8 Sichtungen pro 10 Minuten; neue, unbekannte Stationen
  höchstens 5 Sichtungen pro Stunde (in `MESH_TRUSTED` eingetragene Stationen sind davon ausgenommen); zusätzlich ein
  Gesamt-Zufluss-Limit. Wird eine Station begrenzt, erscheint **einmal pro Stunde** ein Hinweis, kein Dauerfeuer.
* **Keine Doppelten, keine Schleifen**: gleiche Kennung wird nur einmal bearbeitet (auch nach Neustart); eigene Meldungen, die
  über den anderen Weg zurückkommen, werden erkannt.
* **Quittungen** sind zurückhaltend (verzögert und unterdrückt, wenn schon eine andere Station quittiert hat).
* Begrenzte Warteschlangen (200 Nachrichten, 50 Quittungen) und ein begrenztes Protokoll (20 000 Zeilen).
* Die Oberfläche zeigt Fremdtext ausschließlich als Text an (geprüft im echten Browser mit eingeschleustem HTML).

## Bekannte Grenzen (bitte lesen)

* **Gemeinsames Geheimnis**: Wer den LoRa-Kanalschlüssel kennt bzw. Mitglied im River-Raum ist, kann Meldungen im Namen
  *jeder* Station schicken oder Meldungen einer Station unterdrücken. Das Format ist nicht einzeln signiert. Schlüssel nur an
  vertrauenswürdige Imker geben; bei Missbrauch Schlüssel wechseln. Deshalb: **ungeprüft** und kein Alarm mit Foto.
* LoRa-Funk ist physikalisch störbar (Störsender, Wetter, Gelände). Kein Ersatz für die eigene Kontrolle.
* Das Programm hat **nicht** an echter Funkhardware laufen können. Das Funkprotokoll wurde gegen die Dokumentation und die
  offizielle Python-Bibliothek abgeglichen und gegen eine Attrappe getestet; die erste Inbetriebnahme mit zwei echten Geräten
  steht aus (Checkliste in `PRUEFSTATUS.md`).
* Freenet ist laut Projekt noch Alpha: Knoten-/`riverctl`-Versionen können das Verhalten ändern. Das Programm meldet in der
  Oberfläche, wenn der Knoten oder `riverctl` nicht erreichbar sind, und verbindet sich selbstständig neu.
* Die Standortangabe ist freiwillig, auf ca. 1 km gerundet und nur für Teilnehmer des Netzes sichtbar.
