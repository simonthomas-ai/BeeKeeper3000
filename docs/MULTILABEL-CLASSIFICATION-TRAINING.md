# Lokaler Multilabel-Datensatz- und Trainingspfad

**Status: vorbereitet, nicht trainiert oder feldvalidiert.** Der Checkout enthält weiterhin keine Trainingsbilder, Annotationen oder freigegebenen Modellgewichte. Die Fixtures der Validator-Tests sind absichtlich keine Bilder und kein Trainings- oder Evaluationsbestand.

Die aktuelle Arbeitsentscheidung ist **Bildklassifikation mit mehreren Labels pro Bild** (keine Bounding-Boxes). Die sieben Slugs sind `vespa_velutina`, `vespa_crabro`, `other_vespidae`, `apis_mellifera`, `bombus_spp`, `syrphidae` und `other_insect`. `labels: []` ist ein zulässiges, fachlich geprüftes Negativbild: Es darf keine der sieben Zielklassen enthalten. Unbestimmte Fälle dürfen nicht automatisch in `other_insect` umetikettiert werden.

## Exportvertrag

Der lokale Datensatz kann als Verzeichnis oder ZIP mit den Root-Einträgen `images/` und `annotations.jsonl` bereitgestellt werden. Das ZIP darf keine Pfad-Traversal-Einträge, verschlüsselten/symbolischen Inhalte, Duplikate oder nicht gelistete Bilddateien enthalten. Die Prüfgrenze beträgt 100.000 Einträge, 50 GB Gesamtgröße und 80 MB je Bilddatei. Die Inhalte werden nur in einem temporären geschützten Verzeichnis entpackt und nicht veröffentlicht. BeeKeeper akzeptiert aktuell vor der Inferenz ausschließlich JPEG/JPG, PNG und WEBP; GIF, AVIF, HEIC, BMP und TIFF werden nicht direkt angenommen. Der Monitor/iPhone-Export muss solche Formate vorher reproduzierbar nach JPEG/PNG/WEBP konvertieren und die Konvertierung/Dateirechtsfreigabe dokumentieren.

```json
{"image":"images/session-001/frame-0001.jpg","labels":["vespa_velutina","apis_mellifera"],"captured_at":"2026-11-20T12:00:00Z","capture_session_id":"session-001","labeler_id":"reviewer-07","review_status":"approved","rights":{"source":"Eigene Feldaufnahme","basis":"Eigene Erlaubnis","status":"training_approved"}}
```

`labeler_id` ist optional und pseudonym. `rights.source` und `rights.basis` sind begrenzte nicht-leere Freitextwerte; `rights.status` muss `training_approved` sein. `review_status` muss `approved` sein. `Eigene Feldaufnahme` ist als generische Quelle erlaubt, bildet aber keine gemeinsame externe-Quellgruppe; der Leakschutz nutzt dafür `capture_session_id`. Für konkrete externe HTTPS-Quellen werden unterschiedliche Quellen getrennt gruppiert. Optionale `publication_allowed`, `evidence_url`, Attribution oder `permission_ref`-Nachweise werden streng geprüft, wenn sie vorhanden sind. Keine Lizenzfreigabe wird aus freien Texten automatisch abgeleitet.

## Prüfung und lokales Training

Die Werkzeuge verwenden nur die übergebenen lokalen Dateien; sie laden weder Daten noch vortrainierte Gewichte und senden nichts an einen Dienst. Vorher Dataset-Rechte, Datenschutz und Weitergabeberechtigung manuell prüfen. Dann im Repository-Root:

```powershell
python -m training.multilabel_dataset --dataset "D:\field-data\approved-dataset" --seed 42 --output "D:\field-data\split-plan.json"
python -m training.train_multilabel --dataset "D:\field-data\approved-dataset" --output-dir "D:\field-data\model-run-001" --epochs 20 --batch-size 16 --learning-rate 0.001 --seed 42
python -m unittest training.test_multilabel_dataset -v
```

Die erste Ausführung verweigert fehlende/zusätzliche, symbolische oder byte-identische Bilddateien, ungültige oder duplizierte Klassen, Pfad-Traversal, naive Zeitstempel, nicht freigegebene Review-/Rechtefelder und unzureichend unabhängige Gruppen. Train/Val/Test werden deterministisch nach zusammenhängenden `capture_session_id`- und konkreten `rights.source`-Gruppen getrennt; gemeinsame Sessions oder Quellen leaken somit nicht zwischen Splits. Verwende pro Bild eine spezifische Quell-URL, sonst kann eine pauschale URL den Bestand zu einer einzigen Gruppe verbinden. Alle sieben Labels müssen im Trainingssplit positive Beispiele haben. Ein kleines Dataset kann wegen der strikten Gruppenbindung keine drei Splits bilden; Einträge werden nicht zur Split-Erzwingung vermischt. Die normale CLI-Ausgabe enthält nur Zähler/Hashes, keine Dateinamen. Das optionale `--output` schreibt konkrete relative Bildpfade in den Splitplan: speichere ihn nur lokal, geschützt und außerhalb synchronisierter/öffentlicher Ordner.

