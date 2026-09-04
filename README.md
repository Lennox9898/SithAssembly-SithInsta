# Signal Desk

`Signal Desk` ist eine lokale Fallarbeitsumgebung fuer Beobachtung, Einordnung und quellengebundene Gegenrede-Entwuerfe zu oeffentlichen Social-Media-Inhalten.

 das Projekt:

- Fallverwaltung mit Status, Beschreibung und Kennzahlen
- Erfassung oeffentlicher Beobachtungen mit Original-URL, Erfassungszeit und Belegregister
- Collector fuer manuelle Eintraege oder erlaubte Exporte; 
- Erkennung dokumentierter Erwaehnungen, Hashtags, gemeinsamer Links, manueller Verknuepfungen und Accountwechsel-Hinweise
- Profile Resolver mit zeitlich nachvollziehbaren Profil-Snapshots
- Identity Resolver fuer analystisch hinterlegte Hypothesen inklusive Grundlage, Status und Konfidenz;
- Relationship Engine, Timeline Engine und Graph Viewer mit anklickbarer Beleg-URL und Zeitpunkt pro Kante
- Suche, Risiko-Filter, Markierungen, Notizen und Screenshot-Referenzen
- Entwuerfe freigegebener Faktencheck-Antworten
- Vollstaendiger Fall-Export als JSON und PDF mit Profilen, IDs, Hypothesen, Beziehungen, Chronologie und Belegen
- SQLite als lokale Standard-Datenbank

## Start

```powershell
.\RUN.bat
```

Danach ist das Interface unter `http://127.0.0.1:8080` erreichbar.

Fuer vollstaendige lokale Entwicklungsprotokolle: `.\DEV.bat`. Laufzeitstatus, lokale CommandDeck-Befehle und Log-Export stehen ueber `python SithAssembly.Runtime.py ...` bereit. Details: `docs/RUNTIME.md`.

## Tests

```powershell
python -m unittest discover -s tests
```

## Architektur

- `app.py`: Startpunkt
- `src/database.py`: SQLite-Schema und Verbindungslogik
- `src/repository.py`: Persistenz und Datenzugriff
- `src/collector.py`: Normalisierung sowie Mention-, Hashtag- und Link-Extraktion
- `src/profile_resolver.py`: Profil-Snapshot- und Aenderungsvergleich
- `src/identity_resolver.py`: validiert analystisch erfasste Identitaetshypothesen
- `src/relationship_engine.py`: konservative, evidenzgebundene Kanten
- `src/timeline_engine.py`: zeitliche Zusammenfuehrung
- `src/graph_viewer.py`: Gruppen, Grad und Zentralitaet
- `src/case_manager.py`: Anwendungs-Fassade fuer Fallakten und Suche
- `src/report_generator.py`: JSON- und lokaler PDF-Bericht
- `src/agent_controller.py`: sichtbare Verarbeitungsstufen
- `src/command_engine.py`: allowlisted Slash-Commands gegen die lokale Fallakte
- `src/case_importer.py`: Validierung manueller oder offiziell exportierter JSON-Daten
- `src/evidence_integrity.py`: lokale Content- und Kontext-Fingerprints
- `src/pattern_engine.py`: evidenzgebundene Musterkandidaten fuer Accounts, Hashtags, Domains und identische Texte
- `src/analyzer.py`: Risiko-Signale und einfache Klassifikation
- `src/drafter.py`: knappe, quellengebundene Antwortentwuerfe
- `src/server.py`: HTTP-API und statische Auslieferung
- `src/module_runtime.py`: explizite JSON-Registry und kontrolliertes Modul-Hooking beim Start
- `src/runtime_logging.py`: lokale JSONL-Runtime-Protokolle mit Redaction sensibler Felder
- `config/module_registry.json`: erlaubte, beim Start geladene `src.*`-Module
- `web/`: lokales Casework-Interface

## Import und Muster

Die Importflaeche akzeptiert eine JSON-Liste mit `handle` und `body` als Pflichtfeldern sowie optionalen Metadaten wie `platform`, `source_url`, `captured_at` und `sources`. Jeder Eintrag wird vor der Speicherung validiert und lokal fingerprinted.

Die Pattern Engine zeigt nur Kandidaten aus vorhandenen Fallbelegen an: wiederkehrende Accounts, gemeinsame Hashtags oder Domains, identische normalisierte Texte und zentrale Knoten. Jede Fundstelle verweist zur zugrunde liegenden Beobachtung. Ein Universeller Server wird später integriert.

