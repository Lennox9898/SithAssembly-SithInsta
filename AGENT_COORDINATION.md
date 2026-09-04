# SithAssembly//Conclave Coordination Contract

Diese Datei ist der operative Vertrag fuer lokale Spezialisten, Module und spaetere Agentenadapter. Die maschinenlesbare Registry liegt in [`config/agent_registry.json`](config/agent_registry.json). Der Coordinator darf nur registrierte lokale Rollen und Topics verwenden.

## Editierbare Policy

Dieser Abschnitt ist fuer menschliche Bearbeitung vorgesehen. Aendere ihn und die Registry, um Arbeitsregeln, Freigaben, Rollenbeschreibungen oder die Reihenfolge der Verarbeitung festzulegen. Ein Agent darf diese Policy nicht selbst aendern.

- Arbeitsziel: Lokale, beleggebundene Fallarbeit und nachvollziehbare Review-Kandidaten.
- Erlaubte Daten: Manuell erfasste, explizit importierte oder lokal abgelegte Belege.
- Automatisierung: Laufart, Frequenz und externe Adapter sind Betreiberentscheidungen. Der aktuelle lokale Server fuehrt nur die vorhandenen lokalen Module aus; weitere Ausfuehrungsarten brauchen einen separaten Adapter und eine klar eingetragene Konfiguration.
- Standard bei Unsicherheit: `needs_review` statt einer Behauptung.
- Freigaben: `review.decision`, `export.request`, `vault.create` und `model.download` brauchen immer einen Menschen.

### Eigene Regeln

Hier koennen eigene, fallbezogene Regeln als klare Saetze ergaenzt werden. Beispiel: `Keine OCR auf Bildbelegen ohne vorherige Sichtpruefung.`

## Grundsatz

Der Coordinator verteilt Ereignisse. Er uebergibt keine uneingeschraenkten Shell-, Netzwerk- oder Datenbankrechte. Jeder Worker liefert ein pruefbares Ergebnis zurueck; nur die zentrale Persistenzschicht schreibt in die Fallakte.

## Event Envelope

```json
{
  "event_id": "uuid",
  "topic": "analysis.review_candidate",
  "case_id": 12,
  "input_refs": ["observation:44", "evidence:91"],
  "input_hash": "sha256:...",
  "producer": "signalforge-analysis",
  "configuration_version": "registry:1|model:revision",
  "created_at": "2026-09-04T12:00:00Z",
  "payload": {
    "result_ref": "analysis_run:18"
  }
}
```

`payload` enthaelt nur IDs oder kleine, schema-validierte Metadaten. Rohbilder, Vault-Passphrasen, Tokens und grosse Beleginhalte werden nicht als Agentennachricht transportiert.

## Regeln fuer die Zustandsuebergabe

- Ein Worker konsumiert nur Topics aus `subscribes_to` und erzeugt nur Topics aus `publishes`.
- Ein Worker liefert `completed`, `failed` oder `needs_review`; er setzt niemals einen Review als akzeptiert.
- Der Idempotenzschluessel lautet `case_id + topic + input_hash + configuration_version`.
- Wiederholungen mit gleichem Idempotenzschluessel liefern den vorhandenen Lauf statt doppelter Kanten oder OCR-Ergebnisse.
- Fehler werden mit Fehlerklasse, Zeit und Input-Referenzen geloggt, nicht mit Rohinhalt oder Geheimnissen.

## Human Gates

Folgende Topics sind die aktuellen Standard-Human-Gates und koennen in der Registry angepasst werden:

- `review.decision`
- `export.request`
- `vault.create`
- `model.download`

Weitere Gates koennen in `config/agent_registry.json` hinzugefuegt werden. Die gewuenschte Ausfuehrungslogik muss durch Serverlogik erzwungen werden; ein Prompt oder Agentenhinweis allein ist keine Zugriffskontrolle.

## Account Adapter Configuration

[`config/instagram_accounts.local.json`](config/instagram_accounts.local.json) is the human-editable local inventory for a future account-based adapter. It is intentionally separate from the agent registry because accounts and credentials are operational configuration, not agent capabilities.

