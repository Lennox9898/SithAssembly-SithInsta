from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any

from src.repository import Repository


@dataclass(frozen=True)
class CommandResult:
    normalized: str
    summary: str
    data: Any
    links: list[dict[str, str]]
    next_commands: list[str]
    state: str = "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "normalized": self.normalized,
            "summary": self.summary,
            "data": self.data,
            "links": self.links,
            "next_commands": self.next_commands,
            "state": self.state,
        }


class CommandEngine:
    """Allowlisted local command layer for the case database, never a platform automation API."""

    HELP = {
        "/context": "Aktuellen lokalen Fallkontext anzeigen.",
        "/find posts --query <text>": "Lokale Beobachtungen durchsuchen.",
        "/find accounts --query <text>": "Search profiles in the active case.",
        "/find mentions @handle": "Belegte Erwahnungen eines Accounts anzeigen.",
        "/find links --domain <domain>": "Gespeicherte geteilte Links filtern.",
        "/source add <url>": "Register an external source in the active case.",
        "/profile show|history|connections @handle": "Show local profile and evidence data.",
        "/profile activity|aliases @handle": "Show local activity or documented account-change indicators.",
        "/profile compare @a @b": "Compare two local profiles and their shared connections.",
        "/graph build|centrality|communities": "Analyze the local case network.",
        "/graph common @a @b": "Gemeinsame belegte Verbindungen anzeigen.",
        "/graph path @a @b": "Gerichteten, belegten Pfad im Fallgraphen suchen.",
        "/timeline build": "Lokale Fallchronologie anzeigen.",
        "/timeline compare @a @b": "Zeitliche Aktivitaet lokaler Profile zusammen anzeigen.",
        "/case create <title>": "Create a new local case.",
        "/case status": "Fallkennzahlen anzeigen.",
        "/case note <text>": "Save a note in the active case.",
        "/case tag <label>": "Register a local case tag.",
        "/review queue": "Show unverified hypotheses and profile changes.",
        "/review approve|reject claim:<id>": "Review or reject an identity hypothesis.",
        "/confidence set relationship:<id> <0-1>": "Konfidenz einer belegten Kante korrigieren.",
        "/contradictions|duplicates|gaps": "Lokale Datenqualitaet pruefen.",
        "/agent status": "Lokale Verarbeitungsschritte anzeigen.",
        "/history": "Lokale ausgefuehrte Commands anzeigen.",
        "/report generate --format pdf": "PDF-Bericht herunterladen.",
        "/export case --format json|pdf": "Export the complete case.",
    }

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def execute(self, raw_command: str, active_case_id: int | None) -> dict[str, Any]:
        result = self._execute(raw_command, active_case_id)
        history_case_id = active_case_id
        if raw_command.strip().lower().startswith("/case create") and isinstance(result.get("data"), dict):
            history_case_id = result["data"].get("id")
        self.repository.record_command(history_case_id, result["normalized"], result["state"], result["summary"])
        return result

    def _execute(self, raw_command: str, active_case_id: int | None) -> dict[str, Any]:
        raw_command = self._clean(raw_command)
        if not raw_command:
            raise ValueError("command is required")
        if not raw_command.startswith("/"):
            raise ValueError("commands must start with /")
        tokens = self._tokens(raw_command)
        command, positionals, options = self._split(tokens)
        normalized = self._normalized(command, positionals, options)

        if command == ("help",):
            topic = positionals[0] if positionals else ""
            items = self.HELP if not topic else {key: value for key, value in self.HELP.items() if topic.lower() in key.lower()}
            return CommandResult(normalized, f"{len(items)} local commands available.", items, [], ["/context", "/find posts --query <text>"]).as_dict()
        if command == ("case", "create"):
            title = " ".join(positionals)
            if not title:
                raise ValueError("case title is required")
            case = self.repository.create_case({"title": title, "description": options.get("description", "")})
            return CommandResult(normalized, f"Created local case {case['id']}.", case, [], [f"/case status --case {case['id']}"]).as_dict()
        case_id = self._case_id(options, active_case_id)
        if command == ("context",):
            case = self._case(case_id)
            return CommandResult(normalized, f"Active case: {case['title']}.", case, [], ["/case status", "/timeline build"]).as_dict()
        if command == ("case", "status"):
            case = self._case(case_id)
            return CommandResult(normalized, f"Case {case['id']} has {case['observation_count']} observations.", case, [], ["/review queue", "/report generate --format pdf"]).as_dict()
        if command == ("case", "note"):
            body = " ".join(positionals)
            note = self.repository.add_note(case_id, {"body": body})
            return CommandResult(normalized, "Note saved in the local case.", note, [], ["/timeline build"]).as_dict()
        if command == ("case", "tag"):
            tag = self.repository.add_case_tag(case_id, " ".join(positionals), options.get("color", "amber"))
            return CommandResult(normalized, "Tag registered for the local case.", tag, [], ["/case status"]).as_dict()
        if command == ("source", "add"):
            if not positionals:
                raise ValueError("source URL is required")
            source = self.repository.add_case_source(case_id, positionals[0], options.get("label", ""))
            return CommandResult(normalized, "Source added to the local evidence register.", source, [{"label": source["label"], "url": source["url"]}], ["/case status", "/report generate --format pdf"]).as_dict()
        if command == ("find", "posts"):
            rows = self.repository.list_case_observations(case_id, {"q": options.get("query", ""), "min_risk": options.get("min-risk", "")})
            rows = rows[: self._limit(options)]
            return CommandResult(normalized, f"Found {len(rows)} local observations.", rows, self._observation_links(rows), ["/timeline build", "/graph build"]).as_dict()
        if command == ("find", "accounts"):
            query = options.get("query", " ".join(positionals)).lower()
            rows = [profile for profile in self.repository.get_case_profiles(case_id) if query in f"{profile['handle']} {profile['display_name']}".lower()]
            return CommandResult(normalized, f"Found {len(rows)} profiles in this case.", rows[: self._limit(options)], [], ["/profile show @handle"]).as_dict()
        if command == ("find", "mentions"):
            if not positionals:
                raise ValueError("handle is required")
            rows = self.repository.find_mentions(case_id, positionals[0])[: self._limit(options)]
            links = [{"label": f"Evidence for {row['source_handle']} -> {row['target_handle']}", "url": row["source_url"]} for row in rows if row.get("source_url")]
            return CommandResult(normalized, f"Found {len(rows)} documented mentions.", rows, links, ["/graph build"]).as_dict()
        if command == ("find", "links"):
            rows = self.repository.find_links(case_id, options.get("domain", ""))[: self._limit(options)]
            links = [{"label": row["label"], "url": row["url"]} for row in rows if row.get("url")]
            return CommandResult(normalized, f"Found {len(rows)} shared links.", rows, links, ["/graph build", "/timeline build"]).as_dict()
        if command in {("profile", "show"), ("profile", "history"), ("profile", "connections"), ("profile", "activity"), ("profile", "aliases")}:
            if not positionals:
                raise ValueError("handle is required")
            detail = self.repository.get_profile_detail(case_id, positionals[0])
            if detail is None:
                return CommandResult(normalized, "Profile is not part of the active case.", [], [], ["/find accounts --query <text>"], "not_found").as_dict()
            if command == ("profile", "history"):
                data = detail["snapshots"]
            elif command == ("profile", "connections"):
                data = detail["connections"]
            elif command == ("profile", "activity"):
                data = self.repository.get_profile_activity(case_id, positionals[0])
            elif command == ("profile", "aliases"):
                data = self.repository.get_profile_aliases(case_id, positionals[0])
            else:
                data = detail
            return CommandResult(normalized, f"Profile data loaded for {detail['profile']['handle']}.", data, [], [f"/profile connections {detail['profile']['handle']}", f"/find mentions {detail['profile']['handle']}"]).as_dict()
        if command == ("profile", "compare"):
            if len(positionals) < 2:
                raise ValueError("two handles are required")
            comparison = self.repository.compare_profiles(case_id, positionals[0], positionals[1])
            if comparison is None:
                return CommandResult(normalized, "One or both profiles are not part of the active case.", [], [], ["/find accounts --query <text>"], "not_found").as_dict()
            return CommandResult(normalized, "Local profile comparison completed.", comparison, [], [f"/graph common {positionals[0]} {positionals[1]}"]).as_dict()
        if command == ("graph", "build"):
            graph = self.repository.get_case_graph(case_id)
            return CommandResult(normalized, f"Graph contains {len(graph['nodes'])} nodes and {len(graph['edges'])} evidence-bound edges.", graph, self._edge_links(graph["edges"]), ["/graph centrality", "/graph communities"]).as_dict()
        if command == ("graph", "centrality"):
            nodes = sorted(self.repository.get_case_graph(case_id)["nodes"], key=lambda node: node["centrality"], reverse=True)
            return CommandResult(normalized, f"Ranked {len(nodes)} nodes by local degree centrality.", nodes[: self._limit(options)], [], ["/graph communities"]).as_dict()
        if command == ("graph", "communities"):
            graph = self.repository.get_case_graph(case_id)
            named_groups = [[next(node["handle"] for node in graph["nodes"] if node["id"] == actor_id) for actor_id in group] for group in graph["groups"]]
            return CommandResult(normalized, f"Found {len(named_groups)} connected components.", named_groups, [], ["/network bridges"]).as_dict()
        if command == ("graph", "path"):
            if len(positionals) < 2:
                raise ValueError("two handles are required")
            graph = self.repository.get_case_graph(case_id)
            max_hops = self._bounded_int(options.get("max-hops"), 4, 1, 8)
            path = self.repository.graph_viewer.shortest_path(graph, positionals[0], positionals[1], max_hops)
            return CommandResult(normalized, f"Found {len(path)} documented path steps.", path, self._edge_links(path), ["/graph build"]).as_dict()
        if command == ("graph", "common"):
            if len(positionals) < 2:
                raise ValueError("two handles are required")
            common = self.repository.get_common_connections(case_id, positionals[0], positionals[1])
            return CommandResult(normalized, f"Found {len(common)} common documented connections.", common, [], ["/graph build"]).as_dict()
        if command == ("timeline", "build"):
            events = self.repository.get_case_timeline(case_id)[: self._limit(options)]
            return CommandResult(normalized, f"Timeline contains {len(events)} events.", events, self._event_links(events), ["/report generate --format pdf"]).as_dict()
        if command == ("timeline", "compare"):
            if len(positionals) < 2:
                raise ValueError("at least two handles are required")
            rows = self.repository.get_timeline_compare(case_id, positionals)[: self._limit(options)]
            return CommandResult(normalized, f"Found {len(rows)} local events for the selected profiles.", rows, self._observation_links(rows), ["/timeline build"]).as_dict()
        if command == ("review", "queue"):
            rows = self.repository.get_review_queue(case_id)
            return CommandResult(normalized, f"{len(rows)} items require review.", rows, [], ["/case status"]).as_dict()
        if command in {("review", "approve"), ("review", "reject")}:
            if not positionals:
                raise ValueError("claim reference is required")
            claim_match = re.search(r"(\d+)$", positionals[0])
            if claim_match is None:
                raise ValueError("invalid claim reference")
            state = "reviewed" if command == ("review", "approve") else "rejected"
            result = self.repository.review_identity_claim(case_id, int(claim_match.group(1)), state, options.get("note", ""))
            return CommandResult(normalized, f"Identity hypothesis marked {state}.", result, [], ["/review queue"]).as_dict()
        if command == ("confidence", "set"):
            if len(positionals) < 2:
                raise ValueError("relationship reference and confidence are required")
            relationship_match = re.search(r"(\d+)$", positionals[0])
            if relationship_match is None:
                raise ValueError("invalid relationship reference")
            result = self.repository.set_relationship_confidence(case_id, int(relationship_match.group(1)), float(positionals[1]), options.get("note", ""))
            return CommandResult(normalized, "Relationship confidence updated.", result, [], ["/graph build"]).as_dict()
        if command == ("contradictions",):
            rows = self.repository.find_contradictions(case_id)
            return CommandResult(normalized, f"Found {len(rows)} potential local contradictions.", rows, [], ["/review queue"]).as_dict()
        if command == ("duplicates",):
            rows = self.repository.find_duplicates(case_id, options.get("type", "all"))
            return CommandResult(normalized, f"Found {len(rows)} potential local duplicates.", rows, [], ["/gaps"]).as_dict()
        if command == ("gaps",):
            rows = self.repository.find_gaps(case_id)
            return CommandResult(normalized, f"Found {len(rows)} local evidence gaps.", rows, [], ["/review queue", "/find posts --query <text>"]).as_dict()
        if command in {("agent", "status"), ("queue",)}:
            rows = self.repository.list_processing(case_id)
            return CommandResult(normalized, f"{len(rows)} local processing updates available.", rows, [], ["/review queue"]).as_dict()
        if command == ("history",):
            rows = self.repository.list_command_history(case_id, self._limit(options))
            return CommandResult(normalized, f"Loaded {len(rows)} local command history entries.", rows, [], ["/context"]).as_dict()
        if command in {("report", "generate"), ("export", "case")}:
            export_format = options.get("format", "pdf" if command == ("report", "generate") else "json")
            if export_format not in {"json", "pdf"}:
                raise ValueError("format must be json or pdf")
            url = f"/api/cases/{case_id}/export?format={export_format}"
            return CommandResult(normalized, f"{export_format.upper()} export is ready.", {"case_id": case_id, "format": export_format}, [{"label": f"Download {export_format.upper()}", "url": url}], ["/case status"]).as_dict()
        return CommandResult(
            normalized,
            "This catalog command is not enabled in the local executor.",
            {"reason": "Only local case-database operations are available. Platform capture, watches, alerts, sharing, and identity merging remain disabled."},
            [],
            ["/help", "/context"],
            "not_available",
        ).as_dict()

    def _case(self, case_id: int) -> dict[str, Any]:
        case = self.repository.get_case(case_id)
        if case is None:
            raise ValueError("case not found")
        return case

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.strip().replace("“", '"').replace("”", '"').split())

    @staticmethod
    def _tokens(raw_command: str) -> list[str]:
        try:
            return shlex.split(raw_command[1:])
        except ValueError as error:
            raise ValueError("invalid command quoting") from error

    @staticmethod
    def _split(tokens: list[str]) -> tuple[tuple[str, ...], list[str], dict[str, str]]:
        if not tokens:
            raise ValueError("command name is required")
        command_words = [tokens.pop(0).lower()]
        if command_words[0] in {"find", "source", "profile", "graph", "timeline", "case", "review", "agent", "report", "export", "confidence"}:
            if not tokens:
                raise ValueError("command action is required")
            command_words.append(tokens.pop(0).lower())
        positionals: list[str] = []
        options: dict[str, str] = {}
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.startswith("--"):
                key = token[2:].lower()
                if not key:
                    raise ValueError("invalid option")
                value = "true"
                if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                    value = tokens[index + 1]
                    index += 1
                options[key] = value
            else:
                positionals.append(token)
            index += 1
        return tuple(command_words), positionals, options

    @staticmethod
    def _normalized(command: tuple[str, ...], positionals: list[str], options: dict[str, str]) -> str:
        parts = [f"/{' '.join(command)}", *positionals]
        for key, value in options.items():
            parts.extend([f"--{key}", value])
        return " ".join(parts)

    @staticmethod
    def _case_id(options: dict[str, str], active_case_id: int | None) -> int:
        raw_case = options.get("case")
        if raw_case:
            match = re.search(r"(\d+)$", raw_case)
            if not match:
                raise ValueError("invalid case reference")
            return int(match.group(1))
        if active_case_id is None:
            raise ValueError("select a case or pass --case <id>")
        return active_case_id

    @staticmethod
    def _limit(options: dict[str, str]) -> int:
        return CommandEngine._bounded_int(options.get("limit"), 50, 1, 100)

    @staticmethod
    def _bounded_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
        try:
            result = int(value) if value is not None else default
        except ValueError:
            result = default
        return max(minimum, min(result, maximum))

    @staticmethod
    def _observation_links(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [{"label": f"Observation {row['id']}", "url": row["source_url"]} for row in rows if row.get("source_url")]

    @staticmethod
    def _edge_links(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [{"label": f"Evidence: {row['source_handle']} -> {row['target_handle']}", "url": row["evidence_url"]} for row in rows if row.get("evidence_url")]

    @staticmethod
    def _event_links(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        return [{"label": event["label"], "url": f"/api/observations/{event['observation_id']}"} for event in rows if event.get("observation_id")]
