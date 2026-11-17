"""PicoController: one object for talking to the G2V Pico.

    from pico_lab import PicoController

    with PicoController.from_config("config.json") as pico:
        print(pico.list_spectra())
        pico.apply_spectrum("AM1.5G", turn_on=True)
        ...
        pico.off()

Built on G2V's official `g2vpico` package (v1.0.9). Only the public G2VPico
methods are used, except closing the TCP socket (G2V provides no close()).
"""
from __future__ import annotations

import json
import math
import socket
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from .spectrum import Spectrum, SpectrumError, SpectrumLibrary, validate_intensity

DEFAULT_TIMEOUT_S = 20  # value that worked in the Sep 29 connection test


class PicoController:
    def __init__(self, ip_address: str, pico_id: str, spectra_dir="spectra",
                 timeout_s: float = DEFAULT_TIMEOUT_S, device=None):
        """
        ip_address  : Pico Ethernet IPv4 address, e.g. "169.254.84.67"
        pico_id     : 16-character Pico ID as a string, keep leading zeros
        spectra_dir : folder of spectrum JSON files
        device      : an already-made G2VPico-like object (used for tests / dry runs);
                      if None, a real G2VPico connection is opened.
        """
        pico_id = str(pico_id)
        if device is None and len(pico_id) != 16:
            raise ValueError(f"Pico ID must be 16 characters incl. leading zeros, got {pico_id!r}")
        self.ip_address = ip_address
        self.pico_id = pico_id
        self.library = SpectrumLibrary(spectra_dir)

        if device is None:
            from g2vpico import G2VPico  # imported here so tests run without it
            old = socket.getdefaulttimeout()
            socket.setdefaulttimeout(timeout_s)
            try:
                device = G2VPico(ip_address, pico_id)
            finally:
                socket.setdefaulttimeout(old)
            # G2V creates its socket before connect, so set the timeout on it too.
            sock = getattr(device, "_socket", None)
            if sock is not None:
                sock.settimeout(timeout_s)
        self._dev = device
        self.channels: List[int] = list(device.channel_list)
        self._limits: Dict[int, int] = {}
        self._wavelengths: Dict[int, List[float]] = {}
        self.current_spectrum: Optional[str] = None

    # ---------------------------------------------------------------- setup
    @classmethod
    def from_config(cls, path="config.json", **overrides) -> "PicoController":
        """Read ip_address, pico_id, spectra_dir, timeout_s from a JSON file.
        Relative spectra_dir is resolved next to the config file."""
        path = Path(path)
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in overrides.items() if v is not None})
        spectra_dir = Path(cfg.get("spectra_dir", "spectra"))
        if not spectra_dir.is_absolute():
            spectra_dir = path.parent / spectra_dir
        return cls(cfg["ip_address"], cfg["pico_id"], spectra_dir=spectra_dir,
                   timeout_s=cfg.get("timeout_s", DEFAULT_TIMEOUT_S),
                   device=cfg.get("device"))

    def close(self) -> None:
        """Close the TCP connection. Does NOT turn the light off."""
        sock = getattr(self._dev, "_socket", None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __repr__(self):
        return f"PicoController({self.pico_id} @ {self.ip_address}, {len(self.channels)} channels)"

    # ---------------------------------------------------------------- basics
    def on(self) -> bool:
        if self._dev.turn_on() is not True:
            raise RuntimeError("Pico did not acknowledge the light-on command")
        if not self.is_on():
            raise RuntimeError("Pico did not turn the light on")
        return True

    def off(self) -> bool:
        if self._dev.turn_off() is not True:
            raise RuntimeError("Pico did not acknowledge the light-off command")
        if self.is_on():
            raise RuntimeError("Pico did not turn the light off")
        return True

    def is_on(self) -> bool:
        state = self._dev.is_fixture_on()
        if type(state) is not bool:
            raise RuntimeError(f"Invalid fixture state from Pico: {state!r}")
        return state

    def get_intensity(self) -> float:
        return self._dev.get_global_intensity()

    def set_intensity(self, percent: float) -> bool:
        """Global intensity 0-100 %. Takes effect immediately."""
        percent = validate_intensity(percent)
        if self._dev.set_global_intensity(percent) is not True:
            raise RuntimeError("Pico did not acknowledge the intensity command")
        actual = self.get_intensity()
        if (type(actual) not in (int, float)
                or not math.isclose(actual, percent, rel_tol=0, abs_tol=1e-6)):
            raise RuntimeError(f"Intensity did not match: wanted {percent}, got {actual!r}")
        return True

    def channel_limit(self, channel: int) -> int:
        """Max PWM value allowed on a channel (cached after first read)."""
        if channel not in self._limits:
            self._limits[channel] = int(self._dev.get_channel_limit(channel))
        return self._limits[channel]

    def wavelength_range(self, channel: int) -> List[float]:
        if channel not in self._wavelengths:
            self._wavelengths[channel] = self._dev.get_channel_wavelength_range(channel)
        return self._wavelengths[channel]

    def read_channels(self) -> Dict[int, int]:
        """Current PWM value of every channel, read from the Pico."""
        return {ch: int(self._dev.get_channel_value(ch)) for ch in self.channels}

    def status(self) -> dict:
        return {
            "pico_id": self.pico_id,
            "ip_address": self.ip_address,
            "light_on": self.is_on(),
            "global_intensity": self.get_intensity(),
            "channel_count": len(self.channels),
            "last_applied_spectrum": self.current_spectrum,
        }

    # ---------------------------------------------------------------- spectra
    def list_spectra(self) -> List[str]:
        return self.library.names()

    def check_spectrum(self, spec: Spectrum) -> None:
        """Raise SpectrumError if the spectrum doesn't fit this Pico."""
        unknown = sorted(set(spec.channels) - set(self.channels))
        if unknown:
            raise SpectrumError(f"{spec.name!r} uses channels this Pico doesn't have: {unknown}")
        over = {ch: (v, self.channel_limit(ch)) for ch, v in spec.channels.items()
                if v > self.channel_limit(ch)}
        if over:
            detail = ", ".join(f"ch{c}={v}>limit {lim}" for c, (v, lim) in sorted(over.items()))
            raise SpectrumError(f"{spec.name!r} exceeds channel limits: {detail}")

    def apply_spectrum(self, spectrum: Union[str, Spectrum], turn_on: bool = False,
                       intensity: Optional[float] = None, verify: bool = True) -> Spectrum:
        """Load a spectrum onto the Pico.

        spectrum  : a name from the library, or a Spectrum object
        turn_on   : turn the light on after loading (default: leave it off)
        intensity : global intensity % to use; default is the spectrum's own value
        verify    : read every channel back and check it matches

        Safety: the light is turned OFF first, so the sample never sees a
        half-updated mix of old and new channels. Channels not listed in the
        spectrum are set to 0 (G2V's set_spectrum leaves them unchanged).
        """
        spec = self.library.get(spectrum) if isinstance(spectrum, str) else spectrum
        spec.validate()
        gi = intensity if intensity is not None else spec.global_intensity
        if gi is not None:
            gi = validate_intensity(gi)
        self.check_spectrum(spec)

        self.off()
        self.current_spectrum = None
        target = {ch: spec.channels.get(ch, 0) for ch in self.channels}
        for ch, value in target.items():
            if self._dev.set_channel_value(ch, value) is not True:
                raise RuntimeError(f"Spectrum {spec.name!r} did not load correctly: "
                                   f"channel {ch} write was not acknowledged")

        if gi is not None:
            self.set_intensity(gi)

        if verify:
            actual = self.read_channels()
            bad = {ch: (target[ch], actual[ch]) for ch in target if actual[ch] != target[ch]}
            if bad:
                detail = ", ".join(f"ch{c}: wanted {w}, got {a}" for c, (w, a) in sorted(bad.items()))
                raise RuntimeError(f"Spectrum {spec.name!r} did not load correctly: {detail}")

        if turn_on:
            self.on()
        self.current_spectrum = spec.name
        return spec

    def capture_spectrum(self, name: str, description: str = "", source: str = "",
                         notes: str = "", save: bool = True, overwrite: bool = False,
                         include_wavelengths: bool = True) -> Spectrum:
        """Read whatever spectrum is loaded on the Pico now and (optionally) save
        it to the library. Use this to export the web-UI presets: pick a preset
        in the Pico's web page, then call capture_spectrum('<preset name>')."""
        spec = Spectrum(
            name=name,
            channels=self.read_channels(),
            global_intensity=self.get_intensity(),
            description=description,
            source=source or f"Captured from Pico {self.pico_id} via API",
            pico_id=self.pico_id,
            created=datetime.now().astimezone().isoformat(timespec="seconds"),
            notes=notes,
            wavelengths_nm=({ch: self.wavelength_range(ch) for ch in self.channels}
                            if include_wavelengths else {}),
        )
        if save:
            self.library.add(spec, overwrite=overwrite)
        return spec

    def all_off(self) -> None:
        """Light off and every channel set to 0."""
        self.off()
        self.current_spectrum = None
        for ch in self.channels:
            if self._dev.set_channel_value(ch, 0) is not True:
                raise RuntimeError(f"Pico did not acknowledge clearing channel {ch}")
        if any(self.read_channels().values()):
            raise RuntimeError("Pico did not clear all channels")
