"""Check lock/Flatpak parity offline, or report PyPI health without updating pins."""

import argparse
import json
import re
import tomllib
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ARCHITECTURES = {"x86_64", "aarch64"}


def identity(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path, *, hashed=False):
    result, hashes = {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        pin, *options = line.split()
        match = re.fullmatch(r"([\w.-]+)==([^\s;]+)", pin)
        if not match:
            raise ValueError(f"Invalid exact pin in {path}: {pin}")
        name, version = match.groups()
        name = identity(name)
        if name in result:
            raise ValueError(f"Duplicate pin: {name}")
        result[name] = version
        hashes[name] = set()
        for option in options:
            if not re.fullmatch(r"--hash=sha256:[a-f0-9]{64}", option):
                raise ValueError(f"Invalid hash option: {option}")
            hashes[name].add(option.removeprefix("--hash=sha256:"))
        if hashed and not hashes[name]:
            raise ValueError(f"Missing hashes: {name}")
    return result, hashes


def check(root):
    pins, _ = read_lock(root / "requirements.lock")
    hashed_pins, hashes = read_lock(root / "requirements-hashed.lock", hashed=True)
    development, _ = read_lock(root / "requirements-dev.lock")
    if pins != hashed_pins or any(development.get(n) != v for n, v in pins.items()):
        raise ValueError("Runtime, development and hashed locks disagree")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    for dependency in project["project"]["dependencies"]:
        name, version = dependency.split("==")
        if pins.get(identity(name)) != version:
            raise ValueError(f"Project pin disagrees: {dependency}")
    if development.get("ruff") != project["tool"]["ruff"]["required-version"].removeprefix("=="):
        raise ValueError("Ruff pin disagrees")
    module = json.loads((root / "python-dependencies.json").read_text(encoding="utf-8"))
    coverage, manifest_hashes = defaultdict(set), defaultdict(set)
    for source in module["sources"]:
        url = urllib.parse.urlsplit(source["url"])
        filename = urllib.parse.unquote(url.path.rsplit("/", 1)[-1])
        if url.scheme != "https" or url.netloc != "files.pythonhosted.org":
            raise ValueError("Wheel source must use the PyPI file host over HTTPS")
        name, version = filename.split("-")[:2]
        name = identity(name)
        if pins.get(name) != version:
            raise ValueError(f"Unpinned wheel: {filename}")
        arches = set(source.get("only-arches", ARCHITECTURES))
        if not arches or not arches <= ARCHITECTURES:
            raise ValueError(f"Invalid wheel architectures: {filename}")
        if not filename.endswith("-any.whl") and arches != {
            arch for arch in ARCHITECTURES if arch in filename
        }:
            raise ValueError(f"Wheel architecture filter disagrees: {filename}")
        if coverage[name] & arches:
            raise ValueError(f"Overlapping wheels for {name}")
        coverage[name].update(arches)
        manifest_hashes[name].add(source["sha256"])
    if dict(manifest_hashes) != hashes or any(coverage[n] != ARCHITECTURES for n in pins):
        raise ValueError("Wheel hashes or architecture coverage disagree with locks")
    print(f"DEPENDENCY_PARITY_PASS: {len(pins)} packages on both architectures")
    return pins, module["sources"]


def fetch(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "pypi.org":
        raise ValueError("Health metadata must come from PyPI over HTTPS")
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 — fixed HTTPS metadata host checked above.
        return json.load(response)


def health(root, output):
    pins, sources = check(root)
    report, vulnerable = [], False
    for name, version in sorted(pins.items()):
        current = fetch(f"https://pypi.org/pypi/{name}/{version}/json")
        latest = fetch(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
        published = {item["url"]: item["digests"]["sha256"] for item in current["urls"]}
        for source in sources:
            filename = urllib.parse.urlsplit(source["url"]).path.rsplit("/", 1)[-1]
            if (
                identity(filename.split("-")[0]) == name
                and published.get(source["url"]) != source["sha256"]
            ):
                raise ValueError(f"PyPI wheel digest disagrees: {filename}")
        issues = [
            item["id"] for item in current.get("vulnerabilities", []) if not item.get("withdrawn")
        ]
        vulnerable |= bool(issues)
        report.append(
            {"package": name, "pinned": version, "latest": latest, "vulnerabilities": issues}
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in report:
        print(
            f"{item['package']}: {item['pinned']} → {item['latest']}; advisories: {item['vulnerabilities']}"
        )
    if vulnerable:
        raise ValueError("Pinned runtime dependencies have published vulnerability advisories")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--health", type=Path, help="Fetch live metadata and save a JSON report")
    args = parser.parse_args()
    if args.health:
        health(args.root, args.health)
    else:
        check(args.root)


if __name__ == "__main__":
    main()
