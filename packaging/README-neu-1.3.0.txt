────────────────────────────────────────────────────────────────────────
NEU IN 1.3.0
────────────────────────────────────────────────────────────────────────
· ALTE HANDYS UND TABLETS NUTZEN: Android-App „Hornet3000 Station“ (läuft laut Manifest ab Android 2.2, Baujahr 2010) und
  eine Handy-Seite für alte iPhones/Android-Browser (Adresse des Wächters + /m, läuft ab iOS 9). Ein Altgerät kann
    – als KAMERA dienen (Einrichtung → Kamera → „Altgerät als Station verwenden“, Quelle „push“, speichern, neu starten),
    – als ALARM-ANZEIGE dienen (Ton, Vibration, Bild der Sichtung),
    – ein Foto auswerten lassen (ohne Alarm).
  Die App holt man auf dem Altgerät von der Seite /m des Wächters (Link „Android-App laden“) oder man kopiert die Datei
  aus dem Ordner „mobil“. Eine iPhone-App gibt es NICHT (dafür braucht es einen Mac mit Xcode); iPhones nutzen die Seite /m.
  Was auf welcher Version geht und was nur berechnet statt auf einem echten Gerät erprobt ist: docs/MOBIL.md.
· Nicht getestet: Die Android-App wurde NIE auf einem Gerät oder Emulator ausgeführt (Kamera, Oberfläche, Ton). Geprüft ist
  der Netzwerkteil gegen den echten Wächter, der Bau gegen die Android-2.2-Systembibliothek und die Signatur.
  Bitte beim ersten Einsatz die Checkliste in docs/MOBIL.md durchgehen und Ergebnisse zurückmelden.
· Sicherheit: Die Station ist ein neuer Netzwerk-Eingang. Er verlangt den Zugangsschlüssel, prüft jedes Bild vor dem
  Entpacken (Format, Größe, Maße), erlaubt höchstens 5 Bilder/s und nur eine aktive Station. Einzelheiten: docs/SICHERHEIT.md.

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

