# Model Portfolio

Stand: 2026-09-04. Die Tabelle ist eine Auswahl- und Evaluationsliste, keine Installationsanweisung. Jedes Modell bleibt lokal, opt-in, versionsfixiert und liefert nur Review-Kandidaten oder abgeleitete Textdaten.

## Startreihenfolge

| Aufgabe | Kandidat | Entscheidung | Integration |
| --- | --- | --- | --- |
| Kommentar-Ausreisser | PyOD ECOD | Bereits integriert; transparente Feature-Baseline bleibt Vergleich | `SignalForge` |
| Screenshot-OCR | PaddleOCR 3 mit PP-OCRv6 | Bereits integriert; fuer kurze Social-Screenshot-Texte zuerst validieren | `GlyphWatch` |
| Dokument-/Layout-OCR | `PaddlePaddle/PaddleOCR-VL-1.6` | Erst evaluieren, falls Tabellen, komplexe Layouts oder mehrseitige Quellen relevant werden | eigener opt-in Adapter |
| Themen-/Risiko-Triage | `MoritzLaurer/bge-m3-zeroshot-v2.0-c` | Kandidat fuer konfigurierbare, mehrsprachige Labels ohne eigenes Training | lokaler Review-Adapter |
| Semantische Suche | `BAAI/bge-m3` | Empfohlener erster Retrieval-Encoder fuer deutsche und mehrsprachige Fallakten | Embeddings + SQLite/Vektorindex |
| Quellen-Reranking | `BAAI/bge-reranker-v2-m3` | Nach `bge-m3`; nur die Top-Treffer erneut sortieren | Retrieval-Stage |
| Audio aus lokalem Video | `openai/whisper-large-v3-turbo` | Optional fuer explizit importierte lokale Medien, nicht fuer Abrufe | Media-Transkript-Adapter |
| Quellengebundene Zusammenfassung | `Qwen/Qwen3-8B` | Spaetere, optionale Assistenz; belegte Fakten plus lesbare Modellbewertung mit Beleg-IDs | lokaler, tool-beschraenkter Dienst |

## Begruendung und Grenzen

