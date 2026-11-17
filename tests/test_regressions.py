"""Regression checks for device failures and persistent spectrum libraries."""
import json

import pytest

from pico_lab import FakePico, PicoController, Spectrum, SpectrumError, SpectrumLibrary
from pico_lab.__main__ import main
from pico_lab import spectrum as spectrum_module


@pytest.fixture
def pico(tmp_path):
    return PicoController("unused", "0" * 16, spectra_dir=tmp_path,
                          device=FakePico(channel_count=2))


@pytest.mark.parametrize("result", [False, None])
@pytest.mark.parametrize("operation", ["apply", "all_off"])
def test_failed_off_prevents_channel_writes(pico, monkeypatch, result, operation):
    pico._dev._on = True
    monkeypatch.setattr(pico._dev, "turn_off", lambda: result)
    with pytest.raises(RuntimeError, match="light-off"):
        if operation == "apply":
            pico.apply_spectrum(Spectrum("test", {1: 12}))
        else:
            pico.all_off()
    assert pico._dev.log == []
    assert pico._dev._on is True


def test_acknowledged_off_still_requires_off_state(pico, monkeypatch):
    pico._dev._on = True
    monkeypatch.setattr(pico._dev, "turn_off", lambda: True)
    with pytest.raises(RuntimeError, match="did not turn the light off"):
        pico.apply_spectrum(Spectrum("test", {1: 12}))
    assert pico._dev.log == []


@pytest.mark.parametrize("result", [False, None])
def test_refused_intensity_prevents_light_on(pico, monkeypatch, result):
    monkeypatch.setattr(pico._dev, "set_global_intensity", lambda value: result)
    with pytest.raises(RuntimeError, match="intensity command"):
        pico.apply_spectrum(Spectrum("test", {1: 12}, global_intensity=10), turn_on=True)
    assert not pico.is_on()
    assert pico.current_spectrum is None
    assert ("turn_on",) not in pico._dev.log


def test_intensity_readback_must_match(pico, monkeypatch):
    monkeypatch.setattr(pico._dev, "set_global_intensity", lambda value: True)
    with pytest.raises(RuntimeError, match="Intensity did not match"):
        pico.apply_spectrum(Spectrum("test", {1: 12}), intensity=10, turn_on=True)
    assert not pico.is_on()


@pytest.mark.parametrize("value", [101, -1, "invalid", None, True, float("nan"), float("inf")])
def test_set_intensity_rejects_invalid_input_without_writes(pico, value):
    with pytest.raises(ValueError):
        pico.set_intensity(value)
    assert pico._dev.log == []


@pytest.mark.parametrize("value", [101, -1, "invalid", True, float("nan")])
def test_invalid_override_preserves_existing_state(pico, value):
    pico._dev._on = True
    pico._dev._values[1] = 777
    with pytest.raises(ValueError):
        pico.apply_spectrum(Spectrum("test", {1: 12}), intensity=value)
    assert pico._dev._on
    assert pico._dev._values[1] == 777
    assert pico._dev.log == []


@pytest.mark.parametrize("result", [False, None])
def test_failed_channel_write_is_rejected_even_without_readback(pico, monkeypatch, result):
    monkeypatch.setattr(pico._dev, "set_channel_value", lambda ch, value: result)
    with pytest.raises(RuntimeError, match="not acknowledged"):
        pico.apply_spectrum(Spectrum("test", {1: 12}), verify=False, turn_on=True)
    assert not pico.is_on()
    assert pico.current_spectrum is None


def test_partial_failure_clears_last_spectrum(pico, monkeypatch):
    pico.apply_spectrum(Spectrum("old", {1: 99}))
    original = pico._dev.set_channel_value

    def fail_second(ch, value):
        if ch == 2:
            raise TimeoutError("injected timeout")
        return original(ch, value)

    monkeypatch.setattr(pico._dev, "set_channel_value", fail_second)
    with pytest.raises(TimeoutError):
        pico.apply_spectrum(Spectrum("new", {1: 22, 2: 33}))
    assert pico.current_spectrum is None
    assert not pico.is_on()


@pytest.mark.parametrize("command,method", [("on", "turn_on"), ("off", "turn_off"),
                                            ("intensity", "set_global_intensity")])
