# First Pico hardware test

Planned session: November 17, 2026. Operator: Lawrence Li.

Goal: verify the wrapper on the real G2V Pico, capture a web preset, apply its
PWM values with illumination off, and test controlled on/off operation.

Current evidence: 63 automated tests passed locally with a simulated device.
Physical-device tests remain pending. Record the actual session in
[the results sheet](results/2026-11-17.md).

## 1. Prepare the computer before lab

Use PowerShell and Python 3.11. On this computer, open the existing folder:

```powershell
Set-Location 'C:\Users\Lawrence Li\G2VPicoLab'
```

On another computer, clone the repository first:

```powershell
git clone https://github.com/LawrenceL05/G2VPicoLab.git
cd G2VPicoLab
```

Create a dedicated environment and install the pinned vendor source and tests:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Expected result: 63 tests pass. If installation or a test fails, resolve that
failure before the hardware steps. The requirements pin the vendor commit
whose MainClass.py matches the previously tested local installation.

Create a configuration only if one does not exist:

```powershell
if (-not (Test-Path config.json)) { Copy-Item config.example.json config.json }
notepad config.json
```

Set the actual wired Pico IP address and its exact 16-character ID, including
leading zeros. Keep the ID as a JSON string. Keep timeout_s at 20 initially.
The config file and captured spectra are excluded from Git by default.

```powershell
.\.venv\Scripts\python.exe -m pico_lab --dry-run status
```

Expected result: a simulated device reports light_on=false and 32 channels.
Those simulated values do not confirm the hardware connection.

## 2. Connect in lab

1. Ask Eric to confirm the intended Pico, permitted illumination level and
   physical off control. Prepare the normal lab enclosure and sample arrangement.
2. Read the Pico IP address, subnet mask and ID from its control box.
3. Connect the dedicated Ethernet cable. Configure that adapter with a different
   IPv4 address in the same subnet. Use the device's actual mask.
4. Enable API access and start the Pico control software.
5. Update config.json with the observed values.

Check TCP connectivity:

```powershell
$picoConfig = Get-Content config.json -Raw | ConvertFrom-Json
Test-NetConnection -ComputerName $picoConfig.ip_address -Port 50000
```

Expected result: TcpTestSucceeded is True. A reachable web page alone does not
confirm the API port. If this fails, check cable, adapter/subnet, control
software and API enablement before issuing wrapper commands.

Optionally record the terminal session locally:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
Start-Transcript -Path logs\2026-11-17-session.txt
git rev-parse HEAD
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip freeze
```

## 3. Read-only API check

```powershell
.\.venv\Scripts\python.exe -m pico_lab status
```

Record the reported channel count, fixture state and global intensity. Compare
them with the web interface. This command does not change channel values or
illumination. A connection timeout, invalid ID, JSON error or mismatched values
means this step failed. Record the error before any write test.

## 4. Capture the starting state and one preset

Capture the current channels and global intensity before changing them:

```powershell
.\.venv\Scripts\python.exe -m pico_lab capture lab_original_20261117 --description "Starting lab state before wrapper tests"
```

Expected result: spectra/lab_original_20261117.json exists with channel PWM
values, intensity, timestamp, device ID and wavelength metadata. The file
records the spectrum and intensity. It does not record the fixture on/off state,
so record that separately in the results sheet.

1. Select a known preset in the Pico web interface with Eric's approval.
   Applying a web preset may change illumination immediately.
2. Capture that preset:

```powershell
.\.venv\Scripts\python.exe -m pico_lab capture lab_test_20261117 --description "Known web preset for first hardware verification"
.\.venv\Scripts\python.exe -m pico_lab off
.\.venv\Scripts\python.exe -m pico_lab status
```

Expected result: capture succeeds and the final status reports light_on=false.
If off fails, use the physical control and stop the write tests.

Compare at least three channels, including a nonzero channel, and the intensity
in the saved JSON against the web UI. If possible, repeat with a second preset
whose values differ. This establishes that capture follows the selected preset.
Do not label unchanged or mismatched data as a successful preset export.

If a capture name already exists, inspect it first. Choose a new name or use
--overwrite only when replacement is intended.

## 5. Apply the captured spectrum with the fixture off

```powershell
.\.venv\Scripts\python.exe -m pico_lab apply lab_test_20261117
.\.venv\Scripts\python.exe -m pico_lab status
```

Expected result: the apply succeeds and light_on remains false. The wrapper
checks channel IDs and limits, confirms off, writes every channel, verifies
intensity and reads every channel back. Compare the stored settings with the
web UI. With the sample shielded and operator approval, start from a different
known preset and repeat this step so the test exercises actual channel changes.

Apply does not enable illumination unless --on is supplied. A partial write
failure can leave a partial stored spectrum. Stop and inspect the error before
any later on command. The context manager closes the socket without switching
the fixture off automatically.

## 6. Controlled illumination test

Complete this step only after Steps 3-5 pass and Eric approves the optical
arrangement and test intensity. Enter an approved value from 0 to 100 when
prompted. Use one Python session so the finally block attempts to switch the
fixture off after the observation.

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
@'
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pico_lab import PicoController

level = float(input("Eric-approved test intensity (%): "))
if not math.isfinite(level) or not 0 <= level <= 100:
    raise ValueError("Intensity must be a finite number from 0 to 100")

with PicoController.from_config("config.json") as pico:
    try:
        pico.apply_spectrum("lab_test_20261117", intensity=level)
        stored = pico.read_channels()
        pico.on()
        print("State while on:", pico.status())
        if pico.read_channels() != stored:
            raise RuntimeError("Channel PWM values changed after on()")
        input("Confirm illumination and web-UI agreement, then press Enter to switch off: ")
    finally:
        pico.off()
        print("State after off:", pico.status())
'@ | Set-Content -Encoding utf8 logs\hardware_check.py
.\.venv\Scripts\python.exe logs\hardware_check.py
```

