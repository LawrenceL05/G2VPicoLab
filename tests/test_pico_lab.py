"""Run with:  python -m pytest tests   (no hardware needed - uses SimulatedPico)"""
import json

import pytest

from pico_lab import SimulatedPico, PicoController, Spectrum, SpectrumError, SpectrumLibrary
from pico_lab.__main__ import main


def make(tmp_path, **kw):
    return PicoController("0.0.0.0", "0000000000000000", spectra_dir=tmp_path,
                          device=SimulatedPico(**kw))


def spec(name="Test", **channels):
    return Spectrum(name=name, channels={int(k[2:]): v for k, v in channels.items()},
                    global_intensity=80.0)


def test_save_load_roundtrip(tmp_path):
    s = spec("AM1.5G", ch1=112, ch2=535)
    s.wavelengths_nm = {1: [395, 405]}
    path = s.save(tmp_path / "am.json")
    data = json.loads(path.read_text())
    assert data["units"] == "pwm" and data["channels"][0] == {
        "channel": "1", "value": 112, "wavelength_nm": [395, 405]}
    back = Spectrum.load(path)
    assert back.channels == {1: 112, 2: 535} and back.global_intensity == 80.0


def test_bare_g2v_list_is_accepted(tmp_path):
    (tmp_path / "g2v_example.json").write_text(json.dumps(
        [{"channel": "1", "value": 10}, {"channel": "2", "value": 0}]))
    lib = SpectrumLibrary(tmp_path)
    assert lib.get("G2V_EXAMPLE").channels == {1: 10, 2: 0}


@pytest.mark.parametrize("bad", [
    {"name": "x", "channels": []},
    {"name": "x", "channels": [{"channel": "1", "value": 5000}]},
    {"name": "x", "channels": [{"channel": "1", "value": 1}, {"channel": "1", "value": 2}]},
    {"name": "x", "channels": [{"channel": "1", "value": 1}], "global_intensity": 150},
    {"name": "x", "units": "mA", "channels": [{"channel": "1", "value": 1}]},
])
def test_bad_files_are_skipped_not_fatal(tmp_path, bad):
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    (tmp_path / "good.json").write_text(json.dumps({"name": "Good", "channels": [{"channel": "1", "value": 1}]}))
    lib = SpectrumLibrary(tmp_path)
    assert lib.names() == ["Good"] and "bad.json" in lib.errors


def test_unknown_name_lists_available(tmp_path):
    pico = make(tmp_path)
    pico.library.add(spec("A", ch1=1))
    with pytest.raises(SpectrumError, match="Available: A"):
        pico.apply_spectrum("nope")


def test_apply_turns_off_first_zeroes_others_and_verifies(tmp_path):
    pico = make(tmp_path)
    dev = pico._dev
    dev._values[5] = 999            # leftover from a previous spectrum
    dev._on = True
    pico.library.add(spec("A", ch1=100, ch2=200))
    pico.apply_spectrum("a")       # case-insensitive
    assert dev.log[0] == ("turn_off",)
    assert all(not on for (cmd, *rest) in dev.log if cmd == "set_channel_value" for on in rest[-1:])
    assert dev._values[1] == 100 and dev._values[2] == 200 and dev._values[5] == 0
    assert dev._intensity == 80.0 and not dev._on
    assert pico.current_spectrum == "A"


def test_apply_turn_on_and_intensity_override(tmp_path):
    pico = make(tmp_path)
    pico.apply_spectrum(spec("B", ch3=50), turn_on=True, intensity=25)
    assert pico.is_on() and pico.get_intensity() == 25


def test_rejects_unknown_channel_and_over_limit(tmp_path):
    pico = make(tmp_path, channel_count=4, limit=1000)
    with pytest.raises(SpectrumError, match="doesn't have"):
        pico.apply_spectrum(spec("C", ch9=1))
    with pytest.raises(SpectrumError, match="limit"):
        pico.apply_spectrum(spec("D", ch1=2000))
    assert not any(c[0] == "set_channel_value" for c in pico._dev.log)  # nothing touched


def test_verify_catches_device_refusal(tmp_path):
    pico = make(tmp_path)
    pico._dev.set_channel_value = lambda ch, v: False   # device ignores writes
    with pytest.raises(RuntimeError, match="did not load"):
        pico.apply_spectrum(spec("E", ch1=10))


def test_capture_saves_current_state(tmp_path):
    pico = make(tmp_path)
    pico._dev._values.update({1: 11, 2: 22})
    pico._dev._intensity = 60.0
    s = pico.capture_spectrum("AM0", description="space")
    assert (tmp_path / "am0.json").exists()
    back = SpectrumLibrary(tmp_path).get("am0")
    assert back.channels[1] == 11 and back.global_intensity == 60.0
    assert back.wavelengths_nm[1] == [350, 370] and back.pico_id == "0000000000000000"
    with pytest.raises(FileExistsError):
        pico.capture_spectrum("AM0")


def test_all_off(tmp_path):
    pico = make(tmp_path)
    pico.apply_spectrum(spec("F", ch1=10), turn_on=True)
    pico.all_off()
    assert not pico.is_on() and set(pico.read_channels().values()) == {0}


def test_cli_dry_run(tmp_path, capsys):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"ip_address": "x", "pico_id": "0000000031a0525e",
                               "spectra_dir": "spectra"}))
    Spectrum(name="AM1.5G", channels={1: 5}).save(tmp_path / "spectra" / "am15g.json")
    assert main(["--config", str(cfg), "--dry-run", "list"]) == 0
    assert "AM1.5G" in capsys.readouterr().out
    assert main(["--config", str(cfg), "--dry-run", "apply", "am1.5g", "--on"]) == 0
    assert "ON" in capsys.readouterr().out
    assert main(["--config", str(cfg), "--dry-run", "apply", "missing"]) == 1
