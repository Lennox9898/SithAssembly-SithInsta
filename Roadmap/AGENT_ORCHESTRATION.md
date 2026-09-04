# Agent Orchestration

## Entscheidung

Die erste Ausbaustufe bleibt eine lokale, deterministische Job-Pipeline. Die vorhandene SQLite-Datenbank, `config/module_registry.json`, `config/agent_registry.json` und JSONL-Logs sind dafuer der passende Kern. Ein LLM entscheidet nicht selbst, welcher Job Schreibrechte bekommt.

`LangGraph` ist eine spaetere optionale Adapterebene, wenn mehrere spezialisierte Modelle mit gespeichertem Zustand oder parallelen Schritten erforderlich werden. Die Dokumentation unterscheidet bewusst feste Workflows von dynamischen Agents und beschreibt Router, Subagents und Skills als kombinierbare Muster. [LangGraph Workflows](https://langchain-ai.github.io/langgraph/agents/tools/), [LangGraph Multi-Agent](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/)

## Lokaler Funnel

```text
input import
  -> evidence fingerprint
  -> deterministic extraction
  -> optional analysis jobs
  -> evidence-bound relationship candidates
  -> human review gate
  -> report/export
```

Alle Pfeile sind persistente Ereignisse mit Fall-ID, Input-Hash und Erzeuger. Es gibt keine direkte Agent-zu-Agent-Datenbankmutation.

## Rollen

- `VektorZero`: validiert und normalisiert lokale Eingaben.
- `SignalForge`: erzeugt Ausreisser-Kandidaten aus transparenten Kommentarmerkmalen.
- `GlyphWatch`: verarbeitet nur explizit ausgewaehlte lokale Bildbelege nach Modellbestaetigung.
- `SpectreNet`: erzeugt beleggebundene Beziehungskandidaten.
- `CaseForge`: setzt Review-Aufgaben; die weitere Entscheidung ist ueber die konfigurierbaren Human-Gates steuerbar.
- `BlackArchive`: rendert nur nach Freigabe lokale Exporte.

Die aktuelle, maschinenlesbare Quelle ist [`config/agent_registry.json`](../config/agent_registry.json). Der Server gibt sie lokal unter `GET /api/agents` aus.

## Integrationsstufen

### Stufe A: Ohne Agentenframework

- Neue Tabellen `processing_jobs`, `processing_events`, `agent_runs` und `review_decisions` anlegen.
- Ein lokaler Worker nimmt nur freigegebene Topics aus der Registry an.
- Jeder Job kann `queued`, `running`, `completed`, `failed`, `cancelled` oder `needs_review` sein.
- Idempotenzschluessel: `case_id + topic + input_hash + configuration_version`.

Das ist die naechste Implementierungsstufe und reicht fuer die meisten Modulketten.

### Stufe B: Lokale Modellservices

- Modelle hinter eindeutig versionierten lokalen HTTP- oder Prozessadaptern betreiben.
- Jeder Adapter hat enge Eingabe-/Ausgabe-Schemas und keine Datenbankrechte.
- Der lokale Coordinator besitzt allein die Schreibrechte und verifiziert die Antwort gegen das Schema.
- Modellservice-Ausfall erzeugt standardmaessig `failed` oder `needs_review`; alternative Ausfuehrungswege muessen als eigene Adapter sichtbar konfiguriert sein.

### Stufe C: Optionale LangGraph-Subgraphs

- Nur verwenden, wenn ein Arbeitsschritt wirklich dynamische Toolwahl oder parallele Spezialisten braucht.
- Ein Hauptgraph kontrolliert Context, erlaubte Tools und Human Gates.
- Subgraphs bekommen nur fallbezogene, minimale Kontextpakete; sie erhalten keine Passphrase, keine Vault-Schluessel und keine globalen Datenbankrechte.
- Checkpoints werden lokal referenziert und wie andere Verarbeitungslaufe protokolliert.

## Konfigurierbare Betriebsregeln

- Die aktuelle lokale Runtime hat keine externen Adapter. Automatisierte Laeufe, weitere Agententypen oder Verbindungen werden ueber separate, versionierte Adapter umgesetzt.
- Jeder Adapter definiert seine Berechtigungen, Topics, Datenformate, Zeitplaene, Fehlerbehandlung und Protokollierung explizit in der Registry oder seiner eigenen Konfiguration.
- Modellantworten sollten Beleg-IDs und Modellrevisionen mitliefern, damit Verarbeitungen nachvollziehbar bleiben.
- Freigaben fuer Review, Export und Modell-Downloads folgen den editierbaren Human-Gates in der Registry.
- Neue Agents werden nach Registry-Pruefung, Unit-Tests und einem echten lokalen Lauf aktiviert.
