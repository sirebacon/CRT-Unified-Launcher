"""YouTube on CRT — thin entrypoint. Logic lives in youtube/."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from youtube.launcher import run

if __name__ == "__main__":
    sys.exit(run())
