"""
CRT Station GUI — entry point.

Double-click this file (or the built CRT Station.exe) to launch.
All backend scripts are unchanged; this is a pure front-end shell.
"""
import os
import sys

# Ensure the project root is on sys.path when running as a plain .py script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import CRTStationApp

if __name__ == "__main__":
    app = CRTStationApp()
    app.mainloop()
