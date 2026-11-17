"""Check that the release tag, manifest version and card version agree.

Run by .github/workflows/versions.yml. Set TAG to the release tag (for
example v0.5.3) to also check it against the manifest. Prints GitHub
annotations and exits non-zero on any mismatch.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "custom_components/concept2_logbook/manifest.json"
CARD = ROOT / "custom_components/concept2_logbook/frontend/concept2-logbook-card.js"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    errors: list[str] = []
    manifest_version = json.loads(MANIFEST.read_text())["version"]
    if not SEMVER.match(manifest_version):
        errors.append(
            f"manifest.json version '{manifest_version}' should look like 1.2.3"
        )

    match = re.search(r'const CARD_VERSION = "([^"]+)"', CARD.read_text())
    card_version = match.group(1) if match else None
    if card_version != manifest_version:
        errors.append(
            f"Card version '{card_version}' in concept2-logbook-card.js doesn't "
            f"match manifest.json '{manifest_version}'. Bump both together."
        )

    if tag := os.environ.get("TAG", "").strip():
        tag_version = tag.removeprefix("v")
        if tag_version != manifest_version:
            errors.append(
                f"Release tag '{tag}' doesn't match manifest.json version "
                f"'{manifest_version}'. The Marketplace will show the wrong "
                f"version. Delete this release and tag, set the manifest to "
                f"'{tag_version}' (or tag v{manifest_version}), and release again."
            )

    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print(
        f"OK: manifest {manifest_version}, card {card_version}"
        + (f", tag {tag}" if tag else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
