"""Spectrum files and the spectrum library (a folder of JSON files).

One JSON file per spectrum. Channel values are raw PWM counts (0-4096), the
same units the G2VPico API uses. Format (schema_version 1):

{
  "schema_version": 1,
  "name": "AM1.5G",
  "description": "Pico web-UI preset",
  "units": "pwm",
  "pwm_max": 4096,
  "global_intensity": 100.0,
  "channels": [
    {"channel": "1", "value": 112, "wavelength_nm": [395, 405]},
    ...
  ],
  "source": "Pico web UI preset 'AM1.5G'",
  "pico_id": "0000000031a0525e",
  "channel_count": 32,
  "created": "2026-11-16T16:30:00-08:00",
  "notes": ""
}

Only "name" and "channels" are required; everything else is metadata.
"channels" uses G2V's native list-of-dicts format, so the list can be passed
straight to G2VPico.set_spectrum() as well.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

SCHEMA_VERSION = 1
PWM_MAX = 4096


class SpectrumError(ValueError):
    """Raised for a malformed spectrum file or an unknown spectrum name."""


def validate_intensity(value) -> float:
    try:
        percent = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SpectrumError(f"Invalid intensity {value!r}") from exc
    if isinstance(value, bool) or not 0 <= percent <= 100:
        raise SpectrumError(f"Intensity must be 0-100 %, got {value!r}")
    return percent


def pwm_integer(value) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value.strip()):
        return int(value)
    raise SpectrumError(f"Expected an integer channel or PWM value, got {value!r}")


def slugify(name: str) -> str:
    """'AM1.5G (1 sun)' -> 'am1.5g_1_sun' - a safe file name stem."""
    slug = re.sub(r"[^A-Za-z0-9.\-]+", "_", name.strip()).strip("_").lower()
    if not slug:
        raise SpectrumError(f"Cannot make a file name from spectrum name {name!r}")
    return slug


@dataclass
class Spectrum:
    name: str
    channels: Dict[int, int]                     # channel number -> PWM value
    global_intensity: Optional[float] = 100.0    # 0-100 %, None = leave unchanged
    description: str = ""
    source: str = ""
    pico_id: str = ""
    created: str = ""
    notes: str = ""
    wavelengths_nm: Dict[int, List[float]] = field(default_factory=dict)
    path: Optional[Path] = None                  # where it was loaded from

    # ------------------------------------------------------------ validation
    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SpectrumError("Spectrum has no name")
        if not isinstance(self.channels, dict) or not self.channels:
            raise SpectrumError(f"Spectrum {self.name!r} has no channels")
        for ch, val in self.channels.items():
            if type(ch) is not int or ch < 1:
                raise SpectrumError(f"{self.name!r}: invalid channel {ch}")
            if type(val) is not int or not 0 <= val <= PWM_MAX:
                raise SpectrumError(
                    f"{self.name!r}: channel {ch} value {val} outside 0-{PWM_MAX}")
        gi = self.global_intensity
        if gi is not None:
            validate_intensity(gi)
        if not isinstance(self.wavelengths_nm, dict):
            raise SpectrumError("wavelengths_nm must be a dictionary")
        for ch, bounds in self.wavelengths_nm.items():
            if (ch not in self.channels or not isinstance(bounds, (list, tuple))
                    or len(bounds) != 2
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds)):
                raise SpectrumError(f"Invalid wavelength range for channel {ch}: {bounds!r}")

    # ------------------------------------------------------------ conversion
    def to_g2v_list(self) -> List[dict]:
        """G2V's native format: [{'channel': '1', 'value': 112}, ...]."""
        return [{"channel": str(ch), "value": int(v)}
                for ch, v in sorted(self.channels.items())]

    def to_dict(self) -> dict:
        chans = []
        for ch, v in sorted(self.channels.items()):
            item = {"channel": str(ch), "value": int(v)}
            if ch in self.wavelengths_nm:
                item["wavelength_nm"] = self.wavelengths_nm[ch]
            chans.append(item)
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "units": "pwm",
            "pwm_max": PWM_MAX,
            "global_intensity": self.global_intensity,
            "channels": chans,
            "source": self.source,
            "pico_id": self.pico_id,
            "channel_count": len(self.channels),
            "created": self.created or datetime.now().astimezone().isoformat(timespec="seconds"),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data, path: Optional[Path] = None) -> "Spectrum":
        # Also accept a bare G2V list (e.g. G2V's example test_spectrum.json).
        if isinstance(data, list):
            data = {"name": path.stem if path else "unnamed", "channels": data,
                    "global_intensity": None}
        if not isinstance(data, dict):
            raise SpectrumError(f"{path}: expected a JSON object or list")
        if data.get("units", "pwm") != "pwm":
            raise SpectrumError(f"{path}: units {data['units']!r} not supported (expected 'pwm')")

        channels: Dict[int, int] = {}
        wavelengths: Dict[int, List[float]] = {}
        entries = data.get("channels", [])
        if not isinstance(entries, list):
            raise SpectrumError(f"{path}: channels must be a list")
        for item in entries:
            if not isinstance(item, dict):
                raise SpectrumError(f"{path}: bad channel entry {item!r}")
            try:
                ch = pwm_integer(item["channel"])
                val = pwm_integer(item["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SpectrumError(f"{path}: bad channel entry {item!r}") from exc
            if ch in channels:
                raise SpectrumError(f"{path}: channel {ch} listed twice")
            channels[ch] = val
            if item.get("wavelength_nm"):
                wavelengths[ch] = item["wavelength_nm"]

        spec = cls(
            name=data.get("name") or (path.stem if path else ""),
            channels=channels,
            global_intensity=data.get("global_intensity", 100.0),
            description=data.get("description", ""),
            source=data.get("source", ""),
            pico_id=data.get("pico_id", ""),
            created=data.get("created", ""),
            notes=data.get("notes", ""),
            wavelengths_nm=wavelengths,
            path=path,
        )
        spec.validate()
        if spec.global_intensity is not None:
            spec.global_intensity = validate_intensity(spec.global_intensity)
        return spec

    # ------------------------------------------------------------ file I/O
    @classmethod
    def load(cls, path) -> "Spectrum":
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise SpectrumError(f"{path}: not valid JSON ({exc})") from exc
        return cls.from_dict(data, path)

    def save(self, path, overwrite: bool = False) -> Path:
        path = Path(path)
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists (pass overwrite=True)")
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            try:
                output.write(content)
            except BaseException:
                output.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            if overwrite:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        self.path = path
        return path


class SpectrumLibrary:
    """A folder of spectrum JSON files, looked up by name (case-insensitive)."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Spectrum] = {}
        self.errors: Dict[str, str] = {}   # file name -> problem, for bad files
        self.reload()

    def reload(self) -> None:
        self._cache.clear()
        self.errors.clear()
        for path in sorted(self.folder.glob("*.json")):
            try:
                spec = Spectrum.load(path)
            except (SpectrumError, OSError) as exc:
                self.errors[path.name] = str(exc)
                continue
            key = spec.name.lower()
            if key in self._cache:
                self.errors[path.name] = (
                    f"duplicate name {spec.name!r} (also in {self._cache[key].path.name})")
                continue
            self._cache[key] = spec

    def names(self) -> List[str]:
        return sorted(s.name for s in self._cache.values())

    def __iter__(self) -> Iterator[Spectrum]:
        return iter(sorted(self._cache.values(), key=lambda s: s.name.lower()))

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._cache

    def get(self, name: str) -> Spectrum:
        try:
            return self._cache[name.lower()]
        except KeyError:
            raise SpectrumError(
                f"No spectrum named {name!r} in {self.folder}. "
                f"Available: {', '.join(self.names()) or '(none)'}") from None

    def add(self, spec: Spectrum, overwrite: bool = False) -> Path:
        spec.validate()
        existing = self._cache.get(spec.name.lower())
        if existing is not None and not overwrite:
            raise FileExistsError(f"Spectrum {spec.name!r} already exists (pass overwrite=True)")
        path = existing.path if existing is not None else self.folder / f"{slugify(spec.name)}.json"
        path = spec.save(path, overwrite=overwrite and existing is not None)
        self._cache[spec.name.lower()] = spec
        return path
