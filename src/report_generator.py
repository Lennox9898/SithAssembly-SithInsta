from __future__ import annotations

import json
import unicodedata
from typing import Any


class ReportGenerator:
    def json_bytes(self, report: dict[str, Any]) -> bytes:
        return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")

    def pdf_bytes(self, report: dict[str, Any]) -> bytes:
        lines = self._lines(report)
        pages = [lines[index : index + 46] for index in range(0, len(lines), 46)] or [["Signal Desk case export"]]
        objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
        page_ids: list[int] = []
        content_ids: list[int] = []
        for _page in pages:
            page_ids.append(len(objects) + 1)
            objects.append(b"")
            content_ids.append(len(objects) + 1)
            objects.append(b"")
        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids).encode("ascii")
        objects[1] = b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_ids)).encode("ascii") + b" >>"
        for index, page in enumerate(pages):
            content = self._page_stream(page)
            objects[content_ids[index] - 1] = (
                f"<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream"
            )
            objects[page_ids[index] - 1] = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {content_ids[index]} 0 R >>".encode("ascii")
            )
        return self._serialize(objects)

    def _lines(self, report: dict[str, Any]) -> list[str]:
        case = report["case"]
        lines = [
            "SIGNAL DESK - CASE EXPORT",
            f"Case: {case['title']} (ID {case['id']})",
            f"Generated: {report['generated_at']}",
            "",
            "Profiles",
        ]
        for profile in report["profiles"]:
            lines.append(f"- {profile['handle']} | id {profile['id']} | observations {profile['observation_count']}")
        lines.extend(["", "Identity hypotheses (analyst-supplied, not verified facts)"])
        for claim in report["identity_hypotheses"]:
            lines.append(f"- {claim['handle']}: {claim['candidate_label']} | confidence {claim['confidence']:.2f} | {claim['state']}")
            lines.append(f"  Basis: {claim['basis']}")
        lines.extend(["", "Chronology"])
        for event in report["timeline"]:
            lines.append(f"- {event['timestamp']} | {event['kind']} | {event['label']}")
        lines.extend(["", "Relationships with evidence"])
        for edge in report["relationships"]:
            lines.append(f"- {edge['source_handle']} -> {edge['target_handle']} | {edge['relation_type']} | confidence {edge['confidence']:.2f}")
            lines.append(f"  Evidence: {edge.get('evidence_url') or 'no URL'} @ {edge.get('evidence_timestamp') or 'unknown time'}")
        lines.extend(["", "Evidence register"])
        for evidence in report["evidence"]:
            lines.append(f"- {evidence['kind']} | {evidence['label']} | {evidence.get('url') or evidence.get('file_path') or 'local note'} | {evidence['captured_at']}")
        return self._wrap(lines)

    @staticmethod
    def _wrap(lines: list[str], width: int = 96) -> list[str]:
        wrapped: list[str] = []
        for line in lines:
            normalized = unicodedata.normalize("NFKD", line).encode("ascii", "ignore").decode("ascii")
            while len(normalized) > width:
                split_at = normalized.rfind(" ", 0, width)
                split_at = split_at if split_at > 20 else width
                wrapped.append(normalized[:split_at])
                normalized = "  " + normalized[split_at:].lstrip()
            wrapped.append(normalized)
        return wrapped

    @staticmethod
    def _page_stream(lines: list[str]) -> bytes:
        commands = ["BT", "/F1 9 Tf", "44 755 Td", "12 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) Tj")
            commands.append("T*")
        commands.append("ET")
        return "\n".join(commands).encode("ascii")

    @staticmethod
    def _serialize(objects: list[bytes]) -> bytes:
        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("ascii"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
        return bytes(output)