Expected result: on/off acknowledgments succeed, the API and UI agree, stored
PWM values persist, and the fixture is visibly off at the end. API readback
checks command behavior. Absolute spectral output and irradiance require an
appropriate physical measurement.

If the process is killed, the computer disconnects, or off raises an error,
the finally block cannot guarantee shutdown. Use the physical off control.

## 7. Validate limits and record timing

Read channel limits without exceeding them. Do not deliberately send excessive
PWM to the hardware. The automated tests already cover invalid-value rejection.

```powershell
@'
from pico_lab import PicoController
with PicoController.from_config("config.json") as pico:
    print({ch: pico.channel_limit(ch) for ch in pico.channels})
'@ | .\.venv\Scripts\python.exe -
```

Time a verified application while the fixture remains off:

```powershell
Measure-Command { .\.venv\Scripts\python.exe -m pico_lab apply lab_test_20261117 }
```

Record elapsed time and whether the command actually succeeded. Run three
applications if stable. Timing includes connection and command-line overhead.
The 20-second setting is per socket operation, not a total workflow deadline.

## 8. Finish and record the result

```powershell
.\.venv\Scripts\python.exe -m pico_lab off
.\.venv\Scripts\python.exe -m pico_lab status
```

Verify the physical light is off. If the lab wants the original stored spectrum
restored, apply lab_original_20261117 without --on after the test passes. Confirm
off again. Use alloff only when clearing every stored PWM value is intended.

If a transcript is active:

```powershell
Stop-Transcript
```

Fill in the results sheet. Record unperformed tests as NOT RUN. A hardware pass
requires the read-only connection, capture agreement, verified off-state apply,
approved on/off observation, and final off confirmation. Export the remaining
web presets with capture-presets after these checks succeed.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Port 50000 unavailable | Cable, dedicated adapter, address/mask, API enablement, control software |
| Invalid Pico ID | Exact 16 characters, leading zeros and correct connected unit |
| Timeout, truncated JSON or JSON decode error | Record the exception and last successful operation. Reconnect after confirming physical off. The vendor API assumes each response fits one TCP recv call, so transport errors need diagnosis. |
| Capture differs from the web preset | Confirm the web preset was applied to this unit. Compare changed channels. If API state still differs, use Eric's suggested preset-code export route. |
| Channel limit or readback mismatch | Keep the light off. Record channel, requested value, limit and returned value. |
| Intensity acknowledgment/readback failure | Record requested and returned intensity. Investigate device rounding and protocol behavior before changing verification tolerance. |
| Refused on/off command | Stop the test. Check physical fixture state with the lab operator. |

Protocol reference: the pinned [G2V Python API source](https://github.com/g2v-optics/G2VPico/tree/c8800d28867f4e04d89a0b2d58195b7965f7f874).
