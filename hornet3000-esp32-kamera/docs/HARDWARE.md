# Hardware

## Einkaufsliste

| Teil | Hinweis |
|---|---|
| **AI-Thinker ESP32-CAM** mit OV2640-Kamera und **PSRAM** (4 MB) | der Normalfall bei diesem Modul; ohne PSRAM startet die Firmware nur mit kleinem Bild (320×240) |
| USB-Seriell-Adapter **3,3 V** (FTDI, CP2102, CH340) **oder** Basisplatine „ESP32-CAM-MB“ | das Modul hat keinen USB-Anschluss; Adapter nur zum Flashen und für die serielle Konsole |
| Netzteil **5 V, mindestens 2 A** (Handy-Ladegerät reicht, wenn es gut ist) | Spitzen beim WLAN-Senden sind hoch; schwache Netzteile führen zu „Brownout“-Neustarts |
| Elektrolytkondensator **470–1000 µF**, 10 V oder mehr | direkt zwischen 5V und GND am Modul; glättet Stromspitzen |
| kurzes, dickes USB-Kabel oder Litze ≥ 0,5 mm² | lange dünne Kabel verlieren Spannung (unter ca. 4,7 V am Modul wird es unzuverlässig) |
| Steckbrücken (Dupont) | zum Flashen |
| wetterfestes Gehäuse (IP65) mit klarem Fenster | siehe Abschnitt Gehäuse |
| Trockenmittel-Beutel (Silicagel) | gegen Beschlag |

Die Richtwerte zur Stromaufnahme (grob 150–250 mA im Betrieb, kurze Spitzen deutlich darüber) stammen aus Herstellerangaben und
Erfahrungsberichten, **nicht aus eigenen Messungen** an diesem Aufbau.

## Verdrahtung zum Flashen (USB-Seriell-Adapter, 3,3 V!)

| ESP32-CAM | Adapter |
|---|---|
| 5V | 5V (bei schwachem Adapter besser externes Netzteil) |
| GND | GND |
| U0R (GPIO3) | TX |
| U0T (GPIO1) | RX |
| **IO0** | **GND** (nur zum Flashen verbinden!) |

Ablauf: IO0 mit GND verbinden → Strom anstecken bzw. kurz RESET (Taste auf der Rückseite) drücken → flashen → **IO0-Brücke entfernen** →
RESET drücken. Bleibt die Brücke drin, startet das Modul nicht, sondern wartet auf Flashdaten.
Mit der Basisplatine ESP32-CAM-MB entfällt die Verkabelung; dort per Taste „IO0“ halten, falls der Adapter das nicht selbst macht.

## Betrieb

* Nur 5 V und GND anschließen (Pin „5V“, nicht „3V3“). Die Firmware hält die helle LED (GPIO 4) immer aus: Strom, Wärme und Bienen.
* Betriebsspannung messen: am Modul sollten es **mindestens 4,75 V** sein, auch wenn die Kamera streamt.
* WLAN: 2,4 GHz. Die PCB-Antenne ist schwach; Empfang am Aufstellort mit dem Handy prüfen. Wer es braucht, kann (bei Platinen mit Wahllötstelle) auf eine externe Antenne umlöten – das ist plattenabhängig und hier nicht erprobt.
* Die Firmware startet bei WLAN-Verlust neu (nach 5 Minuten) und startet nach 10 Kamerafehlern in Folge neu; geplanter Neustart alle 7 Tage (nur wenn gerade niemand zuschaut).

## Linse und Bildausschnitt

* Der OV2640 hat einen Fokus-Ring, der werkseitig lackiert/verklebt ist. Mit einer kleinen Zange oder einem Fingernagel vorsichtig drehen, während `/jpg` im Browser läuft. Für Nahaufnahmen (Köderstation, Flugloch) auf 20–40 cm scharfstellen; ab Werk ist die Linse meist auf größere Entfernung scharf gestellt.
* Rechnung (Schätzung, nicht im Feld geprüft): Die Standardlinse hat etwa 65° Bildwinkel. Bildbreite ≈ 1,27 × Abstand. Bei VGA (640 px) und 30 cm Abstand sind das etwa 17 px je Zentimeter; eine 3 cm lange Hornisse wäre dann rund 50 px lang, bei 100 cm Abstand nur noch ca. 15 px. **Deshalb: möglichst nahe (≤ 40 cm) an Flugloch bzw. Köder.**
* Ob das Erkennungsmodell bei OV2640-Bildern in VGA zuverlässig arbeitet, wurde **nicht** geprüft. Bitte mit echten Aufnahmen testen (Standbild speichern, im Wächter über die Testfunktionen prüfen).
* Gegenlicht und Spiegelungen in der Scheibe vermeiden; Scheibe dicht an der Linse, sauber, nicht schräg.
* Bild drehen/spiegeln: in `include/config.h` (`CAM_VFLIP`, `CAM_HMIRROR`) und neu bauen.

## Gehäuse und Montage

* IP65-Gehäuse mit klarer Abdeckung oder eigenes Fenster (Acryl). Linse möglichst nah an die Scheibe, Dichtring/Schaumstoff um die Linse gegen Streulicht.
* Kabeldurchführung nach unten (Tropfschlaufe), Trockenmittel hineinlegen, nach Montage dicht verschließen.
* Direkte Sonne heizt das Gehäuse; Schattenseite oder Sonnendach. Das Modul wird beim Streamen warm; Lüftung ist ohne Zusatz nicht vorgesehen.
* Montage mit Abstand zum Flugloch, damit der Flugbetrieb nicht gestört wird; Kamera ruhig befestigen (Wackeln erzeugt Bewegung im Bild).
* Das Gehäuse muss für den Fall einer **Rücksetzung** erreichbar sein (RESET-Taste, ggf. Zugang zu serieller Schnittstelle).
