from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Any

from src.analyzer import score_text
from src.agent_controller import AgentController
from src.assembly_manifest import module_name
from src.collector import Collector
from src.case_importer import CaseImporter
from src.database import DB_PATH, init_db, open_connection, utc_timestamp
from src.drafter import compose_draft
from src.evidence_integrity import EvidenceIntegrity
from src.identity_resolver import IdentityResolver
from src.profile_resolver import ProfileResolver
from src.relationship_engine import RelationshipEngine
from src.timeline_engine import TimelineEngine
from src.graph_viewer import GraphViewer
from src.pattern_engine import PatternEngine
from src.comment_anomaly import CommentAnomalyEngine
from src.ocr_engine import LocalOcrEngine
from src.evidence_vault import EvidenceVault


class Repository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        self.evidence_dir = self.db_path.parent / "evidence"
        self.vault_dir = self.db_path.parent / "vaults"
        init_db(self.db_path)
        self.collector = Collector()
        self.case_importer = CaseImporter()
        self.evidence_integrity = EvidenceIntegrity()
        self.pattern_engine = PatternEngine()
        self.profile_resolver = ProfileResolver()
        self.relationship_engine = RelationshipEngine()
        self.identity_resolver = IdentityResolver()
        self.timeline_engine = TimelineEngine()
        self.graph_viewer = GraphViewer()
        self.agent_controller = AgentController()
        self.comment_anomaly = CommentAnomalyEngine()
        self.ocr_engine = LocalOcrEngine()
        self.evidence_vault = EvidenceVault(self.vault_dir, self.db_path.parent / "vault_keys")
        self._ensure_default_case()
        self._backfill_legacy_evidence()
        self._backfill_legacy_fingerprints()

    def list_observations(self) -> list[dict[str, Any]]:
        query = """
        SELECT
            o.id,
            o.platform,
            o.content_type,
            o.source_url,
            o.captured_at,
            o.body,
            o.risk_level,
            o.danger_flags,
            o.status,
            a.handle AS actor_handle,
            a.display_name AS actor_display_name,
            d.body AS draft_body,
            d.tone AS draft_tone
        FROM observations o
        JOIN actors a ON a.id = o.actor_id
        LEFT JOIN drafts d ON d.observation_id = o.id
        ORDER BY o.captured_at DESC, o.id DESC
        """
        with open_connection(self.db_path) as connection:
            rows = connection.execute(query).fetchall()

        items = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "platform": row["platform"],
                    "content_type": row["content_type"],
                    "source_url": row["source_url"],
                    "captured_at": row["captured_at"],
                    "body": row["body"],
                    "risk_level": row["risk_level"],
                    "danger_flags": json.loads(row["danger_flags"]),
                    "status": row["status"],
                    "actor_handle": row["actor_handle"],
                    "actor_display_name": row["actor_display_name"],
                    "draft_body": row["draft_body"],
                    "draft_tone": row["draft_tone"],
                }
            )
        return items

    def get_observation(self, observation_id: int) -> dict[str, Any] | None:
        detail_query = """
        SELECT
            o.id,
            o.platform,
            o.content_type,
            o.source_url,
            o.captured_at,
            o.body,
            o.risk_level,
            o.danger_flags,
            o.status,
            a.id AS actor_id,
            a.handle AS actor_handle,
            a.display_name AS actor_display_name,
            a.platform AS actor_platform,
            a.risk_score AS actor_risk_score
        FROM observations o
        JOIN actors a ON a.id = o.actor_id
        WHERE o.id = ?
        """
        sources_query = """
        SELECT id, title, url, excerpt
        FROM sources
        WHERE observation_id = ?
        ORDER BY id ASC
        """
        relationships_query = """
        SELECT
            r.id,
            r.relation_type,
            r.weight,
            target.handle AS target_handle,
            target.platform AS target_platform,
            target.display_name AS target_display_name
        FROM relationships r
        JOIN actors target ON target.id = r.to_actor_id
        WHERE r.evidence_observation_id = ?
        ORDER BY r.weight DESC, target.handle ASC
        """
        draft_query = """
        SELECT tone, audience, body, citations, generated_at, state
        FROM drafts
        WHERE observation_id = ?
        """
        evidence_query = """
        SELECT id, kind, label, url, file_path, captured_at, annotation
        FROM evidence
        WHERE observation_id = ?
        ORDER BY captured_at DESC, id DESC
        """
        tags_query = """
        SELECT t.id, t.label, t.color
        FROM observation_tags ot
        JOIN tags t ON t.id = ot.tag_id
        WHERE ot.observation_id = ?
        ORDER BY t.label ASC
        """
        cases_query = """
        SELECT c.id, c.title, c.status
        FROM case_observations co
        JOIN cases c ON c.id = co.case_id
        WHERE co.observation_id = ?
        ORDER BY c.id ASC
        """

        with open_connection(self.db_path) as connection:
            row = connection.execute(detail_query, (observation_id,)).fetchone()
            if row is None:
                return None
            source_rows = connection.execute(sources_query, (observation_id,)).fetchall()
            relationship_rows = connection.execute(relationships_query, (observation_id,)).fetchall()
            draft_row = connection.execute(draft_query, (observation_id,)).fetchone()
            evidence_rows = connection.execute(evidence_query, (observation_id,)).fetchall()
            ocr_rows = connection.execute(
                """SELECT id, evidence_id, engine, model_profile, state, text, result_json, created_at
                   FROM ocr_runs WHERE evidence_id IN (
                       SELECT id FROM evidence WHERE observation_id = ?
                   ) ORDER BY id DESC""",
                (observation_id,),
            ).fetchall()
            tag_rows = connection.execute(tags_query, (observation_id,)).fetchall()
            case_rows = connection.execute(cases_query, (observation_id,)).fetchall()

        draft = None
        if draft_row:
            draft = {
                "tone": draft_row["tone"],
                "audience": draft_row["audience"],
                "body": draft_row["body"],
                "citations": json.loads(draft_row["citations"]),
                "generated_at": draft_row["generated_at"],
                "state": draft_row["state"],
            }

        return {
            "observation": {
                "id": row["id"],
                "platform": row["platform"],
                "content_type": row["content_type"],
                "source_url": row["source_url"],
                "captured_at": row["captured_at"],
                "body": row["body"],
                "risk_level": row["risk_level"],
                "danger_flags": json.loads(row["danger_flags"]),
                "status": row["status"],
            },
            "actor": {
                "id": row["actor_id"],
                "handle": row["actor_handle"],
                "display_name": row["actor_display_name"],
                "platform": row["actor_platform"],
                "risk_score": row["actor_risk_score"],
            },
            "sources": [
                {
                    "id": source["id"],
                    "title": source["title"],
                    "url": source["url"],
                    "excerpt": source["excerpt"],
                }
                for source in source_rows
            ],
            "relationships": [
                {
                    "id": relation["id"],
                    "relation_type": relation["relation_type"],
                    "weight": relation["weight"],
                    "target_handle": relation["target_handle"],
                    "target_platform": relation["target_platform"],
                    "target_display_name": relation["target_display_name"],
                }
                for relation in relationship_rows
            ],
            "evidence": [
                {
                    "id": evidence["id"],
                    "kind": evidence["kind"],
                    "label": evidence["label"],
                    "url": evidence["url"],
                    "file_path": evidence["file_path"],
                    "captured_at": evidence["captured_at"],
                    "annotation": evidence["annotation"],
                }
                for evidence in evidence_rows
            ],
            "ocr_runs": [
                {
                    **dict(run),
                    "result": json.loads(run["result_json"]),
                }
                for run in ocr_rows
            ],
            "tags": [dict(tag) for tag in tag_rows],
            "cases": [dict(case) for case in case_rows],
            "draft": draft,
        }

    def create_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        handle = self._require_text(payload.get("handle"), "handle")
        platform = self._clean_text(payload.get("platform")) or "instagram"
        body = self._require_text(payload.get("body"), "body")
        display_name = self._clean_text(payload.get("display_name"))
        content_type = self._clean_text(payload.get("content_type")) or "reel_comment"
        source_url = self._clean_text(payload.get("source_url"))
        captured_at = self._clean_text(payload.get("captured_at")) or utc_timestamp()
        cleaned_sources = self._clean_sources(payload.get("sources", []))
        cleaned_relationships = self._clean_relationships(payload.get("relationships", []), platform)
        requested_case_id = payload.get("case_id")
        signals = self.collector.collect(payload)

        analysis = score_text(body)

        with open_connection(self.db_path) as connection:
            case_id = self._resolve_case_id(connection, requested_case_id)
            actor_id = self._get_or_create_actor(connection, handle, platform, display_name)
            cursor = connection.execute(
                """
                INSERT INTO observations (
                    actor_id, platform, content_type, source_url, captured_at, body,
                    risk_level, danger_flags, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    actor_id,
                    platform,
                    content_type,
                    source_url,
                    captured_at,
                    body,
                    analysis.risk_level,
                    json.dumps(analysis.danger_flags),
                    utc_timestamp(),
                ),
            )
            observation_id = int(cursor.lastrowid)
            fingerprint = self.evidence_integrity.fingerprint_observation(
                {
                    "handle": handle,
                    "platform": platform,
                    "source_url": source_url,
                    "captured_at": captured_at,
                    "body": body,
                }
            )
            connection.execute(
                """INSERT INTO observation_fingerprints (observation_id, content_hash, context_hash, created_at)
                   VALUES (?, ?, ?, ?)""",
                (observation_id, fingerprint.content_hash, fingerprint.context_hash, utc_timestamp()),
            )
            connection.execute(
                "INSERT OR IGNORE INTO case_observations (case_id, observation_id, added_at) VALUES (?, ?, ?)",
                (case_id, observation_id, utc_timestamp()),
            )
            connection.execute(
                """
                INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                VALUES (?, ?, 'captured_content', ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    observation_id,
                    f"Captured {content_type}",
                    source_url,
                    captured_at,
                    "Original URL and capture time supplied by the analyst.",
                    utc_timestamp(),
                ),
            )

            for source in cleaned_sources:
                connection.execute(
                    """
                    INSERT INTO sources (observation_id, title, url, excerpt, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        source["title"],
                        source.get("url"),
                        source.get("excerpt"),
                        utc_timestamp(),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                    VALUES (?, ?, 'external_source', ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        observation_id,
                        source["title"],
                        source.get("url"),
                        captured_at,
                        source.get("excerpt", ""),
                        utc_timestamp(),
                    ),
                )

            for hashtag in signals.hashtags:
                self._tag_observation(connection, case_id, observation_id, hashtag, "amber")

            for link in signals.links:
                connection.execute(
                    """
                    INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                    VALUES (?, ?, 'shared_link', ?, ?, ?, ?, ?)
                    """,
                    (case_id, observation_id, "Link appearing in captured content", link, captured_at, "Extracted from the captured text.", utc_timestamp()),
                )

            for relationship in cleaned_relationships:
                target_id = self._get_or_create_actor(
                    connection,
                    relationship["handle"],
                    relationship["platform"],
                    relationship.get("display_name"),
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO relationships (
                        from_actor_id, to_actor_id, relation_type, weight,
                        evidence_observation_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        actor_id,
                        target_id,
                        relationship["relation_type"],
                        relationship["weight"],
                        observation_id,
                        utc_timestamp(),
                    ),
                )

            for finding in self.relationship_engine.from_signals(signals):
                if finding.relation_type != "mention" or finding.target == handle:
                    continue
                target_id = self._get_or_create_actor(connection, finding.target, platform, None)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO relationships (
                        from_actor_id, to_actor_id, relation_type, weight,
                        evidence_observation_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (actor_id, target_id, finding.relation_type, finding.confidence, observation_id, utc_timestamp()),
                )

            profile_changes = self._record_profile_snapshot(connection, case_id, actor_id, observation_id, payload, handle, display_name, captured_at)
            previous_handle = self._clean_text(payload.get("previous_handle"))
            if previous_handle and previous_handle != handle:
                previous_actor_id = self._get_or_create_actor(connection, previous_handle, platform, None)
                confidence = self._bounded_confidence(payload.get("account_switch_confidence"), 0.5)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO relationships (
                        from_actor_id, to_actor_id, relation_type, weight,
                        evidence_observation_id, created_at
                    ) VALUES (?, ?, 'possible_account_switch', ?, ?, ?)
                    """,
                    (previous_actor_id, actor_id, confidence, observation_id, utc_timestamp()),
                )
                profile_changes += 1

            self._refresh_actor_score(connection, actor_id)
            relationship_count = len(cleaned_relationships) + len(signals.mentions) + (1 if previous_handle else 0)
            for update in self.agent_controller.updates_for_observation(relationship_count, profile_changes):
                self._record_job(connection, case_id, update.stage, update.message, update.state, update.confidence, observation_id)
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))

        return self.get_observation(observation_id) or {}

    def create_draft(self, observation_id: int, tone: str = "firm") -> dict[str, Any] | None:
        detail = self.get_observation(observation_id)
        if detail is None:
            return None

        draft = compose_draft(detail["observation"], detail["sources"], tone=tone)

        with open_connection(self.db_path) as connection:
            observation_status = "drafted" if draft["state"] == "pending_review" else "draft_blocked"
            connection.execute(
                """
                INSERT INTO drafts (observation_id, tone, audience, body, citations, generated_at, state)
                VALUES (?, ?, 'public_comment', ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    tone = excluded.tone,
                    body = excluded.body,
                    citations = excluded.citations,
                    generated_at = excluded.generated_at,
                    state = excluded.state
                """,
                (
                    observation_id,
                    draft["tone"],
                    draft["body"],
                    json.dumps(draft["citations"]),
                    utc_timestamp(),
                    draft["state"],
                ),
            )
            connection.execute(
                "UPDATE observations SET status = ? WHERE id = ?",
                (observation_status, observation_id),
            )

        return self.get_observation(observation_id)

    def get_network(self) -> dict[str, Any]:
        actor_query = """
        SELECT
            a.id,
            a.handle,
            a.display_name,
            a.platform,
            a.risk_score,
            COUNT(DISTINCT o.id) AS observation_count
        FROM actors a
        LEFT JOIN observations o ON o.actor_id = a.id
        GROUP BY a.id
        ORDER BY a.risk_score DESC, observation_count DESC, a.handle ASC
        """
        edge_query = """
        SELECT
            r.id,
            source.handle AS source_handle,
            target.handle AS target_handle,
            r.relation_type,
            r.weight
        FROM relationships r
        JOIN actors source ON source.id = r.from_actor_id
        JOIN actors target ON target.id = r.to_actor_id
        ORDER BY r.weight DESC, r.id ASC
        """
        with open_connection(self.db_path) as connection:
            actor_rows = connection.execute(actor_query).fetchall()
            edge_rows = connection.execute(edge_query).fetchall()

        return {
            "actors": [
                {
                    "id": row["id"],
                    "handle": row["handle"],
                    "display_name": row["display_name"],
                    "platform": row["platform"],
                    "risk_score": row["risk_score"],
                    "observation_count": row["observation_count"],
                }
                for row in actor_rows
            ],
            "edges": [
                {
                    "id": row["id"],
                    "source_handle": row["source_handle"],
                    "target_handle": row["target_handle"],
                    "relation_type": row["relation_type"],
                    "weight": row["weight"],
                }
                for row in edge_rows
            ],
        }

    def seed_demo_data(self) -> dict[str, Any]:
        if self.list_observations():
            return {"seeded": False, "reason": "existing_data"}

        samples = [
            {
                "handle": "@sample_rhetoric_watch",
                "display_name": "Sample Rhetoric Watch",
                "platform": "instagram",
                "body": (
                    "Post frames minorities as an infestation, says history was fabricated, "
                    "and pushes people into a private chat."
                ),
                "source_url": "https://instagram.example/reel/alpha",
                "sources": [
                    {
                        "title": "USHMM Holocaust Encyclopedia",
                        "url": "https://encyclopedia.ushmm.org/",
                        "excerpt": "Historical denial narratives recycle falsehoods and erase documented evidence.",
                    },
                    {
                        "title": "Bundeszentrale fuer politische Bildung",
                        "url": "https://www.bpb.de/",
                        "excerpt": "Extremist rhetoric often combines dehumanization with recruitment into closed circles.",
                    },
                ],
                "relationships": [
                    {"handle": "@signal_booster_a", "relation_type": "co-mentioned", "weight": 0.7},
                    {"handle": "@signal_booster_b", "relation_type": "co-mentioned", "weight": 0.4},
                ],
            },
            {
                "handle": "@sample_network_node",
                "display_name": "Sample Network Node",
                "platform": "instagram",
                "body": (
                    "Clip praises strongman rule, frames critics as traitors, and suggests followers "
                    "move coordination into a private group."
                ),
                "source_url": "https://instagram.example/reel/beta",
                "sources": [
                    {
                        "title": "Institute for Strategic Dialogue",
                        "url": "https://www.isdglobal.org/",
                        "excerpt": "Authoritarian propaganda often blends grievance narratives with calls to closed-channel mobilization.",
                    }
                ],
                "relationships": [
                    {"handle": "@sample_rhetoric_watch", "relation_type": "cross-promotion", "weight": 0.6},
                ],
            },
        ]

        inserted = []
        for payload in samples:
            detail = self.create_observation(payload)
            inserted.append(detail["observation"]["id"])

        return {"seeded": True, "observation_ids": inserted}

    def list_cases(self) -> list[dict[str, Any]]:
        query = """
        SELECT c.id, c.title, c.description, c.status, c.created_at, c.updated_at,
               COUNT(DISTINCT co.observation_id) AS observation_count,
               COUNT(DISTINCT e.id) AS evidence_count
        FROM cases c
        LEFT JOIN case_observations co ON co.case_id = c.id
        LEFT JOIN evidence e ON e.case_id = c.id
        GROUP BY c.id
        ORDER BY c.updated_at DESC, c.id DESC
        """
        with open_connection(self.db_path) as connection:
            return [dict(row) for row in connection.execute(query).fetchall()]

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = self._require_text(payload.get("title"), "title")
        description = self._clean_text(payload.get("description"))
        timestamp = utc_timestamp()
        with open_connection(self.db_path) as connection:
            cursor = connection.execute(
                "INSERT INTO cases (title, description, status, created_at, updated_at) VALUES (?, ?, 'open', ?, ?)",
                (title, description, timestamp, timestamp),
            )
        return self.get_case(int(cursor.lastrowid)) or {}

    def get_case(self, case_id: int) -> dict[str, Any] | None:
        query = """
        SELECT c.id, c.title, c.description, c.status, c.created_at, c.updated_at,
               COUNT(DISTINCT co.observation_id) AS observation_count,
               COUNT(DISTINCT e.id) AS evidence_count,
               COUNT(DISTINCT r.id) AS relationship_count
        FROM cases c
        LEFT JOIN case_observations co ON co.case_id = c.id
        LEFT JOIN evidence e ON e.case_id = c.id
        LEFT JOIN relationships r ON r.evidence_observation_id = co.observation_id
        WHERE c.id = ?
        GROUP BY c.id
        """
        with open_connection(self.db_path) as connection:
            row = connection.execute(query, (case_id,)).fetchone()
            if row is None:
                return None
        return dict(row)

    def list_case_observations(self, case_id: int, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        clauses = ["co.case_id = ?"]
        values: list[Any] = [case_id]
        search = self._clean_text(filters.get("q"))
        if search:
            clauses.append("(LOWER(o.body) LIKE ? OR LOWER(a.handle) LIKE ? OR LOWER(COALESCE(a.display_name, '')) LIKE ?)")
            needle = f"%{search.lower()}%"
            values.extend([needle, needle, needle])
        minimum_risk = self._clean_text(filters.get("min_risk"))
        if minimum_risk.isdigit():
            clauses.append("o.risk_level >= ?")
            values.append(int(minimum_risk))
        tag = self._clean_text(filters.get("tag"))
        if tag:
            clauses.append("EXISTS (SELECT 1 FROM observation_tags ot JOIN tags t ON t.id = ot.tag_id WHERE ot.observation_id = o.id AND LOWER(t.label) = ?)")
            values.append(tag.lower())
        query = f"""
        SELECT o.id, o.platform, o.content_type, o.source_url, o.captured_at, o.body,
               o.risk_level, o.danger_flags, o.status, a.id AS actor_id,
               a.handle AS actor_handle, a.display_name AS actor_display_name,
               GROUP_CONCAT(DISTINCT t.label) AS tags
        FROM case_observations co
        JOIN observations o ON o.id = co.observation_id
        JOIN actors a ON a.id = o.actor_id
        LEFT JOIN observation_tags ot ON ot.observation_id = o.id
        LEFT JOIN tags t ON t.id = ot.tag_id
        WHERE {' AND '.join(clauses)}
        GROUP BY o.id
        ORDER BY o.captured_at DESC, o.id DESC
        """
        with open_connection(self.db_path) as connection:
            rows = connection.execute(query, values).fetchall()
        return [
            {
                **dict(row),
                "danger_flags": json.loads(row["danger_flags"]),
                "tags": row["tags"].split(",") if row["tags"] else [],
            }
            for row in rows
        ]

    def get_case_timeline(self, case_id: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with open_connection(self.db_path) as connection:
            observation_rows = connection.execute(
                """SELECT o.id, o.captured_at, o.content_type, o.body, a.handle
                   FROM case_observations co JOIN observations o ON o.id = co.observation_id
                   JOIN actors a ON a.id = o.actor_id WHERE co.case_id = ?""",
                (case_id,),
            ).fetchall()
            evidence_rows = connection.execute(
                "SELECT id, captured_at, kind, label, observation_id FROM evidence WHERE case_id = ?",
                (case_id,),
            ).fetchall()
            profile_rows = connection.execute(
                "SELECT ps.id, ps.captured_at, ps.handle, ps.actor_id FROM profile_snapshots ps WHERE ps.case_id = ?",
                (case_id,),
            ).fetchall()
            note_rows = connection.execute(
                "SELECT id, created_at, body, observation_id FROM case_notes WHERE case_id = ?",
                (case_id,),
            ).fetchall()
        events.extend({"id": row["id"], "timestamp": row["captured_at"], "kind": "observation", "label": f"{row['handle']} · {row['content_type']}", "detail": row["body"], "observation_id": row["id"]} for row in observation_rows)
        events.extend({"id": row["id"], "timestamp": row["captured_at"], "kind": row["kind"], "label": row["label"], "detail": "Evidence item", "observation_id": row["observation_id"]} for row in evidence_rows)
        events.extend({"id": row["id"], "timestamp": row["captured_at"], "kind": "profile_snapshot", "label": f"Profile snapshot: {row['handle']}", "detail": "Recorded profile state", "actor_id": row["actor_id"]} for row in profile_rows)
        events.extend({"id": row["id"], "timestamp": row["created_at"], "kind": "note", "label": "Analyst note", "detail": row["body"], "observation_id": row["observation_id"]} for row in note_rows)
        return self.timeline_engine.merge(events)

    def get_case_graph(self, case_id: int) -> dict[str, Any]:
        node_query = """
        SELECT a.id, a.handle, a.display_name, a.platform, a.risk_score,
               COUNT(DISTINCT observed_case.observation_id) AS observation_count
        FROM actors a
        LEFT JOIN observations observed ON observed.actor_id = a.id
        LEFT JOIN case_observations observed_case ON observed_case.observation_id = observed.id AND observed_case.case_id = ?
        WHERE EXISTS (
            SELECT 1 FROM observations o
            JOIN case_observations co ON co.observation_id = o.id
            WHERE co.case_id = ? AND o.actor_id = a.id
        ) OR EXISTS (
            SELECT 1 FROM relationships r
            JOIN case_observations co ON co.observation_id = r.evidence_observation_id
            WHERE co.case_id = ? AND (r.from_actor_id = a.id OR r.to_actor_id = a.id)
        )
        GROUP BY a.id
        """
        edge_query = """
        SELECT r.id, r.from_actor_id AS source_id, r.to_actor_id AS target_id,
               source.handle AS source_handle, target.handle AS target_handle,
               r.relation_type, r.weight AS confidence, r.evidence_observation_id,
               o.source_url AS evidence_url, o.captured_at AS evidence_timestamp
        FROM relationships r
        JOIN case_observations co ON co.observation_id = r.evidence_observation_id
        JOIN actors source ON source.id = r.from_actor_id
        JOIN actors target ON target.id = r.to_actor_id
        JOIN observations o ON o.id = r.evidence_observation_id
        WHERE co.case_id = ?
        ORDER BY confidence DESC, r.id ASC
        """
        with open_connection(self.db_path) as connection:
            nodes = [dict(row) for row in connection.execute(node_query, (case_id, case_id, case_id)).fetchall()]
            edges = [dict(row) for row in connection.execute(edge_query, (case_id,)).fetchall()]
        return self.graph_viewer.enrich(nodes, edges)

    def get_case_profiles(self, case_id: int) -> list[dict[str, Any]]:
        query = """
        SELECT a.id, a.handle, a.display_name, a.platform, a.risk_score,
               COUNT(DISTINCT observed_case.observation_id) AS observation_count,
               COUNT(DISTINCT ic.id) AS identity_claim_count,
               COUNT(DISTINCT ps.id) AS snapshot_count
        FROM actors a
        LEFT JOIN observations observed ON observed.actor_id = a.id
        LEFT JOIN case_observations observed_case ON observed_case.observation_id = observed.id AND observed_case.case_id = ?
        LEFT JOIN identity_claims ic ON ic.actor_id = a.id AND ic.case_id = ?
        LEFT JOIN profile_snapshots ps ON ps.actor_id = a.id AND ps.case_id = ?
        WHERE EXISTS (
            SELECT 1 FROM observations o
            JOIN case_observations co ON co.observation_id = o.id
            WHERE co.case_id = ? AND o.actor_id = a.id
        ) OR EXISTS (
            SELECT 1 FROM relationships r
            JOIN case_observations co ON co.observation_id = r.evidence_observation_id
            WHERE co.case_id = ? AND (r.from_actor_id = a.id OR r.to_actor_id = a.id)
        )
        GROUP BY a.id
        ORDER BY observation_count DESC, a.risk_score DESC, a.handle ASC
        """
        with open_connection(self.db_path) as connection:
            rows = connection.execute(query, (case_id, case_id, case_id, case_id, case_id)).fetchall()
        return [dict(row) for row in rows]

    def add_note(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        body = self._require_text(payload.get("body"), "body")
        observation_id = payload.get("observation_id") or None
        actor_id = payload.get("actor_id") or None
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            cursor = connection.execute(
                "INSERT INTO case_notes (case_id, observation_id, actor_id, body, created_at) VALUES (?, ?, ?, ?, ?)",
                (case_id, observation_id, actor_id, body, utc_timestamp()),
            )
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))
        return {"id": int(cursor.lastrowid), "body": body}

    def add_identity_claim(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        actor_id = int(payload.get("actor_id", 0))
        evidence_observation_id = payload.get("evidence_observation_id") or None
        claim = self.identity_resolver.validate(
            str(payload.get("candidate_label", "")),
            str(payload.get("basis", "")),
            self._bounded_confidence(payload.get("confidence"), 0.5),
            self._clean_text(payload.get("state")) or "unverified",
        )
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            actor = connection.execute("SELECT id FROM actors WHERE id = ?", (actor_id,)).fetchone()
            if actor is None:
                raise ValueError("actor not found")
            cursor = connection.execute(
                """INSERT INTO identity_claims (case_id, actor_id, candidate_label, basis, confidence, state, evidence_observation_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (case_id, actor_id, claim.candidate_label, claim.basis, claim.confidence, claim.state, evidence_observation_id, utc_timestamp()),
            )
        return {"id": int(cursor.lastrowid), **claim.__dict__}

    def add_screenshot(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        label = self._require_text(payload.get("label"), "label")
        observation_id = payload.get("observation_id") or None
        url = self._clean_text(payload.get("url"))
        annotation = self._clean_text(payload.get("annotation"))
        if not url:
            raise ValueError("url is required for a screenshot reference")
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            cursor = connection.execute(
                """INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                   VALUES (?, ?, 'screenshot_reference', ?, ?, ?, ?, ?)""",
                (case_id, observation_id, label, url, utc_timestamp(), annotation, utc_timestamp()),
            )
        return {"id": int(cursor.lastrowid), "label": label, "url": url, "annotation": annotation}

    def add_local_image(self, case_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        label = self._require_text(payload.get("label"), "label")
        observation_id = payload.get("observation_id") or None
        encoded = self._require_text(payload.get("content_base64"), "content_base64")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("content_base64 must be valid base64") from error
        if not content or len(content) > 8 * 1024 * 1024:
            raise ValueError("local image evidence is limited to 8 MB")
        suffix = self._image_suffix(content)
        if suffix is None:
            raise ValueError("only JPEG, PNG, GIF and WebP image evidence is accepted")

        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            if observation_id is not None:
                linked = connection.execute(
                    "SELECT 1 FROM case_observations WHERE case_id = ? AND observation_id = ?",
                    (case_id, observation_id),
                ).fetchone()
                if linked is None:
                    raise ValueError("observation not found in case")

        relative_path = Path("evidence") / f"case-{case_id}" / f"{hashlib.sha256(content).hexdigest()}{suffix}"
        target_path = self.db_path.parent / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            target_path.write_bytes(content)

        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            cursor = connection.execute(
                """INSERT INTO evidence (case_id, observation_id, kind, label, file_path, captured_at, annotation, created_at)
                   VALUES (?, ?, 'local_image', ?, ?, ?, 'Explicit local image evidence; OCR is opt-in.', ?)""",
                (case_id, observation_id, label, str(relative_path), utc_timestamp(), utc_timestamp()),
            )
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))
        return {"id": int(cursor.lastrowid), "label": label, "file_path": str(relative_path), "kind": "local_image"}

    def get_model_status(self) -> list[dict[str, Any]]:
        return [self.comment_anomaly.status(), self.ocr_engine.status()]

    def get_comment_anomalies(self, case_id: int) -> dict[str, Any]:
        if self.get_case(case_id) is None:
            raise ValueError("case not found")
        return self.comment_anomaly.analyze(self.list_case_observations(case_id))

    def run_ocr(self, case_id: int, evidence_id: int, confirmed: bool = False, language: str = "en") -> dict[str, Any]:
        if not confirmed:
            return {
                "state": "confirmation_required",
                "message": "The first run may download local PaddleOCR model files. Confirmation is required.",
            }
        with open_connection(self.db_path) as connection:
            evidence = connection.execute(
                "SELECT id, file_path FROM evidence WHERE id = ? AND case_id = ? AND kind = 'local_image'",
                (evidence_id, case_id),
            ).fetchone()
            if evidence is None:
                raise ValueError("local image evidence not found in case")
        image_path = self._resolve_evidence_path(str(evidence["file_path"] or ""))
        if image_path is None or not image_path.exists():
            raise ValueError("local image evidence file is unavailable")

        result = self.ocr_engine.extract(image_path, language=language)
        with open_connection(self.db_path) as connection:
            cursor = connection.execute(
                """INSERT INTO ocr_runs (case_id, evidence_id, engine, model_profile, state, text, result_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id,
                    evidence_id,
                    result["engine"],
                    result["profile"],
                    result["state"],
                    result.get("text", ""),
                    json.dumps(result, ensure_ascii=False),
                    utc_timestamp(),
                ),
            )
            self._record_job(
                connection,
                case_id,
                module_name("ocr_engine"),
                result["message"],
                result["state"],
                None,
                None,
            )
        return {"id": int(cursor.lastrowid), "evidence_id": evidence_id, **result}

    def get_vault_status(self) -> dict[str, str]:
        return self.evidence_vault.status()

    def create_evidence_vault(self, case_id: int, passphrase: str, operator: str) -> dict[str, Any]:
        report = self.export_case(case_id)
        if report is None:
            raise ValueError("case not found")
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                "SELECT id, file_path FROM evidence WHERE case_id = ? AND TRIM(COALESCE(file_path, '')) <> ''",
                (case_id,),
            ).fetchall()
        evidence_files = []
        for row in rows:
            path = self._resolve_evidence_path(str(row["file_path"]))
            if path is not None:
                evidence_files.append({"path": path, "archive_name": f"evidence/{row['id']}-{path.name}"})
        artifact = self.evidence_vault.create(case_id, report, evidence_files, passphrase, operator)
        relative_path = artifact["path"].relative_to(self.db_path.parent)
        with open_connection(self.db_path) as connection:
            cursor = connection.execute(
                """INSERT INTO vault_exports (case_id, filename, file_path, operator, manifest_json, ciphertext_sha256, state, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'created', ?)""",
                (
                    case_id,
                    artifact["filename"],
                    str(relative_path),
                    operator,
                    json.dumps(artifact["manifest"], ensure_ascii=False),
                    artifact["ciphertext_sha256"],
                    utc_timestamp(),
                ),
            )
            self._record_job(
                connection,
                case_id,
                module_name("evidence_vault"),
                f"Created signed encrypted vault with {artifact['file_count']} files.",
                "completed",
                None,
                None,
            )
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))
        return {"id": int(cursor.lastrowid), "filename": artifact["filename"], "file_count": artifact["file_count"], "state": "created"}

    def list_vault_exports(self, case_id: int) -> list[dict[str, Any]]:
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                """SELECT id, filename, operator, ciphertext_sha256, state, created_at, verified_at
                   FROM vault_exports WHERE case_id = ? ORDER BY id DESC""",
                (case_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def verify_evidence_vault(self, vault_id: int) -> dict[str, Any]:
        with open_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT id, case_id, file_path FROM vault_exports WHERE id = ?",
                (vault_id,),
            ).fetchone()
            if row is None:
                raise ValueError("vault export not found")
        path = self._resolve_vault_path(str(row["file_path"]))
        if path is None:
            raise ValueError("vault export path is invalid")
        try:
            result = self.evidence_vault.verify(path)
            state = "verified"
        except ValueError as error:
            result = {"state": "invalid", "message": str(error)}
            state = "invalid"
        with open_connection(self.db_path) as connection:
            connection.execute(
                "UPDATE vault_exports SET state = ?, verified_at = ? WHERE id = ?",
                (state, utc_timestamp(), vault_id),
            )
        return {"id": vault_id, **result}

    def read_evidence_vault(self, vault_id: int) -> tuple[str, bytes] | None:
        with open_connection(self.db_path) as connection:
            row = connection.execute("SELECT filename, file_path FROM vault_exports WHERE id = ?", (vault_id,)).fetchone()
        if row is None:
            return None
        path = self._resolve_vault_path(str(row["file_path"]))
        if path is None or not path.exists():
            return None
        return str(row["filename"]), path.read_bytes()

    def list_processing(self, case_id: int) -> list[dict[str, Any]]:
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                """SELECT id, stage, message, state, confidence, related_observation_id, created_at
                   FROM processing_jobs WHERE case_id = ? ORDER BY id DESC LIMIT 30""",
                (case_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_profile_detail(self, case_id: int, handle: str) -> dict[str, Any] | None:
        normalized = self.profile_resolver.normalize_handle(handle)
        with open_connection(self.db_path) as connection:
            actor = connection.execute(
                """
                SELECT a.id, a.handle, a.display_name, a.platform, a.risk_score
                FROM actors a
                WHERE LOWER(a.handle) = LOWER(?) AND EXISTS (
                    SELECT 1 FROM observations o
                    JOIN case_observations co ON co.observation_id = o.id
                    WHERE co.case_id = ? AND o.actor_id = a.id
                )
                """,
                (normalized, case_id),
            ).fetchone()
            if actor is None:
                return None
            snapshots = [dict(row) for row in connection.execute(
                """SELECT id, handle, display_name, bio, profile_url, captured_at, evidence_observation_id
                   FROM profile_snapshots WHERE case_id = ? AND actor_id = ? ORDER BY captured_at DESC, id DESC""",
                (case_id, actor["id"]),
            ).fetchall()]
            claims = [dict(row) for row in connection.execute(
                """SELECT id, candidate_label, basis, confidence, state, evidence_observation_id, created_at
                   FROM identity_claims WHERE case_id = ? AND actor_id = ? ORDER BY id DESC""",
                (case_id, actor["id"]),
            ).fetchall()]
        graph = self.get_case_graph(case_id)
        connections = [edge for edge in graph["edges"] if edge["source_id"] == actor["id"] or edge["target_id"] == actor["id"]]
        return {"profile": dict(actor), "snapshots": snapshots, "identity_hypotheses": claims, "connections": connections}

    def find_mentions(self, case_id: int, handle: str) -> list[dict[str, Any]]:
        normalized = self.profile_resolver.normalize_handle(handle)
        query = """
        SELECT r.id, source.handle AS source_handle, target.handle AS target_handle, r.weight AS confidence,
               o.id AS observation_id, o.source_url, o.captured_at
        FROM relationships r
        JOIN actors source ON source.id = r.from_actor_id
        JOIN actors target ON target.id = r.to_actor_id
        JOIN observations o ON o.id = r.evidence_observation_id
        JOIN case_observations co ON co.observation_id = o.id
        WHERE co.case_id = ? AND r.relation_type = 'mention'
          AND (LOWER(source.handle) = LOWER(?) OR LOWER(target.handle) = LOWER(?))
        ORDER BY o.captured_at DESC
        """
        with open_connection(self.db_path) as connection:
            return [dict(row) for row in connection.execute(query, (case_id, normalized, normalized)).fetchall()]

    def find_links(self, case_id: int, domain: str = "") -> list[dict[str, Any]]:
        domain = self._clean_text(domain).lower()
        with open_connection(self.db_path) as connection:
            rows = [dict(row) for row in connection.execute(
                """SELECT id, observation_id, label, url, captured_at, annotation
                   FROM evidence WHERE case_id = ? AND kind = 'shared_link' ORDER BY captured_at DESC""",
                (case_id,),
            ).fetchall()]
        if not domain:
            return rows
        return [row for row in rows if domain in str(row.get("url", "")).lower()]

    def add_case_source(self, case_id: int, url: str, label: str = "Manually added source") -> dict[str, Any]:
        clean_url = self._require_text(url, "url")
        clean_label = self._clean_text(label) or "Manually added source"
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            cursor = connection.execute(
                """INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                   VALUES (?, NULL, 'external_source', ?, ?, ?, 'Added through local command console.', ?)""",
                (case_id, clean_label, clean_url, utc_timestamp(), utc_timestamp()),
            )
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))
        return {"id": int(cursor.lastrowid), "label": clean_label, "url": clean_url}

    def add_case_tag(self, case_id: int, label: str, color: str = "amber") -> dict[str, Any]:
        clean_label = self._require_text(label, "tag")
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            connection.execute(
                "INSERT OR IGNORE INTO tags (case_id, label, color, created_at) VALUES (?, ?, ?, ?)",
                (case_id, clean_label, color, utc_timestamp()),
            )
            row = connection.execute("SELECT id, label, color FROM tags WHERE case_id = ? AND label = ?", (case_id, clean_label)).fetchone()
            connection.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (utc_timestamp(), case_id))
        return dict(row)

    def get_review_queue(self, case_id: int) -> list[dict[str, Any]]:
        with open_connection(self.db_path) as connection:
            claims = [dict(row) for row in connection.execute(
                """SELECT 'identity_hypothesis' AS kind, ic.id, a.handle AS subject, ic.basis AS detail,
                          ic.confidence, ic.evidence_observation_id AS observation_id
                   FROM identity_claims ic JOIN actors a ON a.id = ic.actor_id
                   WHERE ic.case_id = ? AND ic.state = 'unverified'""",
                (case_id,),
            ).fetchall()]
            profile_changes = [dict(row) for row in connection.execute(
                """SELECT 'profile_change' AS kind, id, '' AS subject, message AS detail,
                          confidence, related_observation_id AS observation_id
                   FROM processing_jobs WHERE case_id = ? AND state = 'review_needed'""",
                (case_id,),
            ).fetchall()]
        return claims + profile_changes

    def get_profile_activity(self, case_id: int, handle: str) -> list[dict[str, Any]]:
        normalized = self.profile_resolver.normalize_handle(handle)
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                """SELECT substr(o.captured_at, 1, 10) AS day, COUNT(*) AS observation_count
                   FROM observations o JOIN actors a ON a.id = o.actor_id
                   JOIN case_observations co ON co.observation_id = o.id
                   WHERE co.case_id = ? AND LOWER(a.handle) = LOWER(?)
                   GROUP BY day ORDER BY day DESC""",
                (case_id, normalized),
            ).fetchall()
        return [dict(row) for row in rows]

    def compare_profiles(self, case_id: int, first_handle: str, second_handle: str) -> dict[str, Any] | None:
        first = self.get_profile_detail(case_id, first_handle)
        second = self.get_profile_detail(case_id, second_handle)
        if first is None or second is None:
            return None
        first_neighbors = {edge["target_handle"] if edge["source_id"] == first["profile"]["id"] else edge["source_handle"] for edge in first["connections"]}
        second_neighbors = {edge["target_handle"] if edge["source_id"] == second["profile"]["id"] else edge["source_handle"] for edge in second["connections"]}
        return {
            "first": first["profile"],
            "second": second["profile"],
            "same_platform": first["profile"]["platform"] == second["profile"]["platform"],
            "shared_connections": sorted(first_neighbors & second_neighbors),
            "first_only_connections": sorted(first_neighbors - second_neighbors),
            "second_only_connections": sorted(second_neighbors - first_neighbors),
        }

    def get_profile_aliases(self, case_id: int, handle: str) -> list[dict[str, Any]]:
        normalized = self.profile_resolver.normalize_handle(handle)
        query = """
        SELECT source.handle AS previous_handle, target.handle AS current_handle,
               r.weight AS confidence, r.evidence_observation_id, o.source_url, o.captured_at
        FROM relationships r
        JOIN actors source ON source.id = r.from_actor_id
        JOIN actors target ON target.id = r.to_actor_id
        JOIN observations o ON o.id = r.evidence_observation_id
        JOIN case_observations co ON co.observation_id = o.id
        WHERE co.case_id = ? AND r.relation_type = 'possible_account_switch'
          AND (LOWER(source.handle) = LOWER(?) OR LOWER(target.handle) = LOWER(?))
        ORDER BY o.captured_at DESC
        """
        with open_connection(self.db_path) as connection:
            return [dict(row) for row in connection.execute(query, (case_id, normalized, normalized)).fetchall()]

    def get_common_connections(self, case_id: int, first_handle: str, second_handle: str) -> list[str]:
        comparison = self.compare_profiles(case_id, first_handle, second_handle)
        if comparison is None:
            return []
        return comparison["shared_connections"]

    def get_timeline_compare(self, case_id: int, handles: list[str]) -> list[dict[str, Any]]:
        normalized = [self.profile_resolver.normalize_handle(handle).lower() for handle in handles]
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        query = f"""
        SELECT o.id, o.captured_at AS timestamp, a.handle, o.content_type, o.source_url, o.body
        FROM observations o JOIN actors a ON a.id = o.actor_id
        JOIN case_observations co ON co.observation_id = o.id
        WHERE co.case_id = ? AND LOWER(a.handle) IN ({placeholders})
        ORDER BY o.captured_at DESC
        """
        with open_connection(self.db_path) as connection:
            rows = connection.execute(query, [case_id, *normalized]).fetchall()
        return [dict(row) for row in rows]

    def find_contradictions(self, case_id: int) -> list[dict[str, Any]]:
        query = """
        SELECT a.handle, 'profile_snapshot_conflict' AS kind,
               COUNT(DISTINCT COALESCE(ps.display_name, '')) AS distinct_display_names,
               COUNT(DISTINCT COALESCE(ps.bio, '')) AS distinct_bios
        FROM profile_snapshots ps JOIN actors a ON a.id = ps.actor_id
        WHERE ps.case_id = ?
        GROUP BY ps.actor_id
        HAVING COUNT(DISTINCT COALESCE(ps.display_name, '')) > 1
            OR COUNT(DISTINCT COALESCE(ps.bio, '')) > 1
        """
        with open_connection(self.db_path) as connection:
            return [dict(row) for row in connection.execute(query, (case_id,)).fetchall()]

    def find_duplicates(self, case_id: int, duplicate_type: str = "all") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with open_connection(self.db_path) as connection:
            if duplicate_type in {"all", "profile"}:
                results.extend(dict(row) for row in connection.execute(
                    """SELECT 'profile_display_name' AS kind, a.display_name AS value, COUNT(*) AS count,
                              GROUP_CONCAT(a.handle) AS members
                       FROM actors a JOIN observations o ON o.actor_id = a.id
                       JOIN case_observations co ON co.observation_id = o.id
                       WHERE co.case_id = ? AND TRIM(COALESCE(a.display_name, '')) <> ''
                       GROUP BY LOWER(a.display_name) HAVING COUNT(DISTINCT a.id) > 1""",
                    (case_id,),
                ).fetchall())
            if duplicate_type in {"all", "source", "link"}:
                results.extend(dict(row) for row in connection.execute(
                    """SELECT 'evidence_url' AS kind, url AS value, COUNT(*) AS count,
                              GROUP_CONCAT(id) AS members
                       FROM evidence WHERE case_id = ? AND TRIM(COALESCE(url, '')) <> ''
                       GROUP BY url HAVING COUNT(*) > 1""",
                    (case_id,),
                ).fetchall())
        return results

    def find_gaps(self, case_id: int) -> list[dict[str, Any]]:
        with open_connection(self.db_path) as connection:
            missing_urls = connection.execute(
                """SELECT COUNT(*) AS count FROM observations o JOIN case_observations co ON co.observation_id = o.id
                   WHERE co.case_id = ? AND TRIM(COALESCE(o.source_url, '')) = ''""",
                (case_id,),
            ).fetchone()["count"]
            missing_sources = connection.execute(
                """SELECT COUNT(*) AS count FROM observations o JOIN case_observations co ON co.observation_id = o.id
                   WHERE co.case_id = ? AND NOT EXISTS (
                       SELECT 1 FROM sources s WHERE s.observation_id = o.id
                   )""",
                (case_id,),
            ).fetchone()["count"]
            unreviewed = connection.execute(
                "SELECT COUNT(*) AS count FROM identity_claims WHERE case_id = ? AND state = 'unverified'",
                (case_id,),
            ).fetchone()["count"]
        candidates = [
            ("missing_original_url", missing_urls, "Observations without an original URL."),
            ("missing_context_source", missing_sources, "Observations without a linked context source."),
            ("unreviewed_identity_hypothesis", unreviewed, "Identity hypotheses awaiting review."),
        ]
        return [{"kind": kind, "count": count, "detail": detail} for kind, count, detail in candidates if count]

    def set_relationship_confidence(self, case_id: int, relationship_id: int, confidence: float, note: str = "") -> dict[str, Any]:
        confidence = self._bounded_confidence(confidence, 0.5)
        with open_connection(self.db_path) as connection:
            row = connection.execute(
                """SELECT r.id FROM relationships r JOIN case_observations co ON co.observation_id = r.evidence_observation_id
                   WHERE r.id = ? AND co.case_id = ?""",
                (relationship_id, case_id),
            ).fetchone()
            if row is None:
                raise ValueError("relationship not found in case")
            connection.execute("UPDATE relationships SET weight = ? WHERE id = ?", (confidence, relationship_id))
            self._record_job(connection, case_id, "Review", f"Relationship {relationship_id} confidence set to {confidence:.2f}. {note}".strip(), "reviewed", confidence, None)
        return {"relationship_id": relationship_id, "confidence": confidence}

    def review_identity_claim(self, case_id: int, claim_id: int, state: str, note: str = "") -> dict[str, Any]:
        if state not in {"reviewed", "rejected"}:
            raise ValueError("review state must be reviewed or rejected")
        with open_connection(self.db_path) as connection:
            row = connection.execute("SELECT id FROM identity_claims WHERE id = ? AND case_id = ?", (claim_id, case_id)).fetchone()
            if row is None:
                raise ValueError("identity claim not found in case")
            connection.execute("UPDATE identity_claims SET state = ? WHERE id = ?", (state, claim_id))
            self._record_job(connection, case_id, "Review", f"Identity claim {claim_id} marked {state}. {note}".strip(), state, None, None)
        return {"claim_id": claim_id, "state": state}

    def record_command(self, case_id: int | None, command_text: str, state: str, summary: str) -> None:
        with open_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO command_history (case_id, command_text, state, summary, executed_at) VALUES (?, ?, ?, ?, ?)",
                (case_id, command_text, state, summary, utc_timestamp()),
            )

    def list_command_history(self, case_id: int | None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT id, case_id, command_text, state, summary, executed_at FROM command_history"
        values: list[Any] = []
        if case_id is not None:
            query += " WHERE case_id = ?"
            values.append(case_id)
        query += " ORDER BY id DESC LIMIT ?"
        values.append(max(1, min(limit, 100)))
        with open_connection(self.db_path) as connection:
            return [dict(row) for row in connection.execute(query, values).fetchall()]

    def import_case_payload(self, case_id: int, payload: Any) -> dict[str, Any]:
        preview = self.case_importer.preview(payload)
        created_ids: list[int] = []
        for item in preview.accepted:
            detail = self.create_observation({**item, "case_id": case_id})
            created_ids.append(detail["observation"]["id"])
        label = self._clean_text(payload.get("label")) if isinstance(payload, dict) else "JSON import"
        with open_connection(self.db_path) as connection:
            self._require_case(connection, case_id)
            connection.execute(
                """INSERT INTO import_batches (case_id, label, source_kind, payload_hash, accepted_count, rejected_count, created_at)
                   VALUES (?, ?, 'manual_json', ?, ?, ?, ?)""",
                (
                    case_id,
                    label or "JSON import",
                    self.evidence_integrity.payload_hash(payload),
                    len(preview.accepted),
                    len(preview.rejected),
                    utc_timestamp(),
                ),
            )
            self._record_job(connection, case_id, module_name("case_importer"), f"Imported {len(created_ids)} validated JSON items.", "completed", None, None)
        return {**preview.as_dict(), "created_observation_ids": created_ids}

    def list_import_batches(self, case_id: int) -> list[dict[str, Any]]:
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                """SELECT id, label, source_kind, accepted_count, rejected_count, created_at
                   FROM import_batches WHERE case_id = ? ORDER BY id DESC LIMIT 20""",
                (case_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_case_findings(self, case_id: int) -> list[dict[str, Any]]:
        observations = self.list_case_observations(case_id)
        tag_query = """
        SELECT t.label, o.id AS observation_id, a.handle AS actor_handle
        FROM observation_tags ot JOIN tags t ON t.id = ot.tag_id
        JOIN observations o ON o.id = ot.observation_id
        JOIN actors a ON a.id = o.actor_id
        JOIN case_observations co ON co.observation_id = o.id
        WHERE co.case_id = ? AND t.label LIKE '#%'
        """
        link_query = """
        SELECT e.id, e.observation_id, e.url, e.captured_at, a.handle AS actor_handle
        FROM evidence e JOIN observations o ON o.id = e.observation_id
        JOIN actors a ON a.id = o.actor_id
        WHERE e.case_id = ? AND e.kind = 'shared_link'
        """
        fingerprint_query = """
        SELECT fp.content_hash, o.id AS observation_id, a.handle AS actor_handle
        FROM observation_fingerprints fp JOIN observations o ON o.id = fp.observation_id
        JOIN actors a ON a.id = o.actor_id
        JOIN case_observations co ON co.observation_id = o.id
        WHERE co.case_id = ?
        """
        with open_connection(self.db_path) as connection:
            tags = [dict(row) for row in connection.execute(tag_query, (case_id,)).fetchall()]
            links = [dict(row) for row in connection.execute(link_query, (case_id,)).fetchall()]
            fingerprints = [dict(row) for row in connection.execute(fingerprint_query, (case_id,)).fetchall()]
        return self.pattern_engine.findings(observations, tags, links, fingerprints, self.get_case_graph(case_id))

    def export_case(self, case_id: int) -> dict[str, Any] | None:
        case = self.get_case(case_id)
        if case is None:
            return None
        observations = self.list_case_observations(case_id)
        timeline = self.get_case_timeline(case_id)
        graph = self.get_case_graph(case_id)
        profiles = self.get_case_profiles(case_id)
        with open_connection(self.db_path) as connection:
            evidence = [dict(row) for row in connection.execute(
                "SELECT id, observation_id, kind, label, url, file_path, captured_at, annotation FROM evidence WHERE case_id = ? ORDER BY captured_at DESC, id DESC",
                (case_id,),
            ).fetchall()]
            notes = [dict(row) for row in connection.execute(
                "SELECT id, observation_id, actor_id, body, created_at FROM case_notes WHERE case_id = ? ORDER BY created_at DESC",
                (case_id,),
            ).fetchall()]
            claims = [dict(row) for row in connection.execute(
                """SELECT ic.id, ic.actor_id, a.handle, ic.candidate_label, ic.basis, ic.confidence, ic.state,
                          ic.evidence_observation_id, ic.created_at
                   FROM identity_claims ic JOIN actors a ON a.id = ic.actor_id WHERE ic.case_id = ?""",
                (case_id,),
            ).fetchall()]
            ocr_runs = [
                {**dict(row), "result": json.loads(row["result_json"])}
                for row in connection.execute(
                    """SELECT id, evidence_id, engine, model_profile, state, text, result_json, created_at
                       FROM ocr_runs WHERE case_id = ? ORDER BY id DESC""",
                    (case_id,),
                ).fetchall()
            ]
        return {
            "export_version": "1.0",
            "generated_at": utc_timestamp(),
            "case": case,
            "profiles": profiles,
            "identity_hypotheses": claims,
            "observations": observations,
            "relationships": graph["edges"],
            "groups": graph["groups"],
            "timeline": timeline,
            "evidence": evidence,
            "ocr_runs": ocr_runs,
            "notes": notes,
        }

    @staticmethod
    def _image_suffix(content: bytes) -> str | None:
        if content.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return ".webp"
        return None

    def _resolve_evidence_path(self, file_path: str) -> Path | None:
        if not file_path:
            return None
        root = self.evidence_dir.resolve()
        candidate = (self.db_path.parent / file_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _resolve_vault_path(self, file_path: str) -> Path | None:
        if not file_path:
            return None
        root = self.vault_dir.resolve()
        candidate = (self.db_path.parent / file_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).strip().split())

    def _ensure_default_case(self) -> None:
        with open_connection(self.db_path) as connection:
            row = connection.execute("SELECT id FROM cases ORDER BY id ASC LIMIT 1").fetchone()
            if row is None:
                timestamp = utc_timestamp()
                cursor = connection.execute(
                    "INSERT INTO cases (title, description, status, created_at, updated_at) VALUES (?, ?, 'open', ?, ?)",
                    ("Unsorted observations", "Local inbox for observations that have not yet been assigned.", timestamp, timestamp),
                )
                default_case_id = int(cursor.lastrowid)
            else:
                default_case_id = int(row["id"])
            connection.execute(
                """INSERT OR IGNORE INTO case_observations (case_id, observation_id, added_at)
                   SELECT ?, o.id, ? FROM observations o""",
                (default_case_id, utc_timestamp()),
            )

    def _backfill_legacy_evidence(self) -> None:
        """Makes observations created by the first MVP auditable in case views."""
        with open_connection(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                SELECT co.case_id, o.id, 'captured_content', 'Captured legacy observation',
                       o.source_url, o.captured_at, 'Backfilled from the local MVP record.', ?
                FROM case_observations co
                JOIN observations o ON o.id = co.observation_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM evidence e
                    WHERE e.case_id = co.case_id AND e.observation_id = o.id AND e.kind = 'captured_content'
                )
                """,
                (utc_timestamp(),),
            )
            connection.execute(
                """
                INSERT INTO evidence (case_id, observation_id, kind, label, url, captured_at, annotation, created_at)
                SELECT co.case_id, s.observation_id, 'external_source', s.title,
                       s.url, o.captured_at, COALESCE(s.excerpt, ''), ?
                FROM sources s
                JOIN observations o ON o.id = s.observation_id
                JOIN case_observations co ON co.observation_id = s.observation_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM evidence e
                    WHERE e.case_id = co.case_id AND e.observation_id = s.observation_id
                      AND e.kind = 'external_source' AND e.label = s.title
                )
                """,
                (utc_timestamp(),),
            )

    def _backfill_legacy_fingerprints(self) -> None:
        with open_connection(self.db_path) as connection:
            rows = connection.execute(
                """SELECT o.id, o.body, o.platform, o.source_url, o.captured_at, a.handle
                   FROM observations o JOIN actors a ON a.id = o.actor_id
                   WHERE NOT EXISTS (
                       SELECT 1 FROM observation_fingerprints fp WHERE fp.observation_id = o.id
                   )"""
            ).fetchall()
            for row in rows:
                fingerprint = self.evidence_integrity.fingerprint_observation(dict(row))
                connection.execute(
                    """INSERT INTO observation_fingerprints (observation_id, content_hash, context_hash, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (row["id"], fingerprint.content_hash, fingerprint.context_hash, utc_timestamp()),
                )
    def _resolve_case_id(self, connection: Any, requested_case_id: Any) -> int:
        if requested_case_id not in (None, ""):
            try:
                case_id = int(requested_case_id)
            except (TypeError, ValueError) as error:
                raise ValueError("invalid case_id") from error
            self._require_case(connection, case_id)
            return case_id
        row = connection.execute("SELECT id FROM cases ORDER BY id ASC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("no case available")
        return int(row["id"])

    @staticmethod
    def _require_case(connection: Any, case_id: int) -> None:
        if connection.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone() is None:
            raise ValueError("case not found")

    def _tag_observation(self, connection: Any, case_id: int, observation_id: int, label: str, color: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO tags (case_id, label, color, created_at) VALUES (?, ?, ?, ?)",
            (case_id, label, color, utc_timestamp()),
        )
        row = connection.execute("SELECT id FROM tags WHERE case_id = ? AND label = ?", (case_id, label)).fetchone()
        connection.execute(
            "INSERT OR IGNORE INTO observation_tags (observation_id, tag_id) VALUES (?, ?)",
            (observation_id, row["id"]),
        )

    def _record_profile_snapshot(
        self,
        connection: Any,
        case_id: int,
        actor_id: int,
        observation_id: int,
        payload: dict[str, Any],
        handle: str,
        display_name: str,
        captured_at: str,
    ) -> int:
        current = {
            "handle": handle,
            "display_name": display_name,
            "bio": self._clean_text(payload.get("profile_bio")),
            "profile_url": self._clean_text(payload.get("profile_url")),
        }
        if not any(current.values()):
            return 0
        previous = connection.execute(
            """SELECT handle, display_name, bio, profile_url FROM profile_snapshots
               WHERE actor_id = ? AND case_id = ? ORDER BY captured_at DESC, id DESC LIMIT 1""",
            (actor_id, case_id),
        ).fetchone()
        changes = self.profile_resolver.compare(dict(previous) if previous else None, current)
        connection.execute(
            """INSERT INTO profile_snapshots (actor_id, case_id, handle, display_name, bio, profile_url, captured_at, evidence_observation_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (actor_id, case_id, current["handle"], current["display_name"], current["bio"], current["profile_url"], captured_at, observation_id),
        )
        for change in changes:
            self._record_job(
                connection,
                case_id,
                module_name("profile_resolver"),
                f"{change.field} changed from {change.previous} to {change.current}.",
                "review_needed",
                change.confidence,
                observation_id,
            )
        return len(changes)

    @staticmethod
    def _bounded_confidence(value: Any, default: float) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = default
        return max(0.0, min(confidence, 1.0))

    @staticmethod
    def _record_job(
        connection: Any,
        case_id: int,
        stage: str,
        message: str,
        state: str,
        confidence: float | None,
        observation_id: int | None,
    ) -> None:
        connection.execute(
            """INSERT INTO processing_jobs (case_id, stage, message, state, confidence, related_observation_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (case_id, stage, message, state, confidence, observation_id, utc_timestamp()),
        )

    def _require_text(self, value: Any, field_name: str) -> str:
        cleaned = self._clean_text(value)
        if not cleaned:
            raise ValueError(f"{field_name} is required")
        return cleaned

    def _clean_sources(self, sources: Any) -> list[dict[str, str]]:
        cleaned_sources = []
        if not isinstance(sources, list):
            return cleaned_sources
        for raw in sources:
            if not isinstance(raw, dict):
                continue
            title = self._clean_text(raw.get("title"))
            if not title:
                continue
            cleaned_sources.append(
                {
                    "title": title,
                    "url": self._clean_text(raw.get("url")),
                    "excerpt": self._clean_text(raw.get("excerpt")),
                }
            )
        return cleaned_sources

    def _clean_relationships(self, relationships: Any, default_platform: str) -> list[dict[str, Any]]:
        cleaned_relationships = []
        if not isinstance(relationships, list):
            return cleaned_relationships
        for raw in relationships:
            if not isinstance(raw, dict):
                continue
            handle = self._clean_text(raw.get("handle"))
            if not handle:
                continue
            relation_type = self._clean_text(raw.get("relation_type")) or "co-mentioned"
            platform = self._clean_text(raw.get("platform")) or default_platform
            try:
                weight = float(raw.get("weight", 0.5))
            except (TypeError, ValueError):
                weight = 0.5
            cleaned_relationships.append(
                {
                    "handle": handle,
                    "display_name": self._clean_text(raw.get("display_name")),
                    "platform": platform,
                    "relation_type": relation_type,
                    "weight": max(0.1, min(weight, 1.0)),
                }
            )
        return cleaned_relationships

    def _get_or_create_actor(self, connection: Any, handle: str, platform: str, display_name: str | None) -> int:
        row = connection.execute(
            "SELECT id FROM actors WHERE handle = ? AND platform = ?",
            (handle, platform),
        ).fetchone()
        if row:
            if display_name:
                connection.execute(
                    "UPDATE actors SET display_name = COALESCE(NULLIF(?, ''), display_name) WHERE id = ?",
                    (display_name, row["id"]),
                )
            return int(row["id"])

        cursor = connection.execute(
            """
            INSERT INTO actors (handle, platform, display_name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (handle, platform, display_name, utc_timestamp()),
        )
        return int(cursor.lastrowid)

    def _refresh_actor_score(self, connection: Any, actor_id: int) -> None:
        row = connection.execute(
            """
            SELECT AVG(risk_level) AS avg_risk
            FROM observations
            WHERE actor_id = ?
            """,
            (actor_id,),
        ).fetchone()
        avg_risk = float(row["avg_risk"] or 0)
        connection.execute(
            "UPDATE actors SET risk_score = ? WHERE id = ?",
            (round(avg_risk, 2), actor_id),
        )