def test_cli_reports_device_refusal(pico, monkeypatch, capsys, command, method):
    import pico_lab.__main__ as cli
    monkeypatch.setattr(cli, "connect", lambda args: pico)
    monkeypatch.setattr(pico._dev, method, lambda *args: False)
    argv = [command, "10"] if command == "intensity" else [command]
    assert main(argv) == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("bad", [
    {"channels": None}, {"channels": {}}, {"channels": [None]},
    {"channels": [{"channel": 1, "value": 12}], "global_intensity": {}},
    {"channels": [{"channel": 1, "value": 12, "wavelength_nm": 7}]},
    {"channels": [{"channel": 1, "value": 12, "wavelength_nm": [1]}]},
    {"channels": [{"channel": 1, "value": 12, "wavelength_nm": [True, 2]}]},
])
def test_bad_structure_does_not_hide_valid_spectra(tmp_path, bad):
    (tmp_path / "bad.json").write_text(json.dumps({"name": "bad", **bad}))
    Spectrum("good", {1: 1}).save(tmp_path / "good.json")
    library = SpectrumLibrary(tmp_path)
    assert library.names() == ["good"]
    assert "bad.json" in library.errors


@pytest.mark.parametrize("field,value", [("channel", 1.9), ("channel", True),
                                        ("value", 12.9), ("value", True)])
def test_json_does_not_coerce_fractional_or_boolean_values(field, value):
    entry = {"channel": "1", "value": 12}
    entry[field] = value
    with pytest.raises(SpectrumError):
        Spectrum.from_dict({"name": "bad", "channels": [entry]})


@pytest.mark.parametrize("channels", [{True: 12}, {1.5: 12}, {1: True}, {1: 12.9}])
def test_direct_spectrum_requires_integer_channels_and_values(pico, channels):
    with pytest.raises(SpectrumError):
        pico.apply_spectrum(Spectrum("bad", channels))
    assert pico._dev.log == []


def test_native_integer_strings_still_work():
    spectrum = Spectrum.from_dict({"name": "native", "channels": [
        {"channel": "01", "value": "12"}]})
    assert spectrum.channels == {1: 12}


def test_overwrite_preserves_original_filename_after_reload(tmp_path):
    path = tmp_path / "000-original.json"
    Spectrum("AM0", {1: 1}).save(path)
    library = SpectrumLibrary(tmp_path)
    assert library.add(Spectrum("AM0", {1: 222}), overwrite=True) == path
    library.reload()
    assert library.get("AM0").channels == {1: 222}
    assert not library.errors
    assert list(tmp_path.glob("*.json")) == [path]


def test_slug_collision_cannot_overwrite_other_spectrum(tmp_path):
    library = SpectrumLibrary(tmp_path)
    library.add(Spectrum("A B", {1: 1}))
    with pytest.raises(FileExistsError):
        library.add(Spectrum("A_B", {1: 222}), overwrite=True)
    library.reload()
    assert library.get("A B").channels == {1: 1}


def test_stale_library_cannot_overwrite_new_file(tmp_path):
    first, second = SpectrumLibrary(tmp_path), SpectrumLibrary(tmp_path)
    first.add(Spectrum("AM0", {1: 1}))
    with pytest.raises(FileExistsError):
        second.add(Spectrum("AM0", {1: 222}), overwrite=True)
    assert Spectrum.load(tmp_path / "am0.json").channels == {1: 1}


def test_failed_replace_keeps_original_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "am0.json"
    Spectrum("AM0", {1: 1}).save(path)

    def fail_replace(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(spectrum_module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        Spectrum("AM0", {1: 222}).save(path, overwrite=True)
    assert Spectrum.load(path).channels == {1: 1}
    assert list(tmp_path.iterdir()) == [path]


def test_all_off_checks_each_clear_result(pico, monkeypatch):
    monkeypatch.setattr(pico._dev, "set_channel_value", lambda ch, value: False)
    with pytest.raises(RuntimeError, match="clearing channel"):
        pico.all_off()


def test_all_off_checks_readback(pico, monkeypatch):
    pico._dev._values[1] = 99
    monkeypatch.setattr(pico._dev, "set_channel_value", lambda ch, value: True)
    with pytest.raises(RuntimeError, match="did not clear"):
        pico.all_off()
