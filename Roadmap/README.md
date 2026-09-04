# SithAssembly//Instawatch Roadmap

Stand: 2026-09-04. Diese Roadmap priorisiert lokale, beleggebundene Fallarbeit. Automatisierung und weitere Ausfuehrungsarten werden als getrennte, konfigurierbare Adapter geplant; sie sind nicht Teil der aktuellen lokalen Runtime.

## Aktueller Stand

- Lokaler SQLite-Server, CommandDeck, Fallverwaltung, Graph, Timeline und JSON/PDF-Export sind vorhanden.
- EvidenceVault, lokale JSONL-Runtime-Logs und eine kontrollierte Modul-Registry sind vorhanden.
- Kommentar-Ausreisser und OCR sind als opt-in Adapter vorhanden.
- `config/agent_registry.json` beschreibt lokale Agentenrollen und Topic-Routing. Sie verbindet noch keine fremden Dienste.

## Phase 1: Belegter Eingang

Ziel: Jeder Fall startet mit nachvollziehbaren, lokal abgelegten Daten.

- Import-Schema fuer manuelle Erfassung und offiziell exportierte Dateien festlegen.
- Fuer jeden Import: Quelle, Zeitpunkt, Hash, Operator und Lizenz-/Nutzungsnotiz erfassen.
- Deduplication ueber Content- und Kontextfingerprints vor dem Anlegen weiterer Beobachtungen.
- UI fuer Importvorschau, Feldvalidierung und Importprotokoll bauen.

Abnahme: Ein Testfall kann importiert, wiederholt importiert und vollstaendig bis zur Ursprungsdatei zurueckverfolgt werden.

## Phase 1A: Account Connector and Scheduled Collection

Ziel: Ein spaeterer Account-Adapter kann beim lokalen Serverstart konfiguriert aktiviert werden, Auftraege kontrolliert abarbeiten und jeden Lauf nachvollziehbar berichten.

- `config/instagram_accounts.local.json` als lokale Account- und Connector-Konfiguration verwenden; der aktuelle Wert `enabled: false` bleibt bis zur Adapterimplementierung bestehen.
- Persistente Collection-Jobs mit Account-Referenz, Fall-ID, Topic, Startzeit, Status, Cursor/Checkpoint und Idempotenzschluessel einfuehren.
- Eine zentrale Warteschlange statt paralleler Direktanfragen verwenden. Sie plant nur innerhalb einer konfigurierten, provider-konformen Quote und protokolliert Anfragen, Antwortstatus, Backoff und Wiederanlauf.
- Autostart als editierbares Connector-Profil vorsehen: deaktiviert, manuell, zeitgesteuert oder beim lokalen Serverstart. Jeder Start erstellt einen Agentenbericht.
- Zeitueberschreitungen, Fehler oder Quota-Antworten fuehren zu Backoff, `blocked` oder `failed`; sie werden nicht durch Account-Sharding oder Umgehungslogik ersetzt.
- Der Adapter schreibt seine Ergebnisse ueber den vorhandenen Importpfad in die Fallakte und meldet `collection.run_reported` mit Batch- und Belegreferenzen.

Abnahme: Ein freigegebener Testlauf wird beim lokalen Start nach dem gewaehlten Profil eingeplant, kann fortgesetzt werden und erzeugt einen vollstaendigen Agentenbericht ohne doppelte Eintraege.

## Phase 2: Analysefunnel

Ziel: Kandidaten werden stufenweise erzeugt, ohne aus einem Score eine Behauptung zu machen.

1. Normalisieren: Text, Zeit, Handle, Links, Hashtags und Quellenbindung.
2. Deterministisch extrahieren: Duplikate, gemeinsame Domains, Mentions, Zeitfenster und Accountwechsel-Hinweise.
3. Leichtgewichtige Modelle: ECOD-Ausreisser, OCR, semantische Aehnlichkeit und Zero-Shot-Themenkandidaten.
4. Evidenzgraph: Nur Kanten mit Beleg-ID, Regel/Modellversion, Zeitpunkt und Konfidenz speichern.
5. Review-Gate: Menschen bestaetigen, verwerfen oder kommentieren Kandidaten.

