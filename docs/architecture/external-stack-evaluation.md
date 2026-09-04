# Externe Bausteine: Ist-Analyse

Stand: 2026-09-04. Referenz: `docs/Agentenstack_Evaluationsdossier_2026-09-04.pdf`.

Diese Bewertung betrachtet nur die aktuelle lokale Arbeitsumgebung. Sie uebernimmt
keine Software, startet keine Dienste und ersetzt keine eigene Logik. Release-Stand,
Lizenz, Sicherheitsmeldungen und Kompatibilitaet jedes Kandidaten muessen unmittelbar
vor einem PoC erneut gegen die jeweilige Primaerquelle geprueft werden.

## Bestehende Architekturkarte

| Bereich | Vorhandener Anker | Bewertung |
| --- | --- | --- |
| HTTP und UI | `app.py`, `src/server.py`, `web/` | Lokaler Server mit API und Fallarbeitsoberflaeche. Kein externer Gateway erforderlich. |
| Commands | `src/command_engine.py`, `SithAssembly.Runtime.py` | Allowlisted lokale Commands gegen die Fallakte. Kein allgemeiner Shell- oder Tool-Proxy. |
| Registry und Module | `config/module_registry.json`, `src/module_runtime.py`, `src/assembly_manifest.py` | Explizit deklarierte `src.*`-Module, kontrolliertes Laden und lesbares Manifest. |
| Koordination | `config/agent_registry.json`, `src/agent_coordination.py`, `src/agent_controller.py` | Lokales Topic- und Capability-Modell; kein externer Message-Broker. |
| Daten und Graph | `src/database.py`, `src/repository.py`, `src/relationship_engine.py`, `src/graph_viewer.py` | SQLite, evidenzgebundene Kanten, lokale Gruppen und Zentralitaet. |
| Analyse | `src/comment_anomaly.py`, `src/ocr_engine.py`, `src/local_llm.py` | Optionale lokale Adapter; keine stillen Modell-Downloads oder externen Aufrufe. |
| Evidenz und Export | `src/evidence_integrity.py`, `src/evidence_vault.py`, `src/report_generator.py` | Fingerprints, opt-in verschluesselte Pakete sowie JSON/PDF-Export. |
| Telemetrie | `src/runtime_logging.py`, `src/runtime_doctor.py` | Lokale redigierte JSONL-Logs und read-only Runtime-Diagnose. |
| Deployment | `config/deployment.local.json`, `src/deployment_preflight.py`, `deploy/` | Inaktive Vorbereitungs-Topologie; noch kein gestarteter Cluster. |

## Kandidaten und Integrationsgrenzen

| Kandidat | Status | Begruendete Integrationsgrenze |
| --- | --- | --- |
| IBM ContextForge | Ignorieren vorerst | `src/module_runtime.py` und `config/module_registry.json` loesen die aktuelle lokale Registry-Aufgabe. Erst benchmarken, wenn mehrere externe MCP/A2A-Dienste betrieben werden. |
| agentgateway | Ignorieren vorerst | Kein externer MCP/A2A- oder gRPC-Traffic vorhanden. Ein zweiter Gateway neben `src/server.py` waere aktuell Doppelstruktur. |
| NATS JetStream | PoC vormerken | Passt spaeter zu `config/agent_registry.json`-Topics. Ein einzelnes Event muss Idempotenz, Replay, Backpressure und Fehlerpfad nachweisen. |
| Temporal | PoC vormerken | Erst relevant fuer einen vorhandenen langen, unterbrechbaren Job. Das heutige lokale Request-Modell braucht noch keinen Workflow-Server. |
| Open Policy Agent | Prioritaet: kleiner PoC | `config/agent_registry.json` enthaelt Rollen, Freigaben und Capabilities. Ein zentraler Policy-Input waere ein klarer Gewinn, wenn fail-closed. |
| OpenLineage und Rekor | Konzepte uebernehmen | `src/runtime_logging.py`, `src/evidence_integrity.py` und `src/evidence_vault.py` sind die Basis. Zuerst ein internes Run-/Artefakt-Envelope spezifizieren. |
| OpenCTI | Datenmodell-Muster uebernehmen | Nuetzlich sind Dedup, Confidence, Quellenprioritaet und als `inferred` markierte Kanten. Kein vollstaendiger OpenCTI-Stack. |
| QUT Coordination Network Toolkit | Methodik bewerten | Plattformneutrale Koordinationsfeatures gegen `src/pattern_engine.py` testen. Ergebnisse bleiben reviewpflichtige Musterkandidaten. |
| OSINTGraph | Referenz, nicht Kern | Import-, Graph- und UI-Ideen isoliert vergleichen. Keine Kopplung an fragile Zugriffsmethoden. |
| OpenTelemetry und AgentOps | OTel-first vormerken | `src/runtime_logging.py` ist eine lokale Grundlage. Erst Trace-Contract definieren, dann einen exportierbaren Adapter. |
| Firecracker, gVisor, Microsandbox | Serverseitig spaeter pruefen | Auf dem lokalen Windows-Entwicklungsplatz kein Gewinn. Fuer untrusted Workloads nur mit Risikoklasse und Netzwerkgrenzen bewerten. |

## Entscheidung

Die naechste sinnvolle Aenderung ist kein Framework-Import. Prioritaet haben drei
kleine, messbare Vertrage: Policy-Input, Event-Envelope und Provenance-Envelope.
Sie halten die lokale Architektur kompatibel mit OPA, NATS/JetStream und OTel,
ohne einen der Dienste vorauszusetzen. Der bestehende Command-Core und die
evidenzgebundene Fallarbeit bleiben der Bezugspunkt.