## Optionale Analysemodelle

`SithAssembly//SignalForge` nutzt bei installierten optionalen Abhaengigkeiten PyOD ECOD fuer lokale Kommentar-Ausreisser. `SithAssembly//GlyphWatch` bindet PaddleOCR 3 / PP-OCRv6 fuer explizit hochgeladene lokale Bildbelege ein. Beides ist opt-in: Es gibt keine automatische Paketinstallation, keinen stillen Gewichtsdownload und kein Abrufen externer Inhalte. Auswahl, Installation und Grenzen stehen in `docs/MODEL_INTEGRATIONS.md`.

Ein spaeterer Qwen-Entwurf trennt sichtbare, beleggebundene Fakten von einer darunter dargestellten, lesbaren Modellbewertung mit Konfidenz und Unsicherheiten. Der Ausgabevertrag steht in `docs/QWEN_OUTPUT.md` und `config/qwen_response_contract.json`.

Lokale Agentenmodelle koennen ueber Ollama, llama.cpp oder vLLM angebunden werden. Die editierbare Provider-Registry, der lokale LLM-API-Vertrag und die Startreihenfolge stehen in `docs/LOCAL_MODELS.md`.

`python app.py --check-config` prueft alle lokalen Registries ohne Serverstart. `python app.py --print-capabilities` und `python SithAssembly.Runtime.py doctor` zeigen lesbar, ob CUDA sowie optionale Beschleuniger wie xFormers oder FlashAttention lokal erkannt werden. Diese Diagnose installiert und aktiviert nichts automatisch.

## Server-Vorbereitung

`deploy/` enthaelt eine standardmaessig inaktive Compose-Topologie fuer PostgreSQL, S3-kompatiblen Belegspeicher, NATS JetStream sowie getrennte API- und Worker-Rollen. `python SithAssembly.Deploy.py preflight` prueft die Vorbereitung ohne Docker zu starten. Die genaue Aktivierungsreihenfolge steht in `docs/DEPLOYMENT_PREP.md`.

Das externe Agentenstack-Dossier ist unveraendert unter `docs/Agentenstack_Evaluationsdossier_2026-09-04.pdf` abgelegt. Die daraus abgeleitete Ist-Analyse, Scorecard und begrenzte PoC-Reihenfolge stehen in `docs/architecture/` und fuehren keine Fremdkomponente automatisch ein.

## EvidenceVault

`SithAssembly//EvidenceVault` erzeugt fuer einen bestehenden Fall ein lokales `.sifvault.json`-Paket mit ZIP-Nutzlast, SHA-256-Manifest, AES-256-GCM-Verschluesselung, scrypt-Key-Derivation und Ed25519-Signatur. Die Passphrase wird nur fuer die Erstellung verwendet und nicht persistiert. Im Interface ist der Export opt-in; alternativ steht `python SIF_EvidenceVault.py create --case-id <id>` bereit. Details: `docs/MODULE_RUNTIME.md` und `docs/IMPORTANT_DISCLAIMER.md`.

## Command-Konsole

Die Command-Konsole im Interface fuehrt eine lokale, restriktive Teilmenge des abgelegten Katalogs direkt aus. Beispiele:

```text
/find posts --query "Begriff" --limit 20
/profile connections @konto
/graph path @konto_a @konto_b --max-hops 4
/timeline build
/report generate --format pdf
```

Die vollstaendige lokal verfuegbare Liste steht in `docs/COMMANDS.md`. `docs/Command-Katalog_Network-Intelligence.pdf` bleibt die unveraenderte Referenz. Noch nicht aktiviert sind Plattform-Capture, Crawling, Watches, Alerts, Sharing, externe Kommunikation und Identitaetszusammenfuehrungen.

## Bedienung

1. Mit `python app.py` starten und `http://127.0.0.1:8080` oeffnen.
2. Einen Fall anlegen oder den lokalen Eingang verwenden.
3. Beobachtung mit Original-URL und Zeitpunkt erfassen. Der Collector verknuepft explizite Erwähnungen, Hashtags und Links mit dieser Beobachtung.
4. Timeline, Graph und Profiluebersicht nutzen. Netzwerkkanten fuehren direkt zur jeweiligen Quell-URL; die Zeit erscheint neben der Kante.
5. Notizen, Screenshot-Referenzen und klar als unbestaetigt markierte Hypothesen nur mit belegter Grundlage hinterlegen.
6. Den Fall ueber die Kopfzeile als JSON oder PDF exportieren.
