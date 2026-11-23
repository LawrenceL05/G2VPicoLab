# pico_lab: G2V Pico spectrum wrapper

## Next lab task

Use the [one-sun distance workflow](WORKING_DISTANCE_WORKFLOW.md) to find the
sample plane where the reference sample matches its calibrated one-sun current.
The procedure uses the existing controller, manual multimeter readings, a coarse
and fine distance sweep, and repeat measurements. Record the raw measurements
with the [CSV template](results/working-distance-template.csv).

## Lab session on November 17, 2026

Use the [hardware workflow](LAB_WORKFLOW.md) for setup, connection checks,
preset capture, verified spectrum application and an approved illumination test.
Record observations in the [lab results sheet](results/2026-11-17.md).
The lab workflow uses Python 3.11 and the pinned requirements files.

On November 17, the wrapper captured and replayed the real Pico's
`am1.5g.0.1suns` preset. All 32 channel values matched. The Pico confirmed
illumination on and then off in the 10-second test. Irradiance remains unmeasured.

A Python wrapper around G2V's official `g2vpico` library (v1.0.9) that:

- keeps a **library of spectra**: a folder with one JSON file per spectrum
- **loads a spectrum by name** onto the Pico, safely
- turns the light **on/off** and sets the **global intensity**
- **captures** whatever is on the Pico into a new spectrum file (used to export the ~20 web-UI presets)

## Files

```
G2VPicoLab/
├── pico_lab/
│   ├── controller.py    PicoController: the main class
│   ├── spectrum.py      Spectrum + SpectrumLibrary (JSON files)
│   ├── simulator.py     SimulatedPico for offline tests and --dry-run
│   └── __main__.py      command line: python -m pico_lab ...
├── spectra/             spectrum JSON files go here
├── tests/               python -m pytest tests
├── config.json          Pico IP address and ID (copy of config.example.json)
└── example_usage.py
```

## Setup

Use the same Python environment where `g2vpico` already works (the `.venv` from
`g2vpico-windows-setup`), or install it:

```
python -m pip install -r requirements-dev.txt
```

Check `config.json` has the current Ethernet IP address and the 16-character Pico ID
(both are on the Pico control box; see the setup README). Then, from the `G2VPicoLab` folder:

```
python -m pico_lab status
```

## Python use

```python
from pico_lab import PicoController

with PicoController.from_config("config.json") as pico:
    print(pico.list_spectra())
    pico.apply_spectrum("AM1.5G")                 # loads it, light stays OFF
    pico.on()
    # ... measure ...
    pico.apply_spectrum("AM0", turn_on=True, intensity=50)
    pico.off()
```

In a notebook, create the controller once (`pico = PicoController.from_config("config.json")`)
and reuse it, as with the original connection cell.

| Method | What it does |
|---|---|
| `list_spectra()` | names in the library |
| `apply_spectrum(name, turn_on=False, intensity=None, verify=True)` | load a spectrum (see "Safety") |
| `on()` / `off()` / `is_on()` | light control; channel values are kept |
| `set_intensity(pct)` / `get_intensity()` | global intensity 0–100 %, takes effect immediately |
| `read_channels()` | current PWM value of every channel |
| `capture_spectrum(name, description=...)` | save the Pico's current spectrum to the library |
| `all_off()` | light off and every channel set to 0 |
| `status()` | dict: light on, intensity, last applied spectrum |
| `close()` | close the connection (does **not** turn the light off) |

## Command line

```
python -m pico_lab list
python -m pico_lab show AM1.5G
python -m pico_lab apply AM1.5G --on --intensity 80
python -m pico_lab off
python -m pico_lab capture "My spectrum" --description "..."
python -m pico_lab capture-presets
python -m pico_lab --dry-run apply AM1.5G       # use the in-memory simulator
```

## Exporting the web-UI presets (building the library)

1. Open the Pico web page (same IP address) in a browser.
2. Run `python -m pico_lab capture-presets`.
3. For each preset: select and apply it in the web page, then type its name at the prompt.
   The script reads all 32 channel values, the global intensity and each channel's
   wavelength range, and writes `spectra/<name>.json`.
4. Press Enter on an empty name to finish. Run `python -m pico_lab list` to check.

## Spectrum file format

```json
{
  "schema_version": 1,
  "name": "AM1.5G",
  "description": "Pico web-UI preset",
  "units": "pwm",
  "pwm_max": 4096,
  "global_intensity": 100.0,
  "channels": [
    {"channel": "1", "value": 112, "wavelength_nm": [395, 405]},
    {"channel": "2", "value": 535, "wavelength_nm": [405, 415]}
  ],
  "source": "Pico web UI preset 'AM1.5G'",
  "pico_id": "0000000000000000",
  "channel_count": 32,
  "created": "2026-11-16T16:30:00-08:00",
  "notes": ""
}
```

- Values are raw **PWM counts (0–4096)**, as agreed with Eric. They are not currents.
- Only `name` and `channels` are required. Channels left out are set to 0 when applied.
- Names are matched case-insensitively. A bad or duplicate file is skipped with a message,
  not a crash.
- A bare G2V list like their `test_spectrum.json` is also accepted.
- The `wavelength_nm` values are illustrative above; real ones come from the Pico.

## Safety: what `apply_spectrum` does

1. Checks every channel exists on this Pico and is within that channel's limit. Nothing
   is sent if the check fails.
2. Turns the light **off**, so the sample never sees a half-updated spectrum.
3. Writes all 32 channels. Channels not in the file are set to **0**. G2V's own
   `set_spectrum` leaves them unchanged, which can leave leftovers from the previous spectrum.
4. Sets the global intensity (the spectrum's own, or `intensity=` if given).
5. Reads every channel back and raises an error if any value doesn't match.
6. Turns the light on only if `turn_on=True`.

Command refusals and missing acknowledgments raise errors. The wrapper checks the
fixture state after on/off commands and reads back intensity after an intensity
change. It validates intensity overrides before changing the device. A failed
apply clears the last-applied spectrum once channel updates begin, and leaves
the fixture off if the initial off command succeeded.

Channel identifiers and PWM values must be integers (native integer strings are
accepted in JSON). Fractional and Boolean values are rejected. Malformed files
are recorded in the library's errors without hiding valid spectra. Overwriting
an existing spectrum preserves its filename. Saves publish a complete file and
reject filename collisions with a different spectrum.

## To verify on hardware

- [x] API status connects through the wired socket override and reports 32 channels.
- [ ] Channel values written while the light is off are kept and used by `on()`. G2V's
      docs say `turn_on` uses the stored spectrum.
- [ ] Choosing a preset in the web page changes the values the API reads back, so
      `capture` actually sees the preset. If not, use Eric's other route: open the
      Pico code and save the spectra dict.
- [x] Per-channel limits (`get_channel_limit`) were read for all 32 channels, ranging
      from 1190 to 3300 PWM. Named presets still need checks against these limits.
- [ ] Timing: applying 32 channels plus verifying is about 70 small requests. Check
      this is fast enough. One verified all-zero replay took 0.579 seconds.

## Tests

```
python -m pytest tests
```

These use `SimulatedPico`, so they run on any computer without the Pico.
