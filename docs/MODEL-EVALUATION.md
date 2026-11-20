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

## Aussagegrenzen
- AP wird für jede Klasse mit einer nach Konfidenz sortierten, schrittweisen Zuordnung und 101-Punkte-Interpolation bei **einem** IoU-Schwellwert berechnet. Das ist **nicht** die COCO-mAP über mehrere IoU-Schwellwerte.
- Das Werkzeug untersucht keine Bilder, überprüft keine Annotationen, erkennt keine Überschneidung zwischen Trainings- und Testdaten und bestätigt keine Lizenzrechte.
- Kennzahlen sind nur so repräsentativ wie die unabhängigen Testdaten und deren Annotationen.
- Es ist kein Modell enthalten. Die Existenz dieses Werkzeugs belegt **weder Modellleistung noch Einsatzfreigabe**.
- Feldtests und fachkundige menschliche Bestätigung bleiben erforderlich.

## Prüfung der Modellherkunft
Bisher ist **kein externes Modell freigegeben**. Kandidaten und die Gründe für Zurückstellung oder Ablehnung stehen im [Register für Modell- und Datenherkunft](MODEL-PROVENANCE-REGISTER-2026-11-20.md).