Abnahme: Jeder Kandidat zeigt Rohbeleg, Transformationsschritte, Modell-/Regelversion und den Grund fuer den Score.

## Phase 3: Arbeitsoberflaeche

Ziel: Recherche und Review sind schneller als die manuelle Tabellenarbeit.

- Runtime- und Agentenstatus im Interface anzeigen.
- Review-Queue nach Quelle, Konfidenz, Modellversion und Fall filtern.
- Graph-Kanten und Timeline-Ereignisse direkt mit Beobachtung, Screenshot und Originalzeitpunkt verlinken.
- Quellenverwaltung mit Vertrauensniveau, Archivhinweis und Gegenbelegen ausbauen.
- Vergleichsansicht fuer Profil-Snapshots und dokumentierte Alias-/Wechselhinweise ergaenzen.

Abnahme: Ein Analyst kann vom Graph-Knoten bis zum Originalbeleg navigieren und jede Zuordnung nachvollziehen.

## Phase 4: Lokale Orchestrierung

Ziel: Verarbeitung ist wiederholbar, abbrechbar und auditierbar.

- Persistente Job-Tabelle mit `queued`, `running`, `completed`, `failed`, `needs_review` und `cancelled` einfuehren.
- Ereignis-Envelope nach `AGENT_COORDINATION.md` persistieren; Jobs idempotent ueber Input-Hash und Konfigurationsversion machen.
- Pro Modul Zeit, Modellrevision, Fehlerklasse, Input-/Output-Referenzen und Verbrauch protokollieren.
- Nur erlaubte Topics aus `config/agent_registry.json` routen; keine Shell- oder Netzwerkkapabilitaet aus der Registry ableiten.

Abnahme: Ein abgebrochener lokaler Lauf kann ohne doppelte Kanten oder doppelten OCR-Text fortgesetzt werden.

## Phase 5: Modelle und Evaluation

Ziel: Modelle erst nach messbarer Qualitaetskontrolle aktivieren.

- Zuerst einen versionierten Goldsatz aus rechtmaessig gespeicherten, anonymisierten oder freigegebenen Beispielen erstellen.
- Pro Aufgabe getrennte Metriken definieren: OCR CER/WER, Retrieval Recall@k, Klassifikation Precision/Recall je Klasse, Ausreisser-Review-Quote.
- Zeit- und Quellen-Splits verwenden, damit Duplikate und gleiche Ereignisse nicht in Train und Test landen.
- Fehlerraten nach Sprache, Bildqualitaet und Inhaltstyp analysieren.
- Kein Modellergebnis als Tatsachenfeststellung oder Identitaetsentscheidung verwenden.

Abnahme: Ein Modell wird nur aktiviert, wenn es gegen die deterministische Baseline gewinnt und die Review-Last nicht unvertretbar erhoeht.

## Phase 6: Berichte und Betrieb

Ziel: Fallakten bleiben exportierbar und nachvollziehbar.

- PDF/JSON/EvidenceVault anhand echter, bereinigter Testfaelle pruefen.
- Backup-/Restore-Prozess fuer SQLite, Belege, Logs und Vault-Schluessel dokumentieren.
- Konfigurationsprofil fuer Development, Offline-Analyse und optionales lokales Modell-Serving einfuehren.
- End-to-End-Tests fuer Import -> Analyse -> Review -> Export automatisieren.

Abnahme: Ein Fall kann auf einem neuen lokalen Rechner aus Backup und verschluesselter Vault validiert werden.

## Reihenfolge

1. Phase 1, Phase 1A und die persistente Job-Tabelle aus Phase 4.
2. ECOD/OCR mit echten, freigegebenen Testdaten aus Phase 2 und 5.
3. Phase 3 fuer sichtbare Review- und Agentenstatusdaten.
4. Semantische Suche und spezialisierte Klassifikation erst nach dem Goldsatz.
5. Optionale LLM-Assistenz zuletzt und ausschliesslich als quellengebundener Entwurf.

Weiterfuehrend: `Roadmap/MODEL_PORTFOLIO.md`, `Roadmap/AGENT_ORCHESTRATION.md` und `AGENT_COORDINATION.md`.
