"""RetroArch cfg patch handler.

Reads retroarch.cfg, sets the requested key = "value" lines, and writes the
file back.  Existing lines not mentioned in set_values are preserved unchanged.
Keys not already present in the file are appended at the end.

Format: retroarch.cfg uses   key = "value"   lines (one per key).
"""
from typing import Dict


def apply(path: str, set_values: Dict[str, str]) -> None:
    """Apply key-value pairs to a retroarch.cfg file.

    Args:
        path:       Absolute path to retroarch.cfg.
        set_values: Dict of {key: value} pairs to set.  Values should be
                    plain strings; they will be written as  key = "value".
    """
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = f.read().splitlines()

    seen: set = set()
    output = []
    for line in lines:
        stripped = line.strip()
        replaced = False
        for key, value in set_values.items():
            if stripped.startswith(f"{key} = "):
                output.append(f'{key} = "{value}"')
                seen.add(key)
                replaced = True
                break
        if not replaced:
            output.append(line)

    # Append any keys that were not already in the file.
    for key, value in set_values.items():
        if key not in seen:
            output.append(f'{key} = "{value}"')

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(output) + "\n")
