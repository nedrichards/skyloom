"""Prepare an exact source checkout and record any release packaging overlay."""

import ast
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from dependencies import check


def commit(directory):
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git is required")
    return subprocess.check_output(  # noqa: S603 — fixed Git command and exact trusted checkout directory.
        [git, "-c", f"safe.directory={directory.resolve()}", "rev-parse", "HEAD"],
        cwd=directory,
        text=True,
    ).strip()


def prepare(root, source, architecture, reference, release):
    reference = reference.removeprefix("refs/tags/")
    if platform.machine() != architecture:
        raise ValueError("A native runner for the requested architecture is required")
    if release and not re.fullmatch(r"v\d+\.\d+\.\d+", reference):
        raise ValueError("An existing vX.Y.Z release tag is required")
    tree = ast.parse((source / "src/skyloom/__init__.py").read_text(encoding="utf-8"))
    version = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    )
    if release and reference != "v" + version:
        raise ValueError("Tag and application version differ")
    overlay = []
    if release:
        # Older published tags predate ARM wheels. Preserve the established
        # packaging-only overlay, but never change a dependency version.
        try:
            check(source)
        except ValueError as error:
            if (root / "requirements.lock").read_bytes() != (
                source / "requirements.lock"
            ).read_bytes():
                raise ValueError(
                    "Release packaging is incomplete and tooling dependency pins differ"
                ) from error
            for name in ("python-dependencies.json", "requirements-hashed.lock"):
                if (root / name).read_bytes() != (source / name).read_bytes():
                    shutil.copyfile(root / name, source / name)
                    overlay.append(name)
    check(source)
    manifest_path = source / "com.nedrichards.Skyloom.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for module in manifest["modules"]:
        if isinstance(module, dict):
            for item in module.get("sources", []):
                if item["type"] == "dir":
                    skip = item.setdefault("skip", [])
                    if "build-ci" not in skip:
                        skip.append("build-ci")
                        overlay.append("manifest: exclude CI diagnostics")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    source_commit, tooling_commit = commit(source), commit(root)
    label = reference if release else "commit-" + source_commit[:12]
    if not release and (number := os.getenv("PR_NUMBER")):
        if not number.isdecimal():
            raise ValueError("Invalid pull request number")
        label = f"pr-{number}-merge-{source_commit[:12]}"
    bundle = f"com.nedrichards.Skyloom-{label}-{architecture}.flatpak"
    dist = source / "dist"
    dist.mkdir(exist_ok=True)
    (source / "build-ci").mkdir(exist_ok=True)
    (dist / f"BUILD_INFO-{architecture}.txt").write_text(
        f"Application source: {source_commit}\nPackaging tooling: {tooling_commit}\n"
        f"Architecture: {architecture} (native)\nVersion: {version}\n"
        f"Runtime: org.gnome.Platform//51\nPackaging overlay: {', '.join(overlay) or 'none'}\n",
        encoding="utf-8",
    )
    return {"bundle": bundle, "version": version, "commit": source_commit}


def main():
    root = Path.cwd()
    outputs = prepare(
        root,
        root / "source",
        os.environ["BUILD_ARCH"],
        os.getenv("SOURCE_REF", ""),
        os.getenv("RELEASE_BUILD") == "true",
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.writelines(f"{name}={value}\n" for name, value in outputs.items())


if __name__ == "__main__":
    main()
