"""Command line:  python -m pico_lab <command> [options]

  status                     light on/off, intensity, last spectrum
  list                       spectra in the library
  show NAME                  print one spectrum's channel values
  apply NAME [--on] [--intensity %]
  on | off | alloff          alloff = light off and all channels 0
  intensity PERCENT
  capture NAME [--description ...] [--source ...] [--overwrite]
  capture-presets            guided export of the web-UI presets (interactive)

Global options: --config config.json  --ip ADDR  --id PICO_ID  --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .controller import PicoController
from .fake import FakePico
from .spectrum import SpectrumError


def build_parser():
    p = argparse.ArgumentParser(prog="python -m pico_lab", description="G2V Pico control")
    p.add_argument("--config", default="config.json", help="config file (default config.json)")
    p.add_argument("--ip", help="override ip_address from config")
    p.add_argument("--id", help="override pico_id from config")
    p.add_argument("--spectra-dir", help="override spectra_dir from config")
    p.add_argument("--dry-run", action="store_true", help="use a fake Pico, no hardware")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    sub.add_parser("list")
    s = sub.add_parser("show"); s.add_argument("name")
    a = sub.add_parser("apply"); a.add_argument("name")
    a.add_argument("--on", action="store_true", help="turn the light on after loading")
    a.add_argument("--intensity", type=float, help="global intensity %% (default: spectrum's)")
    sub.add_parser("on"); sub.add_parser("off"); sub.add_parser("alloff")
    i = sub.add_parser("intensity"); i.add_argument("percent", type=float)
    c = sub.add_parser("capture"); c.add_argument("name")
    c.add_argument("--description", default=""); c.add_argument("--source", default="")
    c.add_argument("--notes", default=""); c.add_argument("--overwrite", action="store_true")
    sub.add_parser("capture-presets")
    return p


def connect(args) -> PicoController:
    overrides = {"ip_address": args.ip, "pico_id": args.id, "spectra_dir": args.spectra_dir}
    if args.dry_run:
        overrides["device"] = FakePico()
    cfg = Path(args.config)
    if cfg.exists():
        return PicoController.from_config(cfg, **overrides)
    if not (args.ip and args.id):
        sys.exit(f"No {cfg} found - create it from config.example.json or pass --ip and --id")
    return PicoController(args.ip, args.id, spectra_dir=args.spectra_dir or "spectra",
                          device=overrides.get("device"))


def capture_presets(pico: PicoController) -> None:
    print("Guided preset export. For each preset:\n"
          "  1) select it in the Pico web page (same IP address) and apply it\n"
          "  2) type its name here exactly as shown in the web page\n"
          "Press Enter on an empty name to finish.\n")
    while True:
        name = input("Preset name: ").strip()
        if not name:
            break
        desc = input("  Description (optional): ").strip()
        try:
            spec = pico.capture_spectrum(name, description=desc,
                                         source=f"Pico web UI preset '{name}'")
        except FileExistsError:
            if input("  Already saved. Overwrite? [y/N] ").lower() != "y":
                continue
            spec = pico.capture_spectrum(name, description=desc,
                                         source=f"Pico web UI preset '{name}'", overwrite=True)
        nonzero = sum(1 for v in spec.channels.values() if v)
        print(f"  Saved {spec.path.name}: {nonzero}/{len(spec.channels)} channels non-zero, "
              f"intensity {spec.global_intensity}%")
    print(f"Library now has {len(pico.library)} spectra.")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with connect(args) as pico:
            if args.cmd == "status":
                print(json.dumps(pico.status(), indent=2))
            elif args.cmd == "list":
                for spec in pico.library:
                    print(f"{spec.name:30s} {spec.description}")
                for fname, err in pico.library.errors.items():
                    print(f"[skipped] {fname}: {err}", file=sys.stderr)
                if not len(pico.library):
                    print(f"(no spectra in {pico.library.folder})")
            elif args.cmd == "show":
                spec = pico.library.get(args.name)
                print(f"{spec.name}  intensity={spec.global_intensity}%  source={spec.source}")
                for ch, v in sorted(spec.channels.items()):
                    print(f"  ch{ch:>2}: {v}")
            elif args.cmd == "apply":
                spec = pico.apply_spectrum(args.name, turn_on=args.on, intensity=args.intensity)
                print(f"Loaded {spec.name!r}; light is {'ON' if pico.is_on() else 'off'}")
            elif args.cmd == "on":
                pico.on(); print("Light ON")
            elif args.cmd == "off":
                pico.off(); print("Light off")
            elif args.cmd == "alloff":
                pico.all_off(); print("Light off, all channels 0")
            elif args.cmd == "intensity":
                pico.set_intensity(args.percent); print(f"Intensity {args.percent}%")
            elif args.cmd == "capture":
                spec = pico.capture_spectrum(args.name, description=args.description,
                                             source=args.source, notes=args.notes,
                                             overwrite=args.overwrite)
                print(f"Saved {spec.path}")
            elif args.cmd == "capture-presets":
                capture_presets(pico)
    except (SpectrumError, FileExistsError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
