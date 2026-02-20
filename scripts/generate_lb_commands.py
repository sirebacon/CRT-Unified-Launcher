"""Generate LaunchBox wrapper command lines from profile files.

Run from the project root:

    python scripts/generate_lb_commands.py
    python scripts/generate_lb_commands.py --json
    python scripts/generate_lb_commands.py --profiles-dir custom/path
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRAPPER_PATH = os.path.join(
    PROJECT_ROOT, "integrations", "launchbox", "wrapper", "launchbox_generic_wrapper.py"
)
DEFAULT_PROFILES_DIR = os.path.join(
    PROJECT_ROOT, "integrations", "launchbox", "wrapper", "profiles"
)
SKIP_SLUGS = {"template", "defaults"}


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def generate_command(profile_path: str, profile: dict) -> str:
    """Return the Python command line LaunchBox should use for this profile."""
    parts = [
        "python",
        f'"{WRAPPER_PATH}"',
        "--profile-file",
        f'"{profile_path}"',
    ]
    for pn in profile.get("process_name", []):
        parts.extend(["--process-name", pn])
    return " ".join(parts)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate LaunchBox wrapper command lines from profile files.")
    p.add_argument("--profiles-dir", default=DEFAULT_PROFILES_DIR, help="Directory containing profile JSON files.")
    p.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON instead of plain text.")
    args = p.parse_args()

    if not os.path.isdir(args.profiles_dir):
        print(f"[Error] Profiles directory not found: {args.profiles_dir}")
        return 1

    results = []
    for fname in sorted(os.listdir(args.profiles_dir)):
        if not fname.endswith(".json"):
            continue
        slug = os.path.splitext(fname)[0]
        if slug in SKIP_SLUGS:
            continue
        profile_path = os.path.join(args.profiles_dir, fname)
        try:
            profile = load_profile(profile_path)
        except Exception as e:
            print(f"[Warning] Could not load {fname}: {e}")
            continue
        results.append({
            "slug": slug,
            "exe": profile.get("path", ""),
            "command": generate_command(profile_path, profile),
        })

    if args.as_json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"\n[{r['slug']}]")
            print(f"  Exe:     {r['exe']}")
            print(f"  Command: {r['command']}")
        if not results:
            print("No profiles found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
