"""Example: step through every spectrum in the library.

Run from the G2VPicoLab folder:   python example_usage.py
Add --dry-run to try it without the Pico.
"""
import sys
import time

from pico_lab import SimulatedPico, PicoController

DRY_RUN = "--dry-run" in sys.argv
overrides = {"device": SimulatedPico()} if DRY_RUN else {}

with PicoController.from_config("config.json", **overrides) as pico:
    print(pico, pico.status())
    names = pico.list_spectra()
    if not names:
        sys.exit("No spectra yet - run:  python -m pico_lab capture-presets")

    try:
        for name in names:
            pico.apply_spectrum(name, turn_on=True)
            print(f"{name}: on at {pico.get_intensity()}%")
            time.sleep(2)          # <- replace with your measurement
    finally:
        pico.off()                 # always leave the light off
        print("Light off")
