# Datensatz- und Trainingspfad für die Insektenerkennung

**Prüfstand: 23.11.2026 – kein Training durchgeführt.** In diesem Checkout gibt es keine Bilddaten, Annotationen oder Modellgewichte. Die ursprüngliche Recherche unten bezog sich auf Objektdetektion mit Boxen. Die danach getroffene Arbeitsentscheidung ist stattdessen **Multilabel-Bildklassifikation** (mehrere Labels pro Bild, `[]` für geprüfte Negativbilder) mit dem lokalen JSONL-Vertrag. Der ausführbare Validator und Trainingspfad stehen in [MULTILABEL-CLASSIFICATION-TRAINING.md](MULTILABEL-CLASSIFICATION-TRAINING.md); sie ersetzen die nachfolgenden historischen Detektionsvoraussetzungen und Monitor-Trainingskommandos. Auch die aktuelle Trainingsdokumentation des Monitor-Repositories beschreibt keinen vollständigen freigegebenen Datensatz. Es wurden für diese Prüfung keine Bilder oder Gewichte heruntergeladen, gespeichert oder weitergegeben.

## Zielklassen und Aufgabe

Die zuvor untersuchte Monitor-Revision spezifiziert einen **Siebenklassen-Objektdetektor**. Die aktuell vereinbarte BeeKeeper-Dataset-Taxonomie für Bildklassifikation nutzt dieselben Slugs, aber nicht das Box-/Detektormodell. Die Klassen standen in `training/data.yaml` und `training/class_schema.py` des Monitor-Repositories:

| ID | Klasse |
|---:|---|
| 0 | `vespa_velutina` |
| 1 | `vespa_crabro` |
| 2 | `other_vespidae` |
| 3 | `apis_mellifera` |
| 4 | `bombus_spp` |
| 5 | `syrphidae` |
| 6 | `other_insect` |

Die Taxonomie ist ein Zielvertrag, keine Behauptung, dass Beispiele oder freigegebene Gewichte vorhanden sind. `unknown`/unbestimmte Fälle sind **keine** zusätzliche implizite Zuordnung zu `other_insect`; eine fachlich bestätigte Zuordnungsregel ist erforderlich. Das Monitor-Trainingsdokument nennt vorläufige Zuordnung von *Vespula* zu `other_vespidae`, die noch fachlich zu bestätigen ist.

## Tatsächlicher Bestand und Quellenprüfung

### BeeKeeper3000-Checkout

- Rekursive Dateiprüfung: keine ONNX-/PyTorch-/TFLite-Gewichte und keine Bilddateien.
- Der einzige gefundene CSV-Datensatz ist `network/field-test-template.csv` (123 Byte), eine leere Feldtestvorlage, keine Trainingsdaten.
- Es gibt keine Bilddateien, Boxannotationen, Provenienzdatei, Klassenfreigabe oder unabhängige Holdout-Auswertung. Es wurde kein Modell trainiert.

### Beekeeper-Monitor – nur gelesen, nicht geändert