- Edit `username`, `purpose`, `execution_profile`, `requested_capabilities`, `agent_topics` and `operator_notes` directly.
- Keep `enabled` set to `false` until a separate adapter exists and its schedule, scope and reporting behavior are configured.
- Use `secret_ref` for a local secret provider reference such as `env:INSTAWATCH_IG_MONITOR_01_PASSWORD`. Do not add a `password` field, a session cookie or a token to this file.
- The current server does not read this file, log in, collect data or schedule runs. A future adapter should resolve the secret only at runtime and report only connection state and references through `/api/agent-reports`.

### Next Connector Step

The `connector_plan` block is the editable starting point for the future adapter. It reserves the following behavior without enabling it today:

- `startup`: manual, scheduled or server-start behavior selected by the operator.
- `work_queue`: persistent collection jobs with checkpoints and idempotency keys.
- `quota_mode`: provider-configured pacing, response-aware backoff and visible usage reporting.
- `failure_strategy`: a paused or failed run is reported to the agent journal and can be resumed from its checkpoint.
- `report_topic`: the topic used by the adapter to report a completed or blocked collection run.

The next code implementation is a queue and adapter boundary, not account-count scaling. Capacity should be measured against the configured provider quota and the observed adapter throughput before increasing any workload.

## Clawdbot/OpenClaw Gateway

`SithAssembly//ClawBridge` is a prepared, disabled bridge for `clawdbot.you` and its OpenClaw Gateway. Its local configuration is [`config/clawdbot.local.json`](config/clawdbot.local.json); its implementation notes are in [`docs/CLAWDBOT.md`](docs/CLAWDBOT.md).

The server exposes `GET /api/clawdbot` for a secret-free readiness view. The current dispatcher policy is `not_configured`, so ClawBridge does not contact OpenClaw or forward tasks to modules or commands.

`GET /api/clawdbot/manifest` and [`CLAWDBOT_SKILL.md`](CLAWDBOT_SKILL.md) provide the local agent contract: discovery, existing read surfaces, append-only reports and the already implemented CommandDeck endpoint.

Example connection report after a future adapter has run:

```json
{
  "agent_id": "vektorzero-collector",
  "state": "completed",
  "summary": "Configured collection run completed.",
  "output_refs": ["import_batch:24"],
  "connections": [
    {
      "name": "ig_monitor_01",
      "kind": "account_adapter",
      "state": "connected",
      "detail": "Configuration reference: instagram_accounts.local.json"
    }
  ]
}
```

## Agentenberichte

Ein Agent kann seine ausgefuehrte Arbeit, Ausgabe-Referenzen und benannte lokale Anbindungen ueber die lokale API melden. Berichte sind append-only in `data/agent_reports.jsonl`; sie aendern weder diese Policy noch die Registry.

```text
POST /api/agent-reports
GET /api/agent-reports?limit=100
```

Minimaler Bericht:

```json
{
  "agent_id": "signalforge-analysis",
  "case_id": 12,
  "state": "needs_review",
  "summary": "Comment feature scoring finished; two candidates require review.",
  "output_refs": ["analysis_run:18", "observation:44"],
  "connections": [
    {
      "name": "PyOD ECOD",
      "kind": "local_model",
      "state": "used",
      "detail": "Model revision is stored with the analysis run."
    }
  ]
}
```

Erlaubte Statuswerte: `completed`, `failed`, `needs_review`, `blocked`, `info`. Nur aktive, in der Registry eingetragene Agenten duerfen berichten. Eine `connection` ist ein transparenter Statushinweis; sie startet keine Verbindung und ruft keine URL ab.

## Neue Agenten anschliessen

1. Rolle, Modul, erlaubte Topics und minimale Berechtigungen in `config/agent_registry.json` eintragen.
2. Ein enges Request-/Response-Schema und eine lokale Testimplementierung erstellen.
3. Unit-Test fuer Registry, Schema und Idempotenz hinzufuegen.
4. Im Dev-Modus starten und `/api/agents`, Runtime-Logs sowie Ergebnisreferenzen pruefen.
5. Erst danach `enabled: true` setzen.

Ein externer Dienst oder ein Agentenframework wird nicht allein durch einen Registry-Eintrag verbunden. Jede Verbindung braucht einen expliziten, pruefbaren Adapter mit eigener Konfiguration und Protokollierung.
