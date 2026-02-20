"""Check for drift between wrapper profile files and LaunchBox emulator config.

Reads LaunchBox's Emulators.xml and compares ApplicationPath values against
wrapper profiles. Reports emulators that reference our wrapper scripts but
whose paths may have drifted from what the profiles expect.

Best-effort only — LaunchBox XML structure may vary across versions.
All mismatches are reported as warnings, never hard errors.

Run from the project root:

    python scripts/check_launchbox_drift.py
    python scripts/check_launchbox_drift.py --lb-data "D:\\LaunchBox\\Data"
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRAPPER_SCRIPT_NAME = "launchbox_generic_wrapper.py"
DEFAULT_PROFILES_DIR = os.path.join(
    PROJECT_ROOT, "integrations", "launchbox", "wrapper", "profiles"
)
SKIP_SLUGS = {"template", "defaults"}

# Common LaunchBox install locations to search if --lb-data is not provided.
LB_SEARCH_PATHS = [
    r"D:\Emulators\LaunchBox\Data",
    r"C:\LaunchBox\Data",
    r"D:\LaunchBox\Data",
]


def find_lb_data_dir(hint: str = "") -> str:
    if hint and os.path.isdir(hint):
        return hint
    for path in LB_SEARCH_PATHS:
        if os.path.isdir(path):
            return path
    return ""


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_profiles(profiles_dir: str) -> dict:
    """Return {slug: profile_dict} for all non-skip profiles."""
    profiles = {}
    if not os.path.isdir(profiles_dir):
        return profiles
    for fname in os.listdir(profiles_dir):
        if not fname.endswith(".json"):
            continue
        slug = os.path.splitext(fname)[0]
        if slug in SKIP_SLUGS:
            continue
        try:
            profiles[slug] = load_profile(os.path.join(profiles_dir, fname))
        except Exception as e:
            print(f"[Warning] Could not load profile {fname}: {e}")
    return profiles


def parse_emulators_xml(xml_path: str) -> list:
    """Parse Emulators.xml and return list of dicts with emulator fields.

    Tolerant — skips elements it cannot read.
    """
    emulators = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for emulator in root.findall(".//Emulator"):
            entry = {}
            for child in emulator:
                entry[child.tag] = (child.text or "").strip()
            if entry:
                emulators.append(entry)
    except Exception as e:
        print(f"[Warning] Could not parse {xml_path}: {e}")
    return emulators


def references_wrapper(app_path: str) -> bool:
    return WRAPPER_SCRIPT_NAME.lower() in app_path.lower()


def main() -> int:
    p = argparse.ArgumentParser(description="Check LaunchBox emulator config drift against wrapper profiles.")
    p.add_argument("--lb-data", default="", help="Path to LaunchBox Data directory.")
    p.add_argument("--profiles-dir", default=DEFAULT_PROFILES_DIR, help="Path to wrapper profiles directory.")
    args = p.parse_args()

    lb_data = find_lb_data_dir(args.lb_data)
    if not lb_data:
        print("[Error] Could not locate LaunchBox Data directory.")
        print(f"        Searched: {LB_SEARCH_PATHS}")
        print("        Use --lb-data to specify it explicitly.")
        return 1

    xml_path = os.path.join(lb_data, "Emulators.xml")
    if not os.path.exists(xml_path):
        print(f"[Error] Emulators.xml not found at: {xml_path}")
        return 1

    profiles = load_profiles(args.profiles_dir)
    emulators = parse_emulators_xml(xml_path)

    wrapper_emulators = [e for e in emulators if references_wrapper(e.get("ApplicationPath", ""))]

    if not wrapper_emulators:
        print("[OK] No emulators in LaunchBox reference the generic wrapper.")
        return 0

    print(f"Found {len(wrapper_emulators)} LaunchBox emulator(s) referencing the generic wrapper:\n")
    issues = 0

    for e in wrapper_emulators:
        title = e.get("Title", "(unknown)")
        app_path = e.get("ApplicationPath", "")
        command_line = e.get("CommandLine", "")

        print(f"  Emulator: {title}")
        print(f"    ApplicationPath: {app_path}")
        print(f"    CommandLine:     {command_line}")

        # Try to match against known profiles.
        matched_slug = None
        for slug in profiles:
            if f"--profile-file" in command_line and slug in command_line:
                matched_slug = slug
                break

        if matched_slug:
            profile = profiles[matched_slug]
            expected_exe = profile.get("path", "")
            print(f"    Matched profile: {matched_slug}")
            print(f"    Profile exe:     {expected_exe}")
            if not os.path.exists(expected_exe):
                print(f"    [WARN] Profile exe does not exist on disk: {expected_exe}")
                issues += 1
            else:
                print(f"    [OK]")
        else:
            print(f"    [WARN] No matching profile found for this command line.")
            issues += 1

        print()

    if issues:
        print(f"{issues} issue(s) detected. Review warnings above.")
        return 1

    print("No drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
