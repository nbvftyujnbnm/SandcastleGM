"""Udonarium (ユドナリウム) adapter.

Udonarium represents everything as XML and saves a room as a zip of those XML
files. We emit a ``<character>`` element per character (name, size, an HP number
resource, and the abilities as a parameter block) and a ``<game-table>`` element
for a map, then bundle them into a room-style zip. Coordinates are converted from
grid cells to Udonarium's pixel space using ``grid_size``.

The schema here follows Udonarium's open data model closely enough to import;
exact element nesting may need tuning against a given Udonarium build, which is
why each piece is also available as standalone XML.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from sandcastlegm.core.state import Character, GameState, MapGrid
from sandcastlegm.vtt.base import VTTAdapter

GRID_SIZE = 50  # pixels per cell


class UdonariumAdapter(VTTAdapter):
    id = "udonarium"
    name = "Udonarium (ユドナリウム)"

    def export_character(self, character: Character, x: int = 0, y: int = 0) -> str:
        root = ET.Element(
            "character",
            {
                "location.name": "table",
                "location.x": str(x * GRID_SIZE),
                "location.y": str(y * GRID_SIZE),
                "posZ": "0",
                "rotate": "0",
                "roll": "0",
            },
        )
        cdata = ET.SubElement(root, "data", {"name": "character"})

        image = ET.SubElement(cdata, "data", {"name": "image"})
        img_id = ET.SubElement(image, "data", {"name": "imageIdentifier", "type": "image"})
        img_id.text = "none_icon"

        common = ET.SubElement(cdata, "data", {"name": "common"})
        ET.SubElement(common, "data", {"name": "name"}).text = character.name
        ET.SubElement(common, "data", {"name": "size"}).text = "1"

        detail = ET.SubElement(cdata, "data", {"name": "detail"})
        resource = ET.SubElement(detail, "data", {"name": "リソース"})
        hp = ET.SubElement(
            resource,
            "data",
            {"name": "HP", "type": "numberResource", "currentValue": str(character.hp)},
        )
        hp.text = str(character.max_hp)

        info = ET.SubElement(detail, "data", {"name": "能力値"})
        for key, value in character.sheet.get("abilities", {}).items():
            ET.SubElement(info, "data", {"name": key}).text = str(value)
        if "level" in character.sheet:
            ET.SubElement(info, "data", {"name": "Lv"}).text = str(character.sheet["level"])

        return _to_xml(root)

    def export_map(self, grid: MapGrid) -> str:
        root = ET.Element(
            "game-table",
            {
                "name": grid.name,
                "width": str(grid.width),
                "height": str(grid.height),
                "gridSize": str(GRID_SIZE),
                "gridType": "0",
                "gridColor": "#000000e6",
                "backgroundImageIdentifier": "testTableBackgroundImage_image",
                "backgroundFilterType": "",
            },
        )
        return _to_xml(root)

    def export_session(self, state: GameState) -> bytes:
        """A Udonarium-style room zip: one XML file per object."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for grid in state.maps.values():
                zf.writestr(f"map_{grid.id}.xml", self.export_map(grid))
            grid = state.active_map
            for character in state.characters.values():
                x = y = 0
                if grid is not None:
                    tok = next(
                        (t for t in grid.tokens.values() if t.character_id == character.id),
                        None,
                    )
                    if tok is not None:
                        x, y = tok.position.x, tok.position.y
                zf.writestr(
                    f"character_{character.id}.xml",
                    self.export_character(character, x=x, y=y),
                )
        return buffer.getvalue()


def _to_xml(element: ET.Element) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        element, encoding="unicode"
    )
