# Register externer Modelle und Datensätze – 20.11.2026

**Zweck:** Wiederverwendbare Erkennungsmodelle für *Vespa velutina* finden, ohne Dateien mit ungeklärten Modell- oder Datenrechten zu übernehmen. Dies ist eine technische Vorprüfung und **kein Rechtsgutachten**.

## Bewertung der Kandidaten

| Kandidat | Festgestellte Hinweise | Entscheidung |
|---|---|---|
| [vespCV/hornet3000](https://github.com/vespCV/hornet3000) | Öffentliches Repository mit GPL-3.0-Kennzeichnung, am 07.06.2025 archiviert. Enthält YOLOv8s-`best.onnx` (44.737.849 Byte) und `best.pt`. Laut README stammen Trainings-/Validierungsbilder überwiegend von waarnemingen.nl/Observation.org mit angeblich genehmigten und teilbaren Lizenzen; der Datensatz wird auf Kaggle genannt. Im geprüften README/Handbuch wurden keine eindeutige Lizenz der konkreten Modellgewichte, keine Lizenzliste je Bild, kein unveränderlicher Trainingsdatensatzstand und keine vollständige Rechtekette gefunden. | **ZURÜCKSTELLEN – nicht bündeln, weitergeben oder freigeben.** Rechte an den Gewichten, genaue Datensatzversion, Rechte/Urhebernennung je Bild und zugehörige Trainingsquellen bei den Verantwortlichen anfragen. Die GPL-Angabe allein belegt diese Rechte nicht. |
| [vespCV/vespcv](https://github.com/vespCV/vespcv) | Enthält `best.pt` (19.174.547 Byte) und Trainingsergebnisse. GitHub meldet als Lizenz `NOASSERTION`; eine vollständige Rechtekette für Modell und Datensatz wurde nicht belegt. | **ZURÜCKSTELLEN – kein Import.** Ausdrückliche Lizenz- und Herkunftsnachweise anfordern. |
| [andrw3000/vespai](https://github.com/andrw3000/vespai) | Die LICENSE-Datei nennt CC BY-NC-SA 4.0 für Repository-Inhalte und AGPL-3.0 für enthaltenen Modellcode. YOLOv5-Gewichte und Verweise auf Plainsight-Annotationen sind vorhanden. | **FÜR ALLGEMEINE WEITERGABE ABLEHNEN.** Die Bedingungen „Nicht kommerziell“ und „Weitergabe unter gleichen Bedingungen“ beschränken nachgelagerte Nutzung und erfüllen nicht das Ziel einer allgemein frei wiederverwendbaren Verteilung. Diese Gewichte oder diesen Code nicht ungeprüft übernehmen. |
| [PauMonterosa/vespa-velutina-tracker](https://github.com/PauMonterosa/vespa-velutina-tracker) | Das README nennt experimentelle YOLOv8s-Kennzahlen und eine lokal vorhandene `best.pt`, aber die Modellbinärdateien werden von Git ignoriert. Außerdem fehlen laut README die genaue Datensatz-YAML und Lizenzen der Ausgangsdaten. | **ZURÜCKSTELLEN – keine nutzbare Gewichtsdatei und keine vollständige Rechtekette.** Die berichteten Kennzahlen sind kein Leistungsnachweis für dieses Projekt. |
| [Roboflow ISR Vespa-velutina-Datensatz v1](https://universe.roboflow.com/institute-of-systems-and-robotics-isr/vespa-velutina-hihv9-upzpe/dataset/1) | Die Datensatzseite nennt CC BY 4.0 und 1.508 Bilder im Versionsdatensatz. Die generierte Ansicht beschreibt Augmentierung sowie Trainings-/Validierungs-/Testaufteilung. | **NUR DATENKANDIDAT – nicht importiert.** Berechtigung der hochladenden Person, Originalbildquellen, Urhebernennung und Lizenz je Bild, aktuelle Bedingungen, Überschneidungen zwischen Datensätzen und Rechte zur Weitergabe des bearbeiteten Datensatzes vor Nutzung prüfen. Die CC-BY-Angabe auf der Plattform allein belegt nicht die Zustimmung sämtlicher Fotografen. |

## Lizenzrechtliche und technische Regeln
1. Niemals annehmen, dass eine Softwarelizenz automatisch für separat trainierte Gewichte, Originalfotos, fremde Datensätze oder Modellausgaben gilt.
2. Auch Trainingsdatensätze können Rechte und Bedingungen beeinflussen. Eine dokumentierte rechtliche Prüfung der **konkreten Gewichtsdatei** und des Datensatzes ist erforderlich.
3. Bedingungen mit `NonCommercial` werden für das allgemeine Verteilungsprofil von BeeKeeper3000 nicht akzeptiert: Auch ein nicht gewinnorientiertes Projekt kann kommerzielle Nutzer oder Nutzungen haben.
4. Modelle mit fehlenden, mehrdeutigen oder unvereinbaren Nutzungsrechten nicht in das öffentliche Repository importieren.
5. Vor einer Freigabe durch `camera/model_manifest.py` müssen exakte Modell-SHA-256, Originaldateiadresse, URL des Lizenznachweises, namentliche prüfende Person, Prüfzeitstempel mit Zeitzone und ausdrückliche Berechtigungen für Inferenz und Weitergabe vorliegen.
6. Nach Klärung der Rechte das Modell in den unterstützten ONNX-Ausgabevertrag umwandeln, Werkzeuge/Versionen/Prüfsummen dokumentieren und mit unabhängig annotierten, zurückgehaltenen Testdaten bewerten.
7. Kennzahlen aus fremden README-Dateien **nicht** als eigene BeeKeeper3000-Ergebnisse veröffentlichen.

## Aktueller Stand
**Kein externes Modell ist für BeeKeeper3000 freigegeben.** Das standardmäßig sperrende Modellmanifest bleibt daher ohne genehmigtes Produktionsmodell. Die Auswertungswerkzeuge und Kamerapipeline sind für einen korrekt lizenzierten Kandidaten vorbereitet. Es dürfen weder Erkennungen erfunden noch ein installiertes Modell vorgetäuscht werden.

## Quellen
- vespCV/hornet3000: https://github.com/vespCV/hornet3000
- vespCV/vespcv: https://github.com/vespCV/vespcv
- VespAI: https://github.com/andrw3000/vespai
- Vespa Velutina Tracker: https://github.com/PauMonterosa/vespa-velutina-tracker
- Roboflow ISR Datensatz v1: https://universe.roboflow.com/institute-of-systems-and-robotics-isr/vespa-velutina-hihv9-upzpe/dataset/1
- Von vespCV genannter Kaggle-Datensatz: https://www.kaggle.com/datasets/marcoryvandijk/vespa-velutina-v-crabro-vespulina-vulgaris
