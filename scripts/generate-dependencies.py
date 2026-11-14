#!/usr/bin/env python3
"""Verify pinned CPython 3.14 wheels for x86_64 and aarch64, then emit offline inputs.

Keep downloaded wheels in wheels/ (or architecture subdirectories). Superseded
versions are ignored when requirements.lock is present. Builds never use network.
"""

import hashlib
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

ARCHITECTURES = ("x86_64", "aarch64")


def verify_wheel(wheel: Path, expected: str) -> str:
    """Verify downloaded bytes even when Python runs with optimization enabled."""
    with wheel.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"SHA-256 mismatch for {wheel.name}")
    return digest


def wheel_architectures(filename):
    if filename.endswith("-any.whl"):
        return ARCHITECTURES
    architectures = tuple(arch for arch in ARCHITECTURES if arch in filename)
    if not architectures:
        raise ValueError(f"Unsupported wheel platform: {filename}")
    return architectures


def main(root: Path) -> None:
    wheels = sorted((root / "wheels").rglob("*.whl"))
    if not wheels:
        raise ValueError("No downloaded wheels found; existing dependency locks were preserved")
    pinned = {}
    lock = root / "requirements.lock"
    if lock.exists():
        for line in lock.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                name, version = line.strip().split("==")
                pinned[name.lower().replace("_", "-")] = version
    sources, metadata = {}, {}
    requirements, coverage = defaultdict(set), defaultdict(set)
    for wheel in wheels:
        name, version = wheel.name.split("-")[:2]
        identity = name.lower().replace("_", "-")
        if pinned and pinned.get(identity) != version:
            continue
        key = (name, version)
        if key not in metadata:
            with urllib.request.urlopen(
                f"https://pypi.org/pypi/{name}/{version}/json", timeout=30
            ) as response:
                metadata[key] = json.load(response)
        item = next(f for f in metadata[key]["urls"] if f["filename"] == wheel.name)
        digest = verify_wheel(wheel, item["digests"]["sha256"])
        architectures = wheel_architectures(wheel.name)
        coverage[identity].update(architectures)
        requirements[key].add(digest)
        source = {"type": "file", "url": item["url"], "sha256": digest, "dest": "wheels"}
        if architectures != ARCHITECTURES:
            source["only-arches"] = list(architectures)
        sources[wheel.name] = source
    for identity in pinned or coverage:
        missing = set(ARCHITECTURES) - coverage[identity]
        if missing:
            raise ValueError(f"Missing {identity} wheels for {sorted(missing)}; locks preserved")
    if not sources:
        raise ValueError("No pinned wheels found; existing dependency locks were preserved")
    module = {
        "name": "python-dependencies",
        "buildsystem": "simple",
        "build-commands": [
            "pip3 install --no-index --no-deps --no-build-isolation --prefix=/app wheels/*.whl"
        ],
        "sources": [sources[name] for name in sorted(sources)],
    }
    (root / "python-dependencies.json").write_text(
        json.dumps(module, indent=2) + "\n", encoding="utf-8"
    )
    hashed = [
        f"{name}=={version} " + " ".join(f"--hash=sha256:{digest}" for digest in sorted(digests))
        for (name, version), digests in sorted(requirements.items())
    ]
    (root / "requirements-hashed.lock").write_text(
        "# GNOME 51, CPython 3.14, x86_64 and aarch64\n" + "\n".join(hashed) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(Path(__file__).resolve().parent.parent)
