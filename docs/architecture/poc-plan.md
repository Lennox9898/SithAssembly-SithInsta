# Externe Bausteine: Begrenzter PoC-Plan

Stand: 2026-09-04. Dieser Plan ist bewusst analyse-first. Kein Abschnitt startet
einen Dienst, installiert Abhaengigkeiten oder migriert Daten. Alle PoCs laufen
parallel zum bestehenden lokalen Ablauf und muessen entfernbar bleiben.

## Phase 0: Vertraege vor Infrastruktur

1. **Policy-Input:** Ein JSON-kompatibles Objekt fuer Rolle, Modul, Capability,
   Datenklasse, Aktion und Limits. Anker: `config/agent_registry.json`.
   Erfolg: fuenf vorhandene Entscheidungen koennen reproduzierbar bewertet werden;
   bei Policy-Fehler wird abgelehnt.
2. **Event-Envelope:** `schema_version`, `event_id`, `trace_id`, `occurred_at`,
   `actor`, `subject`, `payload_ref` und `idempotency_key`. Anker:
   `src/agent_coordination.py` und `src/agent_controller.py`.
   Erfolg: eine lokale Simulation erkennt ein dupliziertes Event und verarbeitet
   eine gespeicherte Sequenz deterministisch erneut.
3. **Provenance-Envelope:** Run-ID, Modul-/Modellprofil, Eingabe-Fingerprint,
   Quellreferenzen, Ergebnis-Fingerprint und Fehlerstatus. Anker:
   `src/evidence_integrity.py`, `src/evidence_vault.py`, `src/runtime_logging.py`.
   Erfolg: ein Artefakt kann lokal auf Integritaet und Herkunft zurueckgefuehrt
   werden, ohne Klartextbelege in Telemetrie zu schreiben.

## Phase 1: Einzelne, austauschbare PoCs

| PoC | Kandidat | Umfang | Exit-Kriterium | Stop-Kriterium |
| --- | --- | --- | --- | --- |
| Policy | OPA | Fuenf fest definierte lokale Zugriffsentscheidungen ueber Adapter pruefen. | Alle erlaubten und verweigerten Faelle sind reproduzierbar; Ausfall ist fail-closed. | Kein klarer Vorteil gegen deklarative lokale Regeln. |
| Event | NATS JetStream | Einen Eventtyp mit zwei Produzenten, drei Consumern, Worker-Crash und Replay testen. | Keine doppelte Fallaktion; Backpressure und Wiederanlauf sind messbar. | Zusatzbetrieb ohne Robustheitsgewinn. |
| Workflow | Temporal | Einen langen lokalen Analyse-/Importlauf mit Checkpoint, Timeout und manueller Pause abbilden. | Crash/Resume bewahrt Status und Belegreferenzen. | Kein reprasentativer Langlaufjob oder zu hohe Betriebsbelastung. |
| Telemetrie | OpenTelemetry | Einen Trace fuer Command -> Policy -> Worker -> Artefakt bilden; Redaction testen. | Keine Secrets oder Beleginhalte im Export, Korrelation bleibt nachvollziehbar. | Trace-Contract nicht stabil oder Debugging schlechter als JSONL. |
| Graphqualitaet | OpenCTI- und QUT-Muster | Synthetischen Korpus mit Aliasen, Konflikten, koordinierten und normalen Gruppen auswerten. | Konfidenz, `inferred`, Fehlalarme und Beleglinks sind nachvollziehbar. | Kein Gewinn gegen einfachere Regeln. |

## Reihenfolge und Schutzgrenzen

1. Zuerst die drei Vertraege schreiben und mit Unit-Tests absichern.
2. Danach hoechstens einen Dienst-PoC gleichzeitig ausfuehren.
3. Vor jedem PoC aktuelle Primaerquellen fuer Release, Lizenz, Advisories und Self-Hosting pruefen.
4. Keine Plattform-Automatisierung, keine nicht autorisierte Datenerhebung und keine Ausleitung von Fallinhalten an externe Observability-Dienste.
5. Erst nach einem bestandenen PoC eine separate Integrationsentscheidung treffen.
