# Modellbewertung mit unabhängigen, zurückgehaltenen Testdaten

Das Repository enthält `camera/evaluate_detections.py`. Damit lassen sich für jede Klasse richtig-positive (TP), falsch-positive (FP) und falsch-negative (FN) Erkennungen sowie Präzision, Trefferquote (Recall), F1-Wert und die mit 101 Punkten interpolierte durchschnittliche Präzision (AP) bei einem gewählten IoU-Schwellwert berechnen.

## Format der Annotationen
Pro Zeile steht genau ein UTF-8-JSON-Objekt (JSONL). Bilder, genaue Standorte und ursprüngliche Mediendateien privat halten. Beispiel mit **künstlichen Demonstrationswerten, nicht mit echten Messergebnissen**:

```json
{"image_id":"private-image-0001","image_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","ground_truth":[{"class_id":0,"bbox_xyxy":[10,10,100,100]}],"predictions":[{"class_id":0,"confidence":0.93,"bbox_xyxy":[12,12,98,98]}]}
```

Koordinaten sind Pixelwerte `[x1,y1,x2,y2]` mit Ursprung links oben und positiver Rechtecksfläche. Die tatsächlichen Referenzmarkierungen (`ground_truth`) müssen unabhängig erstellt worden sein; die Vorhersagen (`predictions`) müssen von exakt der zu bewertenden Modellversion stammen. Ein Bild darf nicht doppelt vorkommen.

Der unabhängige Testsatz darf weder beim Training noch beim Nachtrainieren, bei der Schwellwertwahl oder bei der Modellauswahl verwendet worden sein. Zusätzlich müssen Annotationsverfahren, Übereinstimmung der Annotierenden, Klassenzuordnung, Kamerabedingungen, Auswahlverfahren der Bilder und Nutzungsrechte separat dokumentiert werden.

## Ausführung

```sh
python -m camera.evaluate_detections --annotations private-test.jsonl --output private-report.json --iou 0.5 --confidence 0.25
```

Der JSON-Bericht enthält die SHA-256-Prüfsumme der Annotationsdatei. Bericht, Herkunft der Annotationen, Modell-SHA-256 und Modellmanifest gemeinsam in einer zugriffsgeschützten Prüfdokumentation aufbewahren. Rohbilder, private Standortdaten oder sensible Annotationen niemals in ein öffentliches Repository einchecken.


## Ereignis- und Fehlalarmbewertung im Kamerabetrieb

camera/evaluate_events.py ergänzt die Bild-/Box-Metriken um eine ereignisbasierte Auswertung. Das ist für eine Station wichtig, weil mehrere aufeinanderfolgende Frames desselben Vorbeiflugs nicht als unabhängige Sichtungen zählen sollen und die Zahl falscher Alarme pro überwachte Kamerastunde für den Betrieb entscheidend ist.

Jede JSONL-Zeile beschreibt eine nicht überlappende Sitzung einer pseudonymisierten Kamera:
- session_id, camera_id, model_sha256, start_time_utc und duration_seconds
- ground_truth_review_status: "verified" und ein pseudonymisierter reviewer_id
- ground_truth_events mit Event-ID, Klassen-ID sowie Start-/Endsekunde relativ zur Sitzung
- predicted_events mit denselben Zeit-/Klassenfeldern und einer Konfidenz

Die Referenzereignisse müssen fachkundig menschlich geprüft sein. Das Modell-Hashfeld muss für alle Sitzungen identisch sein. Überlappende Sitzungen derselben Kamera werden abgewiesen, damit überwachte Kamerastunden nicht doppelt gezählt werden. Standortkoordinaten oder Bilddaten gehören nicht in diese Datei.

Ausführung:
    python -m camera.evaluate_events --sessions private-events.jsonl --output private-event-report.json --temporal-iou 0.5 --confidence 0.5

Der Bericht weist pro Klasse und insgesamt TP/FP/FN, Ereignis-Precision/Recall/F1 sowie false_alarms_per_camera_hour aus. Ereignisse werden nur innerhalb derselben Kamerasitzung, derselben Klasse und anhand zeitlicher Intervall-IoU zugeordnet. Bei fehlenden positiven oder vorhergesagten Ereignissen wird eine nicht definierte Kennzahl als null ausgegeben, nicht als scheinbare Null-Leistung.

Diese Software-Metriken sind nur so gut wie die geprüften Ereignisannotationen und die unabhängigen Aufnahmesitzungen. Sie ersetzen weder einen externen Standort-Holdout noch Konfidenzintervalle oder eine fachliche Feldabnahme.

## Aussagegrenzen
- AP wird für jede Klasse mit einer nach Konfidenz sortierten, schrittweisen Zuordnung und 101-Punkte-Interpolation bei **einem** IoU-Schwellwert berechnet. Das ist **nicht** die COCO-mAP über mehrere IoU-Schwellwerte.
- Das Werkzeug untersucht keine Bilder, überprüft keine Annotationen, erkennt keine Überschneidung zwischen Trainings- und Testdaten und bestätigt keine Lizenzrechte.
- Kennzahlen sind nur so repräsentativ wie die unabhängigen Testdaten und deren Annotationen.
- Es ist kein Modell enthalten. Die Existenz dieses Werkzeugs belegt **weder Modellleistung noch Einsatzfreigabe**.
- Feldtests und fachkundige menschliche Bestätigung bleiben erforderlich.

## Prüfung der Modellherkunft
Bisher ist **kein externes Modell freigegeben**. Kandidaten und die Gründe für Zurückstellung oder Ablehnung stehen im [Register für Modell- und Datenherkunft](MODEL-PROVENANCE-REGISTER-2026-11-20.md).
