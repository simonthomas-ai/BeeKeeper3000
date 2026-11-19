────────────────────────────────────────────────────────────────────────
NEU IN 1.2.0
────────────────────────────────────────────────────────────────────────
· FUNKNETZ: Die Stationen können sich bei einer bestätigten Sichtung gegenseitig melden – über LoRa-Funk (MeshCore,
  868 MHz, Funkgerät am USB-Anschluss) und/oder über Freenet (River-Chatraum, Internet). Beides ist ab Werk
  AUSGESCHALTET und wird unter „Einrichtung → Funknetz“ eingeschaltet. Reiter „Funknetz“: Stand, Protokoll, Testsendung.
  Anleitung, Schlüssel, Sendezeit-Regeln und Grenzen: docs/FUNKNETZ.md (im Programmordner).
  Wichtig: Eine Funkmeldung ist immer UNGEPRÜFT und löst bei den Nachbarn nur eine Textmeldung aus, keinen Foto-Alarm.
  Wer den Kanalschlüssel bzw. den River-Raum kennt, kann Meldungen im Namen jeder Station schicken – Schlüssel nur an
  vertraute Imker geben.
· Nicht getestet: der LoRa-Weg an echter Funkhardware (nur gegen eine Geräte-Attrappe und die offizielle Bibliothek
  abgeglichen) und Freenet im offenen Netz (nur ein lokaler Knoten). Bitte beim ersten Einsatz mit zwei Geräten prüfen
  (docs/PRUEFSTATUS.md). Freenet-Knoten und riverctl sind NICHT im Installer enthalten.
· ABSICHERUNG: Schutz vor Angriffen aus dem Browser (fremde Webseiten können nichts auslösen), strenge
  Inhaltsrichtlinie, begrenzte Anfragegrößen, geprüfte Eingaben in der Einrichtung, Einstellungsdatei nur für den
  Besitzer lesbar. Einzelheiten und bewusste Grenzen: docs/SICHERHEIT.md.
· Aktualisierte Bibliotheken (Pillow 13.0.0, certifi 2026.10.23), neu: pyserial für das Funkgerät.