Der Trainingsbefehl hat zwei explizite Aufgaben:

- `--task seven_multilabel` (Standard) exportiert `[1,7]`-Logits und verlangt positive Beispiele für alle sieben Slugs im Trainingssplit.
- `--task vespa_velutina_binary` exportiert `[1,1]`-Logits mit genau der Klasse `vespa_velutina`. Positiv ist ein Bild, dessen `labels`-Liste diesen Slug enthält. Negativ ist ein fachlich geprüftes Bild, dessen Liste ihn nicht enthält; andere Zielklassen dürfen zusammen mit dem Negativlabel vorkommen.

Der Siebenklassen-Datensatzvertrag und die JSONL-Felder bleiben unverändert. Das Einklassenmodell ist keine verkürzte oder umkodierte Version des Siebenklassenmodells: Es muss als eigener Gewichtsbestand, eigener Hash, eigene ONNX-Klasse und eigener unabhängiger Holdout geführt werden.

Optionale, direkt gepinnte Trainingsabhängigkeiten stehen in `training/requirements-training.txt`: `torch==2.9.1` (BSD-3-Clause; [Upstream-Lizenz](https://github.com/pytorch/pytorch/blob/v2.9.1/LICENSE)), `Pillow==12.0.0` (MIT-CMU; [Upstream-Lizenz](https://github.com/python-pillow/Pillow/blob/12.0.0/LICENSE)) und `onnx==1.20.1` (Apache-2.0; [Upstream-Lizenz](https://github.com/onnx/onnx/blob/v1.20.1/LICENSE)). Das sind keine Kamera-Abhängigkeiten; der Bestand wurde nicht installiert. PyTorch enthält je nach Installationsweg CPU-/GPU-Builds; für den vorgesehenen CPU-Pfad nur eine passende offizielle CPU-Distribution verwenden (`torch.__version__` darf den lokalen Build-Suffix `+cpu` tragen). Transitive Versionen und ihre Lizenzen vor einem produktiven Einsatz zusätzlich inventarisieren. Beispielsweise zuerst Pillow/ONNX gemäß Pin-Datei und danach PyTorch mit dem offiziellen CPU-Index installieren; Ausführung erst nach vollständiger Lizenz- und SBOM-Prüfung. Es wird ein zufällig initialisiertes kleines CNN von Grund auf trainiert, kein externes oder vortrainiertes Modell.

Das Training erzeugt `classifier.pt`, `classifier.onnx` und `training-evidence.json` im neu anzulegenden Ausgabeordner. Der ONNX-Vertrag ist RGB/NCHW `[1,3,224,224]`, Wertebereich `0..1`, Ausgabe `[1,7]` als Logits (vor Interpretation Sigmoid anwenden). ONNX wird nach Export auf Graph-I/O und Struktur geprüft. Der lokale Nachweis enthält SHA-256 für Annotationen, Splitplan, Checkpoint und ONNX sowie Parameter und reine Val-Split-Metriken; Testdaten werden weder trainiert noch zur Schwellenwertwahl verwendet. Dateipfade des privaten Datasets werden nicht in den Nachweis geschrieben.

## Feldtest-, Schnittstellen- und Sicherheitsgrenzen

Der aktuelle `camera/onnx_detector.py`-Adapter ist auf **Objektdetektion mit Boxen** ausgelegt und konsumiert diesen neuen Klassifikatorvertrag nicht. Der Klassifikator ist deshalb kein aktivierbares Kameramodell, erzeugt keine Produktivalarme und darf nicht als Modell für den bestehenden Detector konfiguriert werden. Der Monitor-Checkout wurde nicht geändert. Die Exportstruktur entspricht dem hier vereinbarten Dataset-JSONL-Vertrag; eine End-to-End-Modellintegration benötigt noch einen abgestimmten Klassifikationsadapter im Monitor und in BeeKeeper3000.

Jeder spätere Gewichtsbestand bleibt `experimental_unvalidated`, bis ein unabhängiger, standortgetrennter Holdout, fachliche Annotation, Unsicherheits-/Fehlalarmbewertung und ein freigegebener Inferenzadapter belegt sind. Die internen Val-Metriken sind keine Feld- oder Artbestimmungsgenauigkeit. Bis dahin nur lokale technische Tests; keine automatischen Benachrichtigungen oder Eradikationsentscheidungen. Eingabebilder bleiben lokal; keine Rohbilder, GPS-Daten oder Review-Identitäten übertragen.

Rollback: Nur den neu erzeugten Modell-Ausgabeordner entfernen und keine Modellkonfiguration aktivieren. Der Quellbestand und bestehende Feldtest-/No-AI-Pfade werden durch diese Werkzeuge nicht verändert.

## Feldstart zu Trainingsdaten

1. Fotos nur aus einer freigegebenen Aufnahme-/Stationsquelle erfassen. Aufnahmezeit, pseudonyme Session-ID und Kamerastandort lokal festhalten; genaue private Koordinaten und personenbezogene Angaben nicht in das Exportmanifest schreiben.
2. Die Aufnahmen in das vereinbarte Monitor-Exportformat übernehmen: ZIP oder Verzeichnis mit `images/` und `annotations.jsonl`, ein JSON-Record je Bild, Liste aus den sieben Slugs oder `[]` für ein geprüftes Negativbild.
3. Jede Aufnahme fachkundig reviewen: sichtbare Zielklassen bestätigen, negative Bilder aktiv prüfen, keine ungeklärte Art in `other_insect` einsortieren. Rechtequelle, Basis, Status, Nachweis und Freigabe je Bild prüfen.
4. Den Export lokal validieren und erst danach in ein geschütztes Trainingsverzeichnis kopieren. Der Validator prüft Pfade, ZIP-Inhalte, Manifest-/Bild-Inventar, Duplikate, Labels, Reviewstatus und Rechte. Ohne unabhängige Trainer-/Validation-/Test-Gruppen nach Aufnahme-Session und Quelle wird kein Lauf erzeugt.
5. Ein Training wird erst freigegeben, wenn alle sieben Klassen fachlich, räumlich und kameraseitig ausreichend repräsentiert sind, der Holdout unabhängig und gruppengeleakt ist und eine Lizenz-/Datenschutzfreigabe vorliegt. Es gibt keine allgemeingültige Bildzahl, ab der Training „sinnvoll“ ist; jede Menge ist vor Ort fachlich und datenstatistisch zu begründen. Die Summe und Verteilung dürfen erst nach einem realen Holdout ausgewertet werden.

Die auf dem Monitor-`main` nachweisbare Spezifikation enthält noch das alte Box-/YOLO-Profil und keinen dort vorhandenen Pfad `docs/FIELD-DATASET-CAPTURE.md`. Die hier implementierte JSONL-/Multilabel-Brücke ist deshalb eine lokale Zielvorgabe, kein Nachweis eines bereits abgestimmten oder implementierten Monitor-Importadapters. Der Monitor wurde nicht geändert.

## Windows-Import des Monitor-Zips

Aus dem BeeKeeper3000-Repository-Root:

```powershell
python -m training.multilabel_dataset --dataset "$env:USERPROFILE\Downloads\field-dataset.zip" --seed 42 --output "$env:LOCALAPPDATA\BeeKeeper3000\field-split-plan.json"
```

Der erfolgreiche Exitcode `0` beweist nur einen gültigen, freigegebenen Dateivertrag und einen deterministischen Split. Er belegt keine Modellgenauigkeit. Bei Exitcode `2` ist der Export abzulehnen und die Fehlzeile zu korrigieren. Für einen Trainingsversuch erst nach Prüfung der Ausgabegründe:

```powershell
python -m training.train_multilabel --dataset "$env:USERPROFILE\Downloads\field-dataset.zip" --output-dir "$env:LOCALAPPDATA\BeeKeeper3000\model-run-01" --epochs 20 --batch-size 16 --learning-rate 0.001 --seed 42
```

Dieser Lauf startet nur mit drei unabhängigen, leakfreien Gruppen und positiven Beispielen für alle sieben Klassen. Die asiatische Hornisse `vespa_velutina` ist als eine der sieben unterstützten Slugs und als menschlich prüfbares Klassifikationslabel vollständig benannt. Das bedeutet weder eine vorhandene Gewichtedatei noch eine validierte Detektion oder Alarmfreigabe. Bis echtes unabhängiges Feld-Holdout und freigegebene Daten vorliegen, bleibt jeder spätere Gewichtsbestand `experimental_unvalidated`.

Für die ausdrücklich vorgesehene erste binäre Stufe denselben Export mit `--task vespa_velutina_binary` verwenden:

```powershell
python -m training.train_multilabel --dataset "$env:USERPROFILE\Downloads\field-dataset.zip" --output-dir "$env:LOCALAPPDATA\BeeKeeper3000\vespa-velutina-run-01" --task vespa_velutina_binary --epochs 20 --seed 42
```

Die kurze Klassen-Variante ist ebenfalls verfügbar:

```powershell
python -m training.train_multilabel --dataset "$env:USERPROFILE\Downloads\field-dataset.zip" --output-dir "$env:LOCALAPPDATA\BeeKeeper3000\vespa-velutina-run-01" --classes vespa_velutina --epochs 20 --seed 42
```

Der Binary-Lauf erfordert im Trainingssplit mindestens ein positives und ein negatives Beispiel, aber keine positiven Beispiele der sechs weiteren Slugs. Negative Bilder können dennoch `apis_mellifera`, `bombus_spp` oder andere freigegebene Nicht-Hornissen-Labels tragen. Das ONNX-Ausgabeformat wird als `[1,1]`-Logit und genau eine Klasse `vespa_velutina` dokumentiert. Es werden weiterhin keine Gewichte trainiert oder ausgeliefert, wenn der reale freigegebene Datenbestand fehlt; keine Produktivalarme oder Qualitätskennzahlen werden aus Fixtures abgeleitet.
