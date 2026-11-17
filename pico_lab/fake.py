"""Compatibility import for scripts that use the original class name."""
from .simulator import SimulatedPico as FakePico

__all__ = ["FakePico"]