- `BAAI/bge-m3` unterstuetzt dichte, sparse und Multi-Vector-Retrieval-Varianten, mehr als 100 Sprachen und lange Eingaben. Die Modellkarte empfiehlt Hybrid-Retrieval plus Reranking. Deshalb ist es der sinnvollste erste Baustein fuer Fall- und Quellenrecherche, nicht fuer Schuld- oder Identitaetsurteile. [Modellkarte](https://huggingface.co/BAAI/bge-m3)
- `MoritzLaurer/bge-m3-zeroshot-v2.0-c` formuliert Triage als Entailment-Aufgabe und kann ohne Trainingsdaten starten. Labels muessen sachlich und eng sein, etwa `enthaelt direkten Link`, `enthaelt Drohung`, `enthaelt abwertende Sprache`; keine Labels wie `ist organisiert` oder `ist Person X`. [Modellkarte](https://huggingface.co/MoritzLaurer/bge-m3-zeroshot-v2.0-c)
- `PaddleOCR-VL-1.6` ist eine neuere, multimodale Dokument-Parsing-Option. Fuer das bestehende Screenshot-Szenario bleibt PP-OCRv6 die schlankere Startlinie; OCR-VL wird nur mit fixem Testsatz und Kostenmessung verglichen. [Modellkarte](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6)
- `openai/whisper-large-v3-turbo` ist die beschleunigte, auf vier Decoder-Layer reduzierte Variante von Whisper large-v3. Es eignet sich fuer optionale lokale Transkription, nicht fuer eine Behauptung ueber den Inhalt eines Videos ohne kontrollierbare Zeitmarken. [Modellkarte](https://huggingface.co/openai/whisper-large-v3-turbo)
- `Qwen/Qwen3-8B` ist ein Apache-2.0-Modell mit 8.2B Parametern, mehrsprachiger Unterstuetzung und dokumentiertem lokalem Serving. Sein Entwurf hat zwei sichtbare Ebenen: belegte Fakten mit Evidenz-IDs und direkt darunter eine lesbare, probabilistische Modellbewertung mit Konfidenz, Basisbelegen und Unsicherheiten. Der feste Ausgabe-Vertrag steht in `config/qwen_response_contract.json`. [Modellkarte](https://huggingface.co/Qwen/Qwen3-8B)

## Implementationsmuster

### Retrieval-Funnel

1. Text und Metadaten lokal normalisieren.
2. `bge-m3`-Embeddings pro Beobachtung und Quelle erzeugen, Modellrevision und Input-Hash speichern.
3. Dense Treffer mit lexikalischer Suche kombinieren.
4. Nur die besten Kandidaten mit `bge-reranker-v2-m3` sortieren.
5. Treffer mit Original-URL, Zeit und Evidenz-ID an die UI liefern.

Die Pipeline gibt Quellen zurueck, keine frei formulierte Antwort. Erst ein menschlicher Review oder eine separate, quellengebundene Entwurfsfunktion darf daraus Text erzeugen.

### Triage-Funnel

1. Regelbasierte Marker und ECOD zuerst ausfuehren.
2. Zero-Shot nur auf regel- oder review-relevante Inhalte anwenden.
3. Score, Label, Prompt-Template und Modellrevision speichern.
4. Unterhalb einer vorab festgelegten Schwelle nichts markieren; im Unsicherheitsbereich `review_required` setzen.
5. Akzeptierte oder verworfene Review-Entscheidungen als Goldsatz sammeln.

### LLM-Funnel

1. Ein Retrieval-Job liefert eine geschlossene Liste von Evidenz-ID und Quellenauszuegen.
2. Das LLM erhaelt nur diese Auszuege und den Vertrag `config/qwen_response_contract.json`.
3. Ein Validator lehnt Fakten ohne Evidenz-ID oder mit unbekannten IDs ab; die Modellbewertung bleibt als eigene, lesbare Ebene erhalten.
4. Der Entwurf zeigt Fakten, Qwen-Modellbewertung, Unsicherheiten und Review-Fragen in dieser Reihenfolge. Weitere Ausfuehrungswege muessen als getrennte, protokollierte Adapter konfiguriert sein.

## Was selbst trainiert werden kann

| Ziel | Sinnvoller Ansatz | Startbedingung |
| --- | --- | --- |
| Enge, lokale Taxonomie fuer Review | SetFit auf einem mehrsprachigen Sentence-Transformer | Genuegend doppelt gepruefte Labels und separater Testsplit |
| Retrieval fuer eigene Quellenarten | Kontrastives Fine-Tuning von `bge-m3` | Query-Dokument-Paare mit Relevanzurteil |
| Entwurfsformat oder Extraktionsschema | LoRA/PEFT auf einem lokalen Instruct-Modell | Grosse, qualitaetsgesicherte Menge mit Quellen-IDs; keine Rohbelege unkontrolliert verwenden |
| OCR-Anpassung | Erst Fehleranalyse und Sprach-/Bildtest; keine spontane Nachtrainierung | Wiederkehrender, messbarer OCR-Fehler auf rechtmaessigen Daten |

SetFit ist fuer wenige gelabelte Beispiele ein geeigneter erster Klassifikationsweg und kann mehrsprachige Sentence-Transformer verwenden. PEFT/LoRA reduziert beim spaeteren Fine-Tuning die Anzahl trainierbarer Parameter und bewahrt das Basismodell. [SetFit-Dokumentation](https://huggingface.co/docs/setfit/index), [PEFT Quicktour](https://huggingface.co/docs/peft/main/quicktour)

## Evaluationsprotokoll

- Vor jeder Installation: Modellrevision, Lizenz, Groesse, Hardware- und Offline-Anforderungen dokumentieren.
- Vor jedem Training: Datenherkunft, Zweck, Labeldefinition, Reviewer, Aufteilung und Ausschlusskriterien versionieren.
- Fuer Klassifikation: Precision, Recall, F1 und Confusion-Matrix je Label; dabei `unknown` als eigene korrekte Ausgabe zulassen.
- Fuer Retrieval: Recall@k, MRR und Anteil der Treffer mit vollstaendigem Quellenpfad.
- Fuer OCR: Zeichen- und Wortfehlerrate sowie Sichtpruefung der Bounding-Box-/Zeilenreferenz.
- Jede Auswertung gegen die bestehende regelbasierte Baseline vergleichen. Eine hoehere Trefferzahl ohne akzeptable Precision ist kein Fortschritt.
