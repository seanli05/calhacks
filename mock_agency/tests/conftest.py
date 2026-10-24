import sys
from pathlib import Path

# mock_agency deploys as its own project root, so its modules import as `agency.*`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
