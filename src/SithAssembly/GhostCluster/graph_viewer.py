from __future__ import annotations

from collections import defaultdict
from typing import Any


class GraphViewer:
    def enrich(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        degree: dict[int, int] = defaultdict(int)
        adjacency: dict[int, set[int]] = defaultdict(set)
        for edge in edges:
            source_id = int(edge["source_id"])
            target_id = int(edge["target_id"])
            degree[source_id] += 1
            degree[target_id] += 1
            adjacency[source_id].add(target_id)
            adjacency[target_id].add(source_id)

        for node in nodes:
            node["degree"] = degree[int(node["id"])]
            node["centrality"] = node["observation_count"] + node["degree"]

        groups: list[list[int]] = []
        visited: set[int] = set()
        for node in nodes:
            node_id = int(node["id"])
            if node_id in visited:
                continue
            stack = [node_id]
            component: list[int] = []
            visited.add(node_id)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            groups.append(component)
        return {"nodes": nodes, "edges": edges, "groups": groups}

    @staticmethod
    def shortest_path(graph: dict[str, Any], source_handle: str, target_handle: str, max_hops: int = 4) -> list[dict[str, Any]]:
        nodes_by_handle = {str(node["handle"]).lower(): int(node["id"]) for node in graph["nodes"]}
        source_id = nodes_by_handle.get(source_handle.lower())
        target_id = nodes_by_handle.get(target_handle.lower())
        if source_id is None or target_id is None:
            return []
        paths: dict[int, list[dict[str, Any]]] = {source_id: []}
        queue = [source_id]
        while queue:
            current = queue.pop(0)
            current_path = paths[current]
            if current == target_id:
                return current_path
            if len(current_path) >= max_hops:
                continue
            for edge in graph["edges"]:
                if int(edge["source_id"]) != current:
                    continue
                next_id = int(edge["target_id"])
                if next_id in paths:
                    continue
                paths[next_id] = [*current_path, edge]
                queue.append(next_id)
        return []
