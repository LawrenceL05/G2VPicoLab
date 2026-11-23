# One-sun working-distance measurement

Find the distance where the reference sample produces its calibrated one-sun current. Use the existing Pico controller for illumination and the multimeter for manual measurements.

## 1. Record the reference and the decision rule

Complete this table before illumination. Use the sample certificate, the device manual, and Eric's lab protocol.

| Field | Session value |
| --- | --- |
| Date, operator, repository commit, Python environment | |
| Reference sample model, serial number, active area | |
| Certificate or datasheet and calibration date | |
| Calibrated current at one sun, with unit and sign | |
| Calibration spectrum and reference temperature | |
| Calibration uncertainty | |
| Electrical condition for the calibrated current | |
| Temperature correction equation, if required | |
| Current tolerance for acceptance | |
| Repeatability tolerance and required repeat count | |
| Pico model and serial number | |
| Optical reference surface for distance, with photo | |
| Initial distance, permitted range, coarse step, fine step | |
| Spectrum name, saved JSON filename, global intensity percent | |
| Warmup procedure, settle time, exposure time, rest time | |
| Multimeter model, range, resolution, accuracy, burden specification | |
| Lead terminals, polarity, wiring diagram, meter mode | |

Define distance along the optical axis from the documented fixture reference surface to the sample's active surface. Measure the active surface height, not the holder height.

G2V lists a nominal working distance of 7 cm for the Pico product. Confirm the lab unit's reference surface and calibration geometry before you use 70 mm as the starting point. The manufacturer specification alone does not establish the correct distance for this fixture.

Use the calibrated current as the target. For a short-circuit reference current, use the certificate's short-circuit measurement condition. Account for the meter burden voltage and lead resistance. If the sample has an integrated shunt or conditioned output, follow its specified readout method.

A standard current at one sun supports an irradiance estimate only under the reference sample's calibration conditions. Spectrum, temperature, and measurement load affect the result. If these conditions differ, resolve the mismatch before you attribute the current error to distance.

## 2. Prepare the software and the measurement circuit

1. Follow the connection and Ethernet checks in [the hardware workflow](LAB_WORKFLOW.md).
2. Activate the Python environment with the pinned vendor package.
3. Record the repository commit.
4. Run the offline tests.
5. Check the live API status.
6. Confirm the physical off state.
7. Record the fixture's initial spectrum and intensity.
8. Connect the reference sample according to its certificate and the meter manual.
9. Record a diagram or photo of the circuit.

From the repository root, use the same verified interpreter for all commands.

```powershell
python -m pytest tests -q
python -m pico_lab status
python -m pico_lab list
```

For a direct current measurement, confirm that the sample permits this connection. Use the correct fused current input and a range that covers the expected current. An unsuitable input or range can damage the meter or sample. For a conditioned voltage output, use its specified voltage measurement circuit.

Keep the lamp off during changes to the circuit or sample position. Use the existing lab enclosure and physical off control from the hardware workflow.

## 3. Select and verify one fixed illumination setting

1. Select the saved spectrum that matches the reference calibration.
2. Inspect the spectrum with `python -m pico_lab show NAME`.
3. Record its channel values and global intensity.
4. Use the same spectrum and global intensity throughout the distance sweep.
5. Complete the lab warmup procedure.

The November 17 test used `am1.5g.0.1suns`. That name denotes a 0.1-sun preset. Choose the reference-compatible one-sun recipe for this experiment. If the local library lacks that recipe, capture the correct web preset through the existing capture workflow.

Global intensity 100% means the full scale of the loaded recipe. It does not establish one sun. The reference current supplies the measurement target.

The controller's `apply_spectrum()` method checks the channel limits and verifies the stored values. API verification establishes the electrical settings of the Pico. The reference measurement establishes the response at the sample plane.

## 4. Measure the dark current and the initial point

1. Center the active area on the optical axis.
2. Set the active surface perpendicular to the optical axis.
3. Set the initial distance from the recorded reference surface.
4. Record the sample temperature, if an instrument is available.
5. Confirm that the light is off.
6. Record at least three dark readings with timestamps.
7. Enable the fixed illumination setting for the agreed exposure.
8. Wait for the agreed settle interval.
9. Record at least three light readings at the agreed cadence.
10. Disable illumination.
11. Confirm the physical off state.
12. Record any drift, meter overload, alignment change, or contact problem.

Keep the settle interval and the total exposure consistent across distances. If the current still drifts at the end of the interval, mark the point unstable. Resolve the warmup or thermal behavior before the comparison.

Use the following code for one timed exposure. Enter the spectrum name, fixed intensity, and agreed timing before the hardware connection. Read the multimeter manually during the acquisition window.

Save this snippet as a local session script in the repository root. Run it with the verified interpreter. If the connection needs the per-process Ethernet override, apply that same verified override in this session as described in the hardware workflow.

