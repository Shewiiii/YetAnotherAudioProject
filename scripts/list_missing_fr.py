import glob
import json
import re
import sys
from pathlib import Path

# Non-exhaustive keyword list to append if a false positive is present
EXCLUDE = [
    "cadenza 2",
    "DUNU DaVinci",
    "Moondrop DUSK",
    "FATFreq Scarlet Mini S1",
    "Nightjar Duality",
    "Softears Volume S",
    "Truthear Zero: RED",
    "Zero : Red",
    "7Hz Timeless II",
    "Elysian Acoustic Labs Annihilator (2023)",
    "Elysian Acoustic Labs Pilgrim",
    "Kiwi Ears Orchestra II",
    "Moondrop Variation",
    "Nicehck String Snow (3.5mm)",
    "Sennheiser Momentum True Wireless 4",
    "Simgot EA1000"
]

# Non-exhaustive token list (under ()) to append if a false positive is present
MEASUREMENT_SUFFIX_TOKENS = {
    "anc",
    "avg",
    "bore",
    "c",
    "default",
    "eq",
    "m100",
    "macos",
    "reference",
    "ring",
    "setting",
    "sponge",
    "standard",
    "tips",
    "usb",
    "ver",
    "windows",
    "listener",
    "tam",
    "mm"
}

# Add project root to sys.path so params can be imported
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import params

# Fallback path for the exported JSON
JSON_PATH = (
    SCRIPT_DIR / "website_phones.json"
    if (SCRIPT_DIR / "website_phones.json").exists()
    else PROJECT_ROOT / "website_phones.json"
)


def normalize(name: str) -> str:
    """Strip extensions, spacing, and punctuation for flexible matching."""
    name = re.sub(r"\.txt$", "", name, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def tokens(name: str) -> list[str]:
    """Return comparable name tokens while retaining model boundaries."""
    name = re.sub(r"\.txt$", "", name, flags=re.IGNORECASE)
    return re.findall(r"[a-z0-9]+", name.lower())


def is_excluded(item: dict) -> bool:
    """Return whether a website entry matches a configured exclusion keyword."""
    if str(item.get("fullName", "")).lstrip().startswith("*"):
        return True

    values = [
        item.get("brand", ""),
        item.get("phone", ""),
        item.get("fullName", ""),
        item.get("fileName", ""),
        *item.get("dispNames", []),
    ]
    searchable_text = " ".join(str(value) for value in values)
    normalized_text = normalize(searchable_text)
    return any(normalize(keyword) in normalized_text for keyword in EXCLUDE)


def is_measurement_variant(candidate: str, local_name: str) -> bool:
    """Match a candidate with a local measurement annotation appended."""
    candidate_tokens = tokens(candidate)
    local_tokens = tokens(local_name)
    if len(local_tokens) <= len(candidate_tokens):
        return False
    if local_tokens[: len(candidate_tokens)] != candidate_tokens:
        return False
    suffix = local_tokens[len(candidate_tokens) :]
    return any(token in MEASUREMENT_SUFFIX_TOKENS for token in suffix)


def main():
    if not JSON_PATH.exists():
        print(f"Error: Missing '{JSON_PATH.name}'.")
        print("Save the browser clipboard output to that file and run again.")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        web_phones = json.load(f)

    # Resolve wildcard pattern defined in params.FREQUENCY_RESPONSES
    fr_pattern = str(PROJECT_ROOT / params.FREQUENCY_RESPONSES)
    matched_paths = glob.glob(fr_pattern)

    # Map normalized names to actual file paths/names
    local_files = {normalize(Path(p).name): Path(p).name for p in matched_paths}

    missing = 0

    for item in web_phones:
        if is_excluded(item):
            continue

        brand = item.get("brand", "")
        # Build list of potential name formats Hangout Audio might use
        candidates = [
            item.get("fullName", ""),
            item.get("fileName", ""),
            f"{brand} {item.get('fileName', '')}".strip(),
            f"{brand} {item.get('phone', '')}".strip(),
        ]
        candidates.extend(
            f"{brand} {disp}".strip() for disp in item.get("dispNames", [])
        )

        matched_file = None
        for candidate in candidates:
            norm = normalize(candidate)
            if norm in local_files:
                matched_file = local_files[norm]
                break
            for local_name in local_files.values():
                if is_measurement_variant(candidate, local_name):
                    matched_file = local_name
                    break
            if matched_file:
                break

        if not matched_file:
            print(item.get("fullName"))
            missing += 1

    print(f"Potentially missing: {missing} out of {len(web_phones)}\n")


if __name__ == "__main__":
    main()
