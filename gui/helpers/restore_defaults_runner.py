"""
Thin subprocess wrapper for restore_defaults_from_backup().

Called by the GUI as:
    python restore_defaults_runner.py <launcher_dir>

Accepts the project root as an explicit argument so this script can be
located in any temp/extraction directory (e.g. PyInstaller --onefile) and
still find the correct default_restore module.
"""
import os
import sys

# First positional argument is the launcher directory, or fall back to
# computing it from __file__ (works when running as a plain .py script).
if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    _root = sys.argv[1]
else:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, _root)

try:
    from default_restore import restore_defaults_from_backup  # noqa: E402
except ImportError as exc:
    print(f"ERROR: Could not import default_restore from {_root}: {exc}")
    sys.exit(2)

ok, msg, restored = restore_defaults_from_backup()
print(msg)
if restored:
    print("\nRestored files:")
    for item in restored:
        print(f"  - {item}")

sys.exit(0 if ok else 1)
