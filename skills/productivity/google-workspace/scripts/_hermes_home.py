"""Resolve ANTHOS_HOME for standalone skill scripts.

Skill scripts may run outside the Anthos process (e.g. system Python,
nix env, CI) where ``anthos_constants`` is not importable.  This module
provides the same ``get_anthos_home()`` and ``display_anthos_home()``
contracts as ``anthos_constants`` without requiring it on ``sys.path``.

When ``anthos_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``anthos_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``ANTHOS_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from anthos_constants import display_anthos_home as display_anthos_home
    from anthos_constants import get_anthos_home as get_anthos_home
except (ModuleNotFoundError, ImportError):

    def get_anthos_home() -> Path:
        """Return the Anthos home directory (default: ~/.anthos).

        Mirrors ``anthos_constants.get_anthos_home()``."""
        val = os.environ.get("ANTHOS_HOME", "").strip()
        return Path(val) if val else Path.home() / ".anthos"

    def display_anthos_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``anthos_constants.display_anthos_home()``."""
        home = get_anthos_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
