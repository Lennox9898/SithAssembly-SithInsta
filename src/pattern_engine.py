from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlparse


class PatternEngine:
    """Builds evidence-linked pattern candidates from already captured case records."""

    def findings(
        self,
        observations: list[dict[str, Any]],
        tags: list[dict[str, Any]],
        links: list[dict[str, Any]],
        fingerprints: list[dict[str, Any]],
        graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        findings.extend(self._recurring_accounts(observations))
        findings.extend(self._shared_tags(tags))
        findings.extend(self._shared_domains(links))
        findings.extend(self._repeated_content(fingerprints))
        findings.extend(self._central_nodes(graph))
        return sorted(findings, key=lambda item: (-item["confidence"], item["kind"], item["title"]))

    @staticmethod
    def _recurring_accounts(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for observation in observations:
            grouped[observation["actor_handle"]].append(observation)
        return [
            {
                "id": f"recurring-account:{handle.lower()}",
                "kind": "recurring_account",
                "title": f"Repeated account: {handle}",
                "summary": f"{len(items)} captured observations in this case.",
                "confidence": 0.9,
                "observation_ids": [item["id"] for item in items],
            }
            for handle, items in grouped.items()
            if len(items) >= 3
        ]

    @staticmethod
    def _shared_tags(tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for tag in tags:
            grouped[tag["label"]].append(tag)
        findings = []
        for label, items in grouped.items():
            actors = {item["actor_handle"] for item in items}
            if len(actors) < 2:
                continue
            findings.append(
                {
                    "id": f"shared-hashtag:{label.lower()}",
                    "kind": "shared_hashtag",
                    "title": f"Shared hashtag: {label}",
                    "summary": f"Observed across {len(actors)} accounts.",
                    "confidence": 0.72,
                    "observation_ids": sorted({item["observation_id"] for item in items}),
                }
            )
        return findings

    @staticmethod
    def _shared_domains(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for link in links:
            domain = urlparse(str(link.get("url", ""))).netloc.lower()
            if domain:
                grouped[domain].append(link)
        findings = []
        for domain, items in grouped.items():
            actors = {item["actor_handle"] for item in items}
            if len(actors) < 2:
                continue
            findings.append(
                {
                    "id": f"shared-domain:{domain}",
                    "kind": "shared_domain",
                    "title": f"Shared domain: {domain}",
                    "summary": f"Linked by {len(actors)} accounts in captured material.",
                    "confidence": 0.8,
                    "observation_ids": sorted({item["observation_id"] for item in items}),
                }
            )
        return findings

    @staticmethod
    def _repeated_content(fingerprints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fingerprint in fingerprints:
            grouped[fingerprint["content_hash"]].append(fingerprint)
        findings = []
        for content_hash, items in grouped.items():
            actors = {item["actor_handle"] for item in items}
            if len(actors) < 2:
                continue
            findings.append(
                {
                    "id": f"repeated-content:{content_hash[:16]}",
                    "kind": "repeated_content",
                    "title": "Repeated captured text",
                    "summary": f"The same normalized text appears across {len(actors)} accounts.",
                    "confidence": 0.78,
                    "observation_ids": sorted({item["observation_id"] for item in items}),
                }
            )
        return findings

    @staticmethod
    def _central_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": f"central-node:{node['id']}",
                "kind": "central_actor",
                "title": f"Central node candidate: {node['handle']}",
                "summary": f"Degree {node['degree']}; local centrality score {node['centrality']}.",
                "confidence": 0.65,
                "observation_ids": [],
                "actor_id": node["id"],
            }
            for node in graph["nodes"]
            if node["centrality"] >= 4
        ]
