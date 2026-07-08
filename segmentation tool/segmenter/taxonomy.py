from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PartSpec:
    name: str
    zone: str
    y_range: tuple[float, float]
    optional: bool = True
    primary_fallback: bool = False


@dataclass(frozen=True)
class ClassSpec:
    artifact_class: str
    axis: str
    parts: list[PartSpec]


class Taxonomy:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.version = data.get("version", "unknown")
        self._classes: dict[str, ClassSpec] = {}

        for class_name, spec in data.get("classes", {}).items():
            parts: list[PartSpec] = []
            for part in spec.get("parts", []):
                y_range = part.get("y_range", [0.0, 1.0])
                parts.append(
                    PartSpec(
                        name=str(part["name"]),
                        zone=str(part.get("zone", "")),
                        y_range=(float(y_range[0]), float(y_range[1])),
                        optional=bool(part.get("optional", True)),
                        primary_fallback=bool(part.get("primary_fallback", False)),
                    )
                )

            self._classes[class_name] = ClassSpec(
                artifact_class=class_name,
                axis=str(spec.get("axis", "unknown")),
                parts=parts,
            )

    @property
    def class_names(self) -> list[str]:
        return sorted(self._classes)

    def get(self, artifact_class: str) -> ClassSpec:
        key = artifact_class.strip().casefold()
        for name, spec in self._classes.items():
            if name.casefold() == key:
                return spec
        raise KeyError(
            f"Unknown artifact class: {artifact_class!r}. "
            f"Available: {', '.join(self.class_names)}"
        )
