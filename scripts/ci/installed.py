"""Prove the installed application's architecture, version and source parity."""

import argparse
import ast
import platform
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("architecture", choices=("x86_64", "aarch64"))
    args = parser.parse_args()
    import skyloom

    if platform.machine() != args.architecture:
        raise RuntimeError("Installed application is running on the wrong architecture")
    source = args.source / "src/skyloom"
    module = ast.parse((source / "__init__.py").read_text(encoding="utf-8"))
    expected = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    )
    installed = Path(skyloom.__file__).parent
    if installed != Path("/app/share/skyloom/skyloom") or expected != skyloom.VERSION:
        raise RuntimeError("Expected installed modules and version")
    files = sorted(source.glob("*.py"))
    if {p.name for p in files} != {p.name for p in installed.glob("*.py")}:
        raise RuntimeError("Installed module set differs from source")
    if any(p.read_bytes() != (installed / p.name).read_bytes() for p in files):
        raise RuntimeError("Installed Python source differs from checkout")
    print(f"INSTALLED_PARITY_PASS: {platform.machine()}, {skyloom.VERSION}, {len(files)} modules")


if __name__ == "__main__":
    main()
