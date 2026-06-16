"""Cocofolia (ココフォリア) adapter.

Cocofolia imports characters via a JSON object placed on the clipboard. We build
that object for each character (name, HP status bar, the six abilities as params,
and a chat-palette of ready-to-roll commands) and a session helper that returns
one clipboard payload per character. Maps are emitted as a simple descriptor,
since Cocofolia scene backgrounds are image-based rather than grid data.
"""

from __future__ import annotations

import json
from typing import Any

from sandcastlegm.core.state import Character, MapGrid
from sandcastlegm.vtt.base import VTTAdapter


class CocofoliaAdapter(VTTAdapter):
    id = "cocofolia"
    name = "Cocofolia (ココフォリア)"

    def export_character(self, character: Character) -> dict[str, Any]:
        sheet = character.sheet
        abilities = sheet.get("abilities", {})
        params = [{"label": k, "value": str(v)} for k, v in abilities.items()]
        if "level" in sheet:
            params.append({"label": "Lv", "value": str(sheet["level"])})

        # A chat palette so players can roll the core 3d6 + ability checks.
        commands = "\n".join(
            f"3d6+{{{k}}} 【{k} 能力値判定】" for k in abilities
        ) or "3d6 【判定】"

        return {
            "kind": "character",
            "data": {
                "name": character.name,
                "memo": self._memo(character),
                "initiative": 0,
                "externalUrl": "",
                "status": [
                    {"label": "HP", "value": character.hp, "max": character.max_hp}
                ],
                "params": params,
                "iconUrl": "",
                "commands": commands,
                "color": "#2f4f4f" if character.is_pc else "#7a2f2f",
            },
        }

    def export_character_clipboard(self, character: Character) -> str:
        """The exact string a player pastes into Cocofolia."""
        return json.dumps(self.export_character(character), ensure_ascii=False)

    def export_map(self, grid: MapGrid) -> dict[str, Any]:
        return {
            "kind": "scene",
            "data": {
                "name": grid.name,
                "width": grid.width,
                "height": grid.height,
                "note": "Background image not generated; grid size only.",
            },
        }

    @staticmethod
    def _memo(character: Character) -> str:
        s = character.sheet
        bits = [
            f"{s.get('subspecies', '')} {s.get('combat_style', '')}".strip(),
            f"技能: {'、'.join(s.get('skills', []))}" if s.get("skills") else "",
        ]
        return "\n".join(b for b in bits if b)