```python
import math
import time
from datetime import datetime

from pico_lab import PicoController

spectrum = input("Reference-compatible spectrum name: ").strip()
intensity = float(input("Fixed global intensity (%): "))
settle_s = float(input("Agreed settle interval (seconds): "))
read_s = float(input("Agreed acquisition window (seconds): "))
if not spectrum:
    raise ValueError("A spectrum name is required")
if not math.isfinite(intensity) or not 0 <= intensity <= 100:
    raise ValueError("Intensity must be finite and between 0 and 100")
if not math.isfinite(settle_s) or settle_s < 0:
    raise ValueError("Settle interval must be finite and nonnegative")
if not math.isfinite(read_s) or read_s <= 0:
    raise ValueError("Acquisition window must be finite and positive")

with PicoController.from_config("config.json") as pico:
    try:
        pico.apply_spectrum(spectrum, intensity=intensity, verify=True)
        print("Verified settings", pico.status(), flush=True)
        pico.on()
        print("Light enabled", datetime.now().astimezone().isoformat(), flush=True)
        time.sleep(settle_s)
        print("Record multimeter readings now", flush=True)
        time.sleep(read_s)
    finally:
        pico.off()
        print("Light disabled", pico.status(), flush=True)
```

The script controls one exposure. It does not read the multimeter. A controller error, a lost connection, or a terminated process can prevent software shutdown. If off confirmation fails, use the physical off control and stop the sweep.

## 5. Perform a coarse sweep, then a fine sweep

1. Calculate the normalized response at the initial distance with the equations below.
2. Select the next distance within the permitted range.
3. Confirm the physical off state before sample movement.
4. Measure the new distance.
5. Repeat the dark and light measurements from Section 4.
6. Repeat the initial distance after a few points to check drift.
7. Continue until the stable measurements bracket the target response.
8. Test smaller distance steps within that bracket.
9. Repeat the candidate distance after a fresh approach from each direction.
10. Repeat the initial distance at the end of the session.

Use three repeat exposures per distance as a planning default. Confirm the count and the tolerances with Eric before the session. Within-exposure readings measure temporal variation. Repeat exposures measure repeatability across separate illumination cycles.

If Eric confirms 70 mm as the initial point, a possible coarse sequence is 70, 75, 65, 80, and 60 mm. Use only distances within the unit's permitted range. Refine a bracket with 1 mm steps if the mount supports that resolution. These distances are proposed trial points, not measured results.

Keep the sample, spectrum, intensity, alignment, meter mode, range, exposure, and readout cadence fixed. Record any required deviation as a new condition.

If the target lies outside the permitted range, stop the distance search. Check the recipe, calibration conditions, wiring, and sample condition with Eric. Treat a later intensity adjustment as a separate experiment.

## 6. Calculate the response and select the distance

For a certificate that defines a net photocurrent, calculate the corrected response.

```text
I_net = mean(I_light) - mean(I_dark)
R = I_net / I_reference
target_error_percent = 100 * (R - 1)
```

Preserve the raw signed readings and their units. Apply the certificate's sign convention and temperature correction before the comparison. If the certificate defines a different response, use that definition and document it.

Under matching spectral conditions and a valid linear reference-cell calibration, the estimated irradiance ratio is approximately R. A one-sun reference corresponds to 1000 W/m^2 for the applicable AM1.5G calibration. Retain the certificate's reference irradiance when it differs.

1. Calculate the mean and spread for each exposure.
2. Calculate the mean and spread across repeat exposures at each distance.
3. Plot the corrected current against distance with repeat variation.
4. Mark the calibrated target and its uncertainty.
5. Compare the measured variation with the agreed tolerance and instrument uncertainty.
6. Select a repeatable distance that meets the target tolerance.
7. Report the distance as inconclusive if uncertainty or drift prevents a choice.

The acceptance condition for the current target is `abs(target_error_percent) <= agreed_tolerance_percent`. Apply the separate repeatability criterion from the session table as well.

Record the selected distance with the mount resolution and reposition variation. If several distances meet the criteria, report the acceptable interval. Avoid a false precision that exceeds the measurement capability.

A single sample at the center checks its response over its active area. To assess spatial uniformity, scan a sufficiently small calibrated detector over the required area as a separate follow-up. This sweep establishes a working distance for the stated sample and conditions.

## 7. Save the evidence and finish

1. Copy [the blank measurement CSV](results/working-distance-template.csv) to a unique session filename.
2. Enter one row per raw meter reading.
3. Enter `dark`, `settle`, or `light` in the phase column.
4. Preserve overloaded or unstable readings with their status and reason.
5. Save the completed session table with the raw data.
6. Save the plot and the selected-distance rationale.
7. Save the exact spectrum JSON and code revision with the session evidence.
8. Disable illumination.
9. Confirm the API and physical off states.
10. Record the final distance, fixture state, and next action.

Keep local device configuration and credentials outside Git. Share the measurement data, sample identifiers, and photos according to the lab's existing data policy.

The result should state the calibrated target, measured current, repeat variation, selected distance or interval, optical reference surface, spectrum, intensity, temperature information, and unresolved uncertainty. Record unperformed checks as NOT RUN.

## Sources

- [Existing Pico hardware workflow](LAB_WORKFLOW.md)
- [November 17 hardware record](results/2026-11-17.md)
- [Pico controller implementation](pico_lab/controller.py)
- [G2V Pico product specifications](https://g2voptics.com/products/led-solar-simulator-pico/)
- [Reference-cell linearity and calibration context](https://www.nlr.gov/pv/pvdpc/cell-measurements)
