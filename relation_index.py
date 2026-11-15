"""Run the VulRIS CLI from a source checkout without installing the package.

``python relation_index.py ...`` is equivalent to the installed ``vulris`` command.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from relation_index.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
