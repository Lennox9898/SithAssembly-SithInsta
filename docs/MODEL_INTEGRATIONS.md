# Lokale Modellintegration

`SithAssembly//SignalForge` und `SithAssembly//GlyphWatch` sind optionale Adapter. Das Grundsystem laeuft ohne ML-Abhaengigkeiten; es installiert nichts und laedt keine Gewichte im Hintergrund.

## Auswahl

- Kommentar-Ausreisser: PyOD ECOD ist die primäre Option. ECOD ist parameterarm und fuer tabellarische, unsupervised Ausreisser-Scores geeignet. Das System verwendet nur transparente lokale Merkmale wie Textlaenge, Grossbuchstaben-, Satzzeichen-, Link-, Erwaehnungs- und Hashtag-Anteil sowie Wiederholungen. Unter 20 Kommentaren bleibt es bei einem robusten lokalen Vergleich; Ausgaben sind immer `review_required`.
- Screenshot-OCR: PaddleOCR 3 mit PP-OCRv6 ist die primäre Option fuer explizit hochgeladene lokale Bildbelege. PP-OCRv6 ist die aktuelle offizielle Generation und hat je nach Tier breitere Sprachabdeckung sowie verbesserte Erkennung gegenueber PP-OCRv5. Der Adapter nutzt die dokumentierte `PaddleOCR(...).predict(...)`-Schnittstelle und aktiviert keine Dokument-Orientierungs- oder Entzerrungsmodelle. Dadurch bleibt der erste Einsatz auf die benoetigte OCR-Pipeline begrenzt.
- Alternative fuer dokumentlastige Quellen: docTR. Es ist sinnvoll, wenn strukturierte OCR-Ausgaben aus PDFs oder mehrseitigen Dokumenten im Vordergrund stehen. Es ist nicht als zweiter paralleler Runtime-Adapter eingebunden, um doppelte Gewichts-Downloads und uneinheitliche Ergebnisse zu vermeiden.

## Installation

Fuer SignalForge nach expliziter Freigabe:

```powershell
python -m pip install numpy pyod
```

Fuer GlyphWatch zuerst eine zu Windows/CPU/GPU passende `paddlepaddle`-Runtime nach der offiziellen PaddleOCR-Anleitung auswaehlen. Danach:

```powershell
python -m pip install paddleocr
```

PaddleOCR kann beim ersten bewusst bestaetigten OCR-Lauf PP-OCRv6-Gewichte laden. Die Oberflaeche fragt davor explizit nach. Es gibt kein automatisches Modell- oder Paket-Setup.

## Grenzen

- Anomalie-Scores sind keine Aussagen zu Absicht, Ideologie, Identitaet oder Koordination.
- OCR-Text wird als abgeleitetes Ergebnis mit Evidenz-ID, Modellprofil und Zeitpunkt gespeichert; der unveraenderte lokale Bildbeleg bleibt referenzierbar.
- Es werden nur manuell hochgeladene Bilddateien verarbeitet. Keine URLs werden abgerufen, keine Plattformen gecrawlt.

## Primaerquellen

- PaddleOCR 3 Installation: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/installation.en.md
- PaddleOCR PP-OCRv6: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md
- PP-OCRv6 auf Hugging Face: https://huggingface.co/models?other=PaddlePaddle
- PaddleOCR General OCR Pipeline: https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html
- PyOD und ECOD: https://github.com/yzhao062/pyod und https://github.com/yzhao062/pyod/blob/master/pyod/models/ecod.py
- docTR Quickstart: https://mindee.github.io/doctr/latest/getting_started/quickstart.html
