"""FakePico: an in-memory stand-in for g2vpico.G2VPico.

Same public methods, no hardware. Used by the tests and by `--dry-run` so the
wrapper can be tried on any laptop. Channel limits and wavelengths are made up.
"""
from __future__ import annotations


class FakePico:
    def __init__(self, ip_address="0.0.0.0", pico_id="0000000000000000",
                 channel_count=32, limit=4096):
        self._id = pico_id
        self._ip_address = ip_address
        self.channel_count = channel_count
        self.channel_list = list(range(1, channel_count + 1))
        self._values = {ch: 0 for ch in self.channel_list}
        self._limits = {ch: limit for ch in self.channel_list}
        self._intensity = 100.0
        self._on = False
        self.log = []  # (command, args) history, handy in tests

    @property
    def id(self):
        return self._id

    def _check(self, channel):
        channel = int(channel)
        if channel not in self.channel_list:
            raise ValueError(f"A channel value of {channel} is invalid")
        return channel

    def get_channel_value(self, channel):
        return self._values[self._check(channel)]

    def set_channel_value(self, channel, value):
        channel = self._check(channel)
        value = int(value)
        self.log.append(("set_channel_value", channel, value, self._on))
        if not 0 <= value <= self._limits[channel]:
            return False
        self._values[channel] = value
        return True

    def clear_channels(self):
        for ch in self.channel_list:
            self.set_channel_value(ch, 0)
        return True

    def get_channel_limit(self, channel):
        return self._limits[self._check(channel)]

    def get_spectrum(self):
        return [{"channel": str(c), "value": v} for c, v in self._values.items()]

    def get_channel_wavelength_range(self, channel):
        ch = self._check(channel)
        lo = 350 + (ch - 1) * 25
        return [lo, lo + 20]

    def get_global_intensity(self):
        return self._intensity

    def set_global_intensity(self, value):
        self.log.append(("set_global_intensity", value))
        self._intensity = float(value)
        return True

    def turn_on(self):
        self.log.append(("turn_on",))
        self._on = True
        return True

    def turn_off(self):
        self.log.append(("turn_off",))
        self._on = False
        return True

    def is_fixture_on(self):
        return self._on
