# Externe Bausteine: Scorecard

Stand: 2026-09-04. Die Werte bewerten den Architektur-Fit zur aktuellen
Codebasis, nicht die Qualitaet oder Sicherheit eines fremden Projekts. Skala:
`0` ungeeignet, `1` schwach, `2` begrenzt, `3` brauchbar, `4` stark, `5` sehr stark.

Gewichtung: Architektur-Fit 20 %, eliminierte Eigenkomplexitaet 15 %, Betriebsaufwand
10 %, Skalierung/Backpressure 10 %, Observability/Debugging 10 %, Austauschbarkeit
10 %, Daten-/Policy-Kontrolle 10 %, Reife/Wartung 5 %, Lizenz/Self-Hosting 5 % und
Migration/Rollback 5 %. Nicht verifizierbare Kriterien bleiben offen statt geraten.

| Kandidat | Vorlaeufiger Score | Kategorie | Beleg im Repository | Bedingung vor einem PoC |
| --- | ---: | --- | --- | --- |
| OPA | 3.8 | PoC vormerken | `config/agent_registry.json` hat Freigaben und Capabilities, aber keinen zentralen Policy-Contract. | Aktuelle Lizenz, Release und fail-closed Python-Anbindung verifizieren. |
| OpenLineage/Rekor-Ideen | 3.6 | Konzepte uebernehmen | `src/evidence_integrity.py`, `src/evidence_vault.py` und `src/runtime_logging.py` besitzen Hash- und Log-Anker. | Privates Provenance-Format festlegen; keine sensiblen Belegdaten ausleiten. |
| NATS JetStream | 3.4 | PoC vormerken | `config/agent_registry.json` modelliert bereits Publishes/Subscribes. | Ein Event-Envelope plus Idempotenz- und Replay-Test muss bestehen. |
| OpenTelemetry | 3.3 | PoC vormerken | `src/runtime_logging.py` redigiert lokal und `src/runtime_doctor.py` liefert Diagnose. | Trace- und Redaction-Vertrag zuerst definieren. |
| OpenCTI-Muster | 3.2 | Konzepte uebernehmen | `src/repository.py`, `src/relationship_engine.py` und Review-Commands behandeln Beziehungen, Konfidenz und Hypothesen. | Eigenes Schema gegen Dedup- und Konflikt-Testkorpus pruefen. |
| Temporal | 2.8 | PoC vormerken | `src/agent_controller.py` bildet kurze Stufen ab; es gibt noch keinen langen resumierbaren Workflow. | Einen realen, lokalen Langlaufjob mit Crash/Resume definieren. |
| QUT-Methodik | 2.8 | Konzepte uebernehmen | `src/pattern_engine.py` und `src/comment_anomaly.py` sind die Analysegrenzen. | Synthetischen Testkorpus, Fehlalarmmetriken und Erklaerbarkeit vorsehen. |
| ContextForge | 2.4 | Ignorieren vorerst | `src/module_runtime.py` und `config/module_registry.json` liefern lokale Discovery. | Erst bei mehreren externen Diensten gegen einen Gateway-Use-Case benchmarken. |
| agentgateway | 2.2 | Ignorieren vorerst | `src/server.py` und der Command-Core decken den heutigen lokalen Zugriff ab. | Erst bei realem MCP/A2A- oder gRPC-Bedarf bewerten. |
| OSINTGraph | 2.0 | Referenz | Graph und Casework liegen bereits in `src/graph_viewer.py` und `src/repository.py`. | Nur Datenmodell/Import- und Query-Ideen isoliert pruefen. |
| Firecracker/gVisor/Microsandbox | 1.9 | Serverseitig spaeter | `deploy/` ist nur Preflight und startet keine untrusted Worker. | Threat Model, RuntimeClass, GPU/Dateisystembedarf und Netzwerkgrenzen nachweisen. |

## Stop-Regeln

- Kein Kandidat ersetzt den eigenen Command-Core, die evidenzgebundene Beziehungserzeugung oder menschliche Review-Schritte ohne nachgewiesenen Vorteil.
- Jeder PoC braucht einen Adapter, ein messbares Exit-Kriterium und einen rueckstandsfreien Entfernungsweg.
- Scores werden erst nach Release-, Lizenz-, Security- und Kompatibilitaetspruefung finalisiert.
- Ein Dienst ohne weniger Eigenkomplexitaet, besseren Standard oder besseres Debugging bleibt draussen.
