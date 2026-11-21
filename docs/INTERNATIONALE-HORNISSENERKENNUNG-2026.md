# Internationale Hornissenerkennung: Quellen, Lizenzlage und technische Nutzung

Stand: 21. November 2026. Dieses Dokument ist eine **Quellen- und Integrationsübersicht**, keine Bestätigung einsatzfähiger KI-Modelle.

## Forschungs- und Entwicklungsquellen

| Projekt | Technik und Nutzen | Rechte / Vorsicht | Quelle |
| --- | --- | --- | --- |
| vespCV | Raspberry Pi 4/5, Kamera, YOLO11, lokale Detektion und E-Mail-Alarm; interessant als Ereignisproduzent fuer die lokale BeeKeeper3000-Bridge | Code GPLv3; Modellgewichte, Bilder und Abhaengigkeiten gesondert pruefen | https://github.com/vespCV/vespcv |
| VespAI | Raspberry Pi 4, YOLOv5s, Hornissen-Klassifikation; wissenschaftlich dokumentierte Feldversuche | CC BY-NC-SA 4.0 und in der Publikation beschriebenes Anfrageverfahren; keine pauschale kommerzielle Freigabe | https://www.nature.com/articles/s42003-024-05979-z ; https://github.com/andrw3000/vespai |
| hornet3000 | Headless Raspberry Pi, YOLOv10n, Kamera und lokale Bildablage; Bau- und Testreferenz | Seit Juni 2025 archiviert; Datensatz-/Gewichtelizenzen separat pruefen | https://github.com/vespCV/hornet3000 |
| Vespa Smart Trap / VST-ONE | ESP32, Kameramodul und modulare Grove-Komponenten; Proof of Concept | GNU Public License laut Projekt; Feldleistung nicht fuer BeeKeeper3000 belegt | https://github.com/jeroen-kanters/Hornet_Trap |
| Waspinator | Raspberry Pi 5, YOLO26n, eigene Feldprototypen; Vergleich von Fehlalarmen und Inferenzzeit | AGPL-3.0 laut Projektwebsite; Datensatz und Modell separat pruefen | https://waspinator.dev/ |
| BuzzCopper | Solar-ESP32, Offline-Pufferung, spaetere Uebertragung; Vorbild fuer stromsparende Stationen | Projekt kuendigt offene Artefakte an; einzelne Downloads und Rechte vor Nutzung verifizieren | https://www.buzzcopper.org/about |

## Integration in BeeKeeper3000 und Beekeeper-Monitor

1. **Nicht blind kopieren**: Fremdcode, Gewichte, Datensaetze und Hardwaredesigns haben unterschiedliche Rechte. Vor Import Lizenz, Version, Herkunft und SHA-256 dokumentieren.
2. **Modular anbinden**: Kameradetektoren nur als externe Ereignisproduzenten an die bestehende authentifizierte lokale Bridge anbinden. Bestehende Schemas und Zugriffskontrollen nicht umgehen.
3. **Datensparsam bleiben**: Ohne gesonderte Freigabe nur notwendige Ereignismetadaten; keine automatischen Foto-, Audio- oder GPS-Uploads.
4. **Keine Scheinpraezision**: Konfidenz eines Fremdmodells ist keine bestaetigte Artbestimmung. Keine automatischen Fallen- oder Nestaktionen aus unvalidierten Treffern ableiten.
5. **Real testen**: Unabhaengige Standorte und Jahreszeiten, Vespa crabro, andere Wespen, Bienen und Schwebfliegen; Precision, Recall, Fehlalarmrate, Strombedarf und Offline-Verhalten messen.
6. **Produktgrenze**: BeeKeeper3000 liefert lokale Sensorik/Adapter, Beekeeper-Monitor zeigt unbestaetigte Beobachtungen. Eine validierte KI-Feldfreigabe ist noch nicht vorhanden.

## Verbundene Dokumentation

- [Beekeeper-Monitor: internationaler Technikvergleich](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/docs/INTERNATIONAL-HORNET-DETECTORS-2026.md)
- [VespaGuard Integrationslandkarte](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/main/docs/VESPAGUARD-INTEGRATION.md)

**Verteilung:** Dieses Dokument ist im GitHub-Repository lesbar. Es wird dadurch keine neue oeffentliche PWA-Website aktiviert und kein externes Portal automatisch beliefert.
