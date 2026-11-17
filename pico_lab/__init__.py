"""pico_lab - spectrum library + controller wrapper for the G2V Pico solar simulator."""
from .controller import PicoController
from .spectrum import Spectrum, SpectrumError, SpectrumLibrary
from .simulator import SimulatedPico

FakePico = SimulatedPico  # Compatibility with existing scripts.

__all__ = ["PicoController", "Spectrum", "SpectrumError", "SpectrumLibrary", "SimulatedPico", "FakePico"]
__version__ = "0.1.0"
