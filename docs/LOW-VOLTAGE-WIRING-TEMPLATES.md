# BeeKeeper3000 – Verdrahtungsvorlagen für Niederspannung

**Stand:** ausschließlich konzeptionelle Anschlussbeispiele. Vor einem Aufbau müssen die genauen Platinenrevisionen, Bauteilnummern, Leitungsquerschnitte und Sicherungen anhand der Herstellerdatenblätter und gemessenen Belastungen ausgewählt werden. **Dies sind keine zertifizierten Schaltpläne.**

## 1. Teilnahme nur mit dem Smartphone

```text
Android / iPhone
  ├─ eingebaute Kamera → vom Nutzer gewähltes Foto → lokaler PWA-Speicher
  ├─ GPS/Kompass → einmalige Berechtigung → ausschließlich lokale Metadaten
  └─ WLAN / Mobilfunk → ausschließlich manueller Metadatenexport
Keine zusätzliche Elektronik, Funk- oder Stromverkabelung nötig.
```

## 2. USB-GNSS-Empfänger (alternativ UART-TTL)

```text
USB-GNSS-Empfänger ──USB──> Edge-PC / Raspberry Pi

UART-Anschluss (erst nach Prüfung der Spannungspegel):
GNSS TX ───────────────> Host RX
GNSS RX <─────────────── Host TX (optionale Konfiguration)
GNSS GND ────────────── Host GND
GNSS VCC <───────────── dokumentierte, geregelte Versorgung
```

Logikpegel von 3,3 V beziehungsweise 5 V und Versorgungsspannung am **konkreten Empfänger** prüfen. Niemals einen 5-V-UART-Ausgang an einen Eingang anschließen, der nur 3,3 V verträgt. NMEA-Fixqualität, HDOP/Genauigkeit und Zeitstempel aufzeichnen. Aus Koordinaten allein lässt sich keine Genauigkeit ableiten.

## 3. Umweltsensoren über galvanisch getrenntes RS-485 / Modbus RTU

```text
Sensor A A(+) ───────────────┐
Sensor B A(+) ───────────────┼── verdrilltes Adernpaar A(+) ── isoliertes RS-485 A
Sensor A B(-) ───────────────┤
Sensor B B(-) ───────────────┴── verdrilltes Adernpaar B(-) ── isoliertes RS-485 B
Sensorbus-Bezug/Schirm ────────── nur nach Transceiver-/Standortplanung
Gateway USB/UART ─────────────── Edge-Rechner
120-Ohm-Abschluss nur an den beiden physikalischen Busenden, soweit erforderlich.
```

Eine lineare Busstruktur verwenden, keine Sternverkabelung, sofern der ausgewählte Transceiver beziehungsweise das Netz dies nicht ausdrücklich unterstützt. Vorspannung und Abschlusswiderstände nach Herstellerangaben einstellen. Außenleitungen benötigen eine für die Installation geeignete galvanische Trennung und Überspannungsschutz.

## 4. Solare Gleichstromversorgung (Konzept)

```text
PV-Modul → passender MPPT-/PWM-Laderegler ↔ geschützter Akku/BMS
                                              |
Akku-Plus → DC-Sicherung nahe am Akku → Gleichstromverteilung
                                       ├─ geregelte Versorgung → Edge-Rechner
                                       ├─ geeignete DC-Versorgung → Kamera
                                       └─ geeignete DC-Versorgung → Funk / Sensoren
Alle Rückleiter → geplante gemeinsame oder getrennte Rückführung laut Datenblättern
```

Ein Solarmodul niemals direkt an Akku oder Einplatinenrechner anschließen. Den täglichen Energiebedarf in Wh aus gemessenen Spitzen- und Durchschnittslasten, Anlaufströmen, Einschaltdauer, Temperatur, gewünschten Autonomietagen und Einstrahlung im ungünstigsten Monat berechnen. Sicherungen, Leitungsquerschnitte, Steckverbinder, BMS, Wandler und Gehäuse nach Datenblatt und Sicherheitsreserven auswählen. Netzspannung, Gebäudeinstallation, Blitzschutz, Mast-Erdung und dauerhafte Außeninstallation gehören in die Hände qualifizierter Fachkräfte.

## 5. Vorlage für die Stückliste

| Bauteil | Vor der Bestellung erforderlicher Nachweis |
|---|---|
| Edge-Rechner / Smartphone | Genaues Modell, Revision, Betriebssystem und unterstützte Anschlüsse |
| Kamera / GNSS / Sensor | Datenblatt, Anschlussbelegung, Spannung, Strom und Umgebungsfestigkeit |
| Funkmodul | Exakte Firmware, erlaubtes Frequenzband, Leistung, Sendezeit und zugelassene Antenne |
| Netzteil / Wandler | Eingangsspannungsbereich, geregelter Ausgang, Dauer-/Spitzenstrom, thermische Belastbarkeit |
| Sicherung / Halter / Leitung | DC-Abschaltvermögen, Auslösekennlinie, Leitungslänge, Temperatur und Spannungsabfall |
| Gehäuse / Kabelverschraubung | Schutzart (IP), UV-/Temperaturbeständigkeit, Kondenswasser und Wartungszugang |
| Überspannungsschutz / Isolation | Für die Installation bemessene Komponenten und Erdungskonzept |

Es werden bewusst **keine allgemeingültigen GPIO-Pinnummern oder ungeprüften Bauteilnummern** angegeben. Der endgültige, nachbaubare Schaltplan muss anhand der exakten Herstellerdatenblätter und von einer qualifizierten Elektro-/Funkfachkraft geprüft werden. Keine Eigenarbeiten an Netzspannung und keine unerlaubte Veränderung von Senderleistung oder Antennengrenzen.