Geprüft wurde `simonthomas-ai/Beekeeper-Monitor` am Commit [`d8972ea1d1bf3eb426866840b2fdefdbacadf764`](https://github.com/simonthomas-ai/Beekeeper-Monitor/commit/d8972ea1d1bf3eb426866840b2fdefdbacadf764). Der Commit enthält Trainings- und Provenienzwerkzeuge, aber keine eingecheckten Trainingsbilder, Annotationen oder Modellgewichte. Der Bericht zur iNaturalist-Suche meldet **1.000 unbegutachtete Metadaten-Kandidaten**, verteilt auf fünf Sichtungsgruppen: je 200 *Vespa velutina*, *Vespa crabro*, *Apis mellifera*, Hummeln (*Bombus terrestris*, *B. lapidarius*) und Wespen (*Vespula vulgaris*, *V. germanica*). Bei Hummeln und Wespen sind je zwei Arten mit 100 Kandidaten vertreten. Der Bericht weist ausdrücklich **0 Trainingsfreigaben und 0 erzeugte YOLO-Labels** aus. Seine Kandidatenverteilung deckt außerdem `syrphidae` und `other_insect` nicht gezielt ab.

Die begleitende Qualitätsprüfung sagt, dass Bildbytes nur für eine technische Sichtprüfung verarbeitet werden und diese weder Artbestimmung noch Trainingsfreigabe oder Boxannotation erteilt. Ein gesonderter Bericht nennt 63 CC0-API-Nachprüfungen für *V. velutina*; das belegt eine Lizenzcode-Übereinstimmung dieser Kandidaten, nicht die fachliche Identität, Bildtauglichkeit, vollständig geprüfte Rechtekette oder Trainingsfreigabe. Zum Prüfzeitpunkt war zusätzlich ein noch nicht abgelaufenes Actions-Artefakt `original-velutina-images` mit 162.829.646 Byte aus dem erfolgreichen Lauf [#45010096375](https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/45010096375) verfügbar (Ablauf: 06.12.2026). Der Workflow-Code verlangt CC0-Metadatenprüfung und Bildqualitätssichtung, hält aber ausdrücklich fest: keine fachliche Artprüfung, keine Annotationen und **0 freigegebene Trainingsbilder**. Artefaktinhalt und Bildanzahl wurden hier nicht abgerufen bzw. verifiziert; ein unannotierter Ein-Arten-Kandidatenbestand wäre ohnehin kein Siebenklassen-Datensatz.

### iNaturalist und GBIF – Metadaten sind keine fertigen Datensätze

Die iNaturalist-API liefert individuelle Beobachtungs- und Fotolizenzfelder. Eine Metadatenabfrage für `V. velutina`, `V. crabro` und `Vespula vulgaris` ergab bei einem `license=cc0,cc-by`-Abfragefilter 10.153, 14.409 bzw. 5.663 Beobachtungstreffer. Das sind **keine** Anzahlen rechtmäßig verwendbarer Trainingsbilder. In je 20 zurückgegebenen Beobachtungen enthielten die Photo-Objekte auch andere oder fehlende Rechtecodes: bei *V. velutina* 5 `cc-by-nc` und 2 ohne Lizenzcode; bei *V. crabro* 35 `cc-by-nc` und 4 `cc-by-sa`; bei *Vespula vulgaris* 10 `cc-by-nc`. Das ist ein begrenzter API-Stichprobenbefund, keine repräsentative Lizenzstatistik. Er zeigt, warum jede konkrete Mediendatei einzeln geprüft werden muss.

Auch GBIFs Filter `license` ist kein Ersatz für die Lizenzprüfung eines Multimedia-Objekts: Die Suchabfrage meldete 8.593 Occurrence-Datensätze mit `CC0_1_0` und 12.814 mit `CC_BY_4_0`. Beim geprüften CC0-Occurrence-Treffer 6129941638 waren die eingebetteten Bildlizenzen ebenfalls CC0. Beim geprüften CC-BY-Occurrence-Treffer 5938133414 lauteten die eingebetteten Fotolizenzen dagegen `CC BY-NC 4.0`. Daher dürfen Occurrence-Zahlen nicht als freigegebene Bildzahlen gezählt werden. Die `license` jedes einzelnen Mediums, Rechteinhaber, Urheber und Attribution müssen separat geprüft werden.

Die externen Forschungsquellen und Modellkandidaten sind im [Provenienzregister](MODEL-PROVENANCE-REGISTER-2026-11-20.md) erfasst. Kurz: Der Roboflow-ISR-Kandidat ist laut Datensatzseite ein einzelklassiger *V. velutina*-Datensatz mit CC-BY-Angabe, dessen Einzelbild-Rechtekette hier nicht bestätigt wurde; Waspinator hat ein Zwei-Klassen-Modell ohne hier geprüftes ONNX und mit offener Trainingsbild-Zuordnung; Hornet3000 ist ein Drei-Arten-Kandidat mit ungeklärter Rechte-/Graphkompatibilität. Keiner erfüllt den vollständigen Siebenklassen- und Freigabebedarf.

## Voraussetzungen vor einem Training

1. **Datenquelle und Rechte:** pro konkretem Bild unveränderliche Quell-URL/ID, Autor bzw. Rechteinhaber, exakter Medienlizenztext und -version, Attribution, Freigabe zur Nutzung für Training und Modellweitergabe, Abrufdatum sowie Hash der empfangenen Bytes. CC0/CC-BY-Metadaten allein beweisen nicht, dass der Uploadende die Rechte vergeben durfte. CC-BY-NC, CC-BY-ND, CC-BY-SA ohne gesonderte Prüfung, fehlende oder widersprüchliche Rechte bleiben ausgeschlossen.
2. **Echte Bildlabels:** Für den nun vereinbarten Klassifikationspfad müssen alle Zielklassen eines Bildes manuell fachlich geprüft und als Slugs eingetragen sein. Ein iNaturalist-Artnachweis allein belegt nicht, dass die Art im konkreten Bild sichtbar ist. `labels: []` ist nur nach aktiver Prüfung zulässig, dass keine der sieben Zielklassen abgebildet ist. Es werden keine Bounding-Boxes verwendet.
3. **Vollständige Zielabdeckung:** ausreichende und kamerarepräsentative Beispiele für alle sieben Klassen. Schwierige positive und negative Fälle, insbesondere *V. velutina* vs. *V. crabro*, andere Vespidae, Bienen, Hummeln, Schwebfliegen und sonstige Insekten, sind erforderlich. Unbestimmte Exemplare müssen nach einer dokumentierten Regel als ungeklärte Review-Fälle oder separate Out-of-Distribution-Testbeispiele behandelt werden.
4. **Leckagefreie Aufteilung:** gesamte Beobachtung, Video/Track, Fotograf, Standort/Kamera und zusammengehörige Quellbilder in genau einem Split halten; Duplikate und nahe Duplikate zusätzlich visuell prüfen. Der finale Test muss aus zurückgehaltenen Standorten/Kameras stammen und bis zur einmaligen Endbewertung unangetastet bleiben.
5. **Nachweisbarkeit:** getrennte SHA-256 für Bild und zugehörige Labeldatei, annotierende/reviewende Rollen, Taxonomieversion, Splitgruppe, Export-/Augmentationsprotokoll und Lösch-/Widerrufsverfahren dokumentieren. Private Originale, EXIF-GPS, genaue Bienenstandorte und personenbezogene Reviewdaten lokal und zugriffsgeschützt halten.

## Reproduzierbarer Weg nach Freigabe

Für den geänderten Klassifikationsauftrag enthält dieses Repository nun `training/multilabel_dataset.py` (fail-closed JSONL-Validierung und gruppierter Split) und `training/train_multilabel.py` (CPU-Training von Grund auf und ONNX-Export). Ausführbarer Exportvertrag, Windows-Kommandos, Dependency-Pins, Ausgabe/I-O-Form, Validierung und Integrationsgrenzen sind in [MULTILABEL-CLASSIFICATION-TRAINING.md](MULTILABEL-CLASSIFICATION-TRAINING.md) beschrieben. Die Tools laden keine Bilder oder Gewichte herunter.

Der zuvor untersuchte Monitor-Pfad und die Kandidaten-Skripte sind **kein Ersatz** für diesen Vertrag und ändern den Monitor nicht. Die remote geprüfte Monitor-Revision nutzt Boxen/Detektion; ein ONNX-Klassifikator mit sieben Logits ist nicht mit `camera/onnx_detector.py` kompatibel. Ein im Monitor abgestimmter Bildklassifikationsadapter bleibt vor realer Kamera-Inferenz erforderlich. Bis ein freigegebener echter Bestand bereitsteht, wird nicht trainiert.

## Abhängigkeiten, Datenfluss und Rückbau

Für diese Prüfung wurden keine Trainings-Software-Abhängigkeiten installiert und keine Bilder/Modelle geladen. Der bestehende BeeKeeper-Inferenzpfad pinnt `onnxruntime==1.32.0` (SPDX `MIT`) und `opencv-python-headless==4.14.0.94` (SPDX `Apache-2.0`); dies ist kein Trainingsstack. Optionale direkte Trainingspins und ihre Lizenz-IDs sind in `training/requirements-training.txt` dokumentiert; transitive Lizenzen und die Datenrechte müssen vor Installation bzw. Einsatz weiterhin geprüft werden. Diese Dokumentation ist keine Rechtsberatung.

Der derzeit sichere Datenfluss ist Metadatenrecherche → manuelle Prüfung → lokales, zugriffsgeschütztes Bild/Label-Staging → geprüfter Export; keine Medien- oder privaten Standortdaten werden standardmäßig an BeeKeeper oder Dritte übertragen. Öffentliche Bildquellen können Personen, Häuser oder Standortspuren enthalten; eine Trainingsfreigabe ersetzt keine Datenschutzprüfung. Da hier nur Dokumentation ergänzt wird, besteht kein Datenbank-/Service-Rollback: Änderung zurücknehmen und es werden weder Modelle noch lokale Daten entfernt.

## Verbleibende Blocker

- Kein vollständiger, freigegebener Siebenklassen-Bildbestand und noch keine menschlich geprüften Klassifikationslabels.
- Quell-/Einzelbildrechte und Attributionen müssen je Datei geprüft werden; Kandidatenzahlen ersetzen keine Rechtekette.
- Keine eindeutig definierte Freigaberegel für `unknown`/unbestimmte Tiere und keine Bestätigung der vorläufigen Zuordnung aller relevanten Wespen zu `other_vespidae`.
- Kein Trainingslauf, kein aus BeeKeeper- oder Monitor-Daten trainiertes Gewicht, keine unabhängigen Feldmetriken und keine Modellfreigabe.
- Annotation, fachliche Zweitprüfung, repräsentative Standortaufnahmen, unabhängiger Holdout und ein Bildklassifikationsadapter im Monitor erfordern Betreiber-/Facharbeit.

## Quellen

- [Beekeeper-Monitor: Trainings-README](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/d8972ea1d1bf3eb426866840b2fdefdbacadf764/training/README.md)
- [Beekeeper-Monitor: Siebenklassen-Architekturreview](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/d8972ea1d1bf3eb426866840b2fdefdbacadf764/training/DETECTION-ARCHITECTURE-REVIEW-2026-11-21.md)
- [Beekeeper-Monitor: iNaturalist-Kandidatenbericht](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/d8972ea1d1bf3eb426866840b2fdefdbacadf764/docs/INATURALIST-1000-CANDIDATES-RESULTS-2026-11-21.md)
- [Beekeeper-Monitor: iNaturalist-Rechte- und Metadatenreview](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/d8972ea1d1bf3eb426866840b2fdefdbacadf764/training/INATURALIST-REVIEW.md)
- [Beekeeper-Monitor: CC0-Rechercheworkflow der Artefakt-Ausführung](https://github.com/simonthomas-ai/Beekeeper-Monitor/blob/000e84444310d35a4a988d738ffdcbf382d4ab8b/.github/workflows/ki-cc0-quellen.yml)
- [Beekeeper-Monitor: erfolgreicher CC0-Artefaktlauf](https://github.com/simonthomas-ai/Beekeeper-Monitor/actions/runs/45010096375)
- [iNaturalist Observations API](https://api.inaturalist.org/v1/observations)
- [iNaturalist-Abfrage *V. velutina*](https://api.inaturalist.org/v1/observations?taxon_id=119019&quality_grade=research&license=cc0,cc-by&per_page=0)
- [iNaturalist-Abfrage *V. crabro*](https://api.inaturalist.org/v1/observations?taxon_id=54327&quality_grade=research&license=cc0,cc-by&per_page=0)
- [iNaturalist-Abfrage *Vespula vulgaris*](https://api.inaturalist.org/v1/observations?taxon_id=127777&quality_grade=research&license=cc0,cc-by&per_page=0)
- [GBIF Occurrence API](https://techdocs.gbif.org/en/openapi/v1/occurrence)
- [GBIF-Occurrence-Abfrage CC0](https://api.gbif.org/v1/occurrence/search?taxon_key=1311477&media_type=StillImage&license=CC0_1_0&limit=0)
- [GBIF-Occurrence-Abfrage CC BY](https://api.gbif.org/v1/occurrence/search?taxon_key=1311477&media_type=StillImage&license=CC_BY_4_0&limit=0)
- [GBIF Multimedia-Rechte und Lizenzfelder](https://techdocs.gbif.org/en/data-publishing/multimedia-publishing)
- [Roboflow ISR Datensatz v1](https://universe.roboflow.com/institute-of-systems-and-robotics-isr/vespa-velutina-hihv9-upzpe/dataset/1)
