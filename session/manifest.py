"""Session manifest loader and schema validator.

Schema (schema_version 1)
--------------------------
{
  "schema_version": 1,

  "primary": {
    "profile": "<path to session profile JSON>"
  },

  "watch": [
    { "profile": "<path to session profile JSON>" },
    ...
  ],

  "patches": [
    {
      "type": "retroarch_cfg",
      "path": "<path to retroarch.cfg>",
      "set_values": { "<key>": "<value>", ... }
    },
    {
      "type": "launchbox_emulator",
      "path": "<path to Emulators.xml>",
      "emulators": [
        {
          "title": "<emulator title, case-insensitive>",
          "wrapper_bat": "<path to wrapper .bat>",
          "strip_args": ["<arg to strip from CommandLine>", ...],
          "xml_fields": { "<tag>": "<value>", ... }
        },
        ...
      ]
    },
    {
      "type": "launchbox_settings",
      "bigbox_path": "<path to BigBoxSettings.xml>",
      "settings_path": "<path to Settings.xml>",
      "monitor_index": <int>,
      "disable_splash_screens": <bool>
    }
  ]
}

Validation guarantees (all errors reported in one pass):
  - schema_version present and in SUPPORTED_SCHEMA_VERSIONS
  - primary.profile file exists
  - every watch[i].profile file exists
  - no duplicate process_name values across watch profiles
  - every patch has a known type with all required fields present
  - all file paths referenced in patches exist
  - wrapper_bat paths for launchbox_emulator patches exist
"""
import json
import os
from dataclasses import dataclass, field
from typing import List

SUPPORTED_SCHEMA_VERSIONS = {1}
KNOWN_PATCH_TYPES = {"retroarch_cfg", "launchbox_emulator", "launchbox_settings"}


@dataclass
class WatchEntry:
    profile: str


@dataclass
class Manifest:
    schema_version: int
    primary: WatchEntry
    watch: List[WatchEntry]
    patches: List[dict]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load(path: str) -> Manifest:
    """Load and validate a session manifest JSON file.

    Raises ValueError with a multi-line message listing every validation
    error if validation fails.  Raises OSError / json.JSONDecodeError if the
    file cannot be read or parsed.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors: List[str] = []

    # --- schema_version ---
    schema_version = data.get("schema_version")
    if schema_version is None:
        errors.append("Missing required field: schema_version")
    elif schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(
            f"Unsupported schema_version: {schema_version!r}. "
            f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    # --- primary ---
    primary: WatchEntry | None = None
    p_raw = data.get("primary")
    if p_raw is None:
        errors.append("Missing required field: primary")
    elif not isinstance(p_raw, dict):
        errors.append("primary: must be an object")
    elif "profile" not in p_raw:
        errors.append("primary: missing required field 'profile'")
    else:
        if not os.path.exists(p_raw["profile"]):
            errors.append(f"primary.profile not found: {p_raw['profile']}")
        else:
            primary = WatchEntry(profile=p_raw["profile"])

    # --- watch ---
    watch: List[WatchEntry] = []
    process_names_seen: dict = {}  # lower-cased name -> watch index of first occurrence
    w_raw = data.get("watch")
    if w_raw is None:
        errors.append("Missing required field: watch")
    elif not isinstance(w_raw, list):
        errors.append("watch: must be a list")
    else:
        for i, entry in enumerate(w_raw):
            if not isinstance(entry, dict) or "profile" not in entry:
                errors.append(f"watch[{i}]: missing required field 'profile'")
                continue
            profile_path = entry["profile"]
            if not os.path.exists(profile_path):
                errors.append(f"watch[{i}].profile not found: {profile_path}")
                continue
            try:
                with open(profile_path, "r", encoding="utf-8-sig") as f:
                    profile_data = json.load(f)
                for pname in profile_data.get("process_name", []):
                    pname_l = pname.lower()
                    if pname_l in process_names_seen:
                        errors.append(
                            f"watch[{i}]: process name {pname!r} duplicates "
                            f"watch[{process_names_seen[pname_l]}]"
                        )
                    else:
                        process_names_seen[pname_l] = i
            except Exception as exc:
                errors.append(f"watch[{i}]: cannot read profile {profile_path}: {exc}")
                continue
            watch.append(WatchEntry(profile=profile_path))

    # --- patches ---
    patches: List[dict] = []
    p_list = data.get("patches")
    if p_list is None:
        errors.append("Missing required field: patches")
    elif not isinstance(p_list, list):
        errors.append("patches: must be a list")
    else:
        for i, patch in enumerate(p_list):
            t = patch.get("type")
            if t is None:
                errors.append(f"patches[{i}]: missing required field 'type'")
                continue
            if t not in KNOWN_PATCH_TYPES:
                errors.append(
                    f"patches[{i}]: unknown type {t!r}. "
                    f"Known types: {sorted(KNOWN_PATCH_TYPES)}"
                )
                continue

            patch_ok = True

            if t == "retroarch_cfg":
                if "path" not in patch:
                    errors.append(f"patches[{i}] (retroarch_cfg): missing 'path'")
                    patch_ok = False
                elif not os.path.exists(patch["path"]):
                    errors.append(
                        f"patches[{i}] (retroarch_cfg): path not found: {patch['path']}"
                    )
                    patch_ok = False
                if "set_values" not in patch or not isinstance(patch["set_values"], dict):
                    errors.append(
                        f"patches[{i}] (retroarch_cfg): missing or invalid 'set_values'"
                    )
                    patch_ok = False

            elif t == "launchbox_emulator":
                if "path" not in patch:
                    errors.append(f"patches[{i}] (launchbox_emulator): missing 'path'")
                    patch_ok = False
                elif not os.path.exists(patch["path"]):
                    errors.append(
                        f"patches[{i}] (launchbox_emulator): path not found: {patch['path']}"
                    )
                    patch_ok = False
                em_list = patch.get("emulators")
                if em_list is None or not isinstance(em_list, list):
                    errors.append(
                        f"patches[{i}] (launchbox_emulator): missing or invalid 'emulators'"
                    )
                    patch_ok = False
                else:
                    for j, em in enumerate(em_list):
                        if "title" not in em:
                            errors.append(
                                f"patches[{i}].emulators[{j}]: missing 'title'"
                            )
                            patch_ok = False
                        bat = em.get("wrapper_bat")
                        if bat is None:
                            errors.append(
                                f"patches[{i}].emulators[{j}]: missing 'wrapper_bat'"
                            )
                            patch_ok = False
                        elif not os.path.exists(bat):
                            errors.append(
                                f"patches[{i}].emulators[{j}]: wrapper_bat not found: {bat}"
                            )
                            patch_ok = False

            elif t == "launchbox_settings":
                for field_name in ("bigbox_path", "settings_path"):
                    fp = patch.get(field_name)
                    if fp is None:
                        errors.append(
                            f"patches[{i}] (launchbox_settings): missing '{field_name}'"
                        )
                        patch_ok = False
                    elif not os.path.exists(fp):
                        errors.append(
                            f"patches[{i}] (launchbox_settings): "
                            f"{field_name} not found: {fp}"
                        )
                        patch_ok = False

            if patch_ok:
                patches.append(patch)

    if errors:
        bullet = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"Manifest validation failed ({path}):\n{bullet}")

    return Manifest(
        schema_version=schema_version,
        primary=primary,
        watch=watch,
        patches=patches,
    )
