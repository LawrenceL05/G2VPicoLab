import sys
from pathlib import Path

# let "pytest" find pico_lab from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
