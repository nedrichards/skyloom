"""Create an offline visual contact sheet and an always-run Actions diagnostic summary."""

import argparse
import html
import json
import os
from pathlib import Path


def contact_sheet(directory):
    images = sorted(directory.glob("visual/**/*.png"))
    figures = []
    for path in images:
        relative = html.escape(path.relative_to(directory).as_posix(), quote=True)
        figures.append(
            f'<figure><a href="{relative}"><img loading="lazy" src="{relative}" alt="{relative}"></a><figcaption>{relative}</figcaption></figure>'
        )
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Skyloom demo review</title><style>"
        "body{font:16px system-ui;margin:2rem;background:#eee;color:#222}"
        "main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}"
        "figure{margin:0;padding:1rem;background:white;overflow-wrap:anywhere}"
        "img{width:100%;height:360px;object-fit:contain}figcaption{margin-top:1rem}"
        "</style><h1>Skyloom demo review</h1>"
        "<p>Invented records only. Functional screenshots; no pixel-difference or physical-input acceptance is claimed.</p><main>"
        + "".join(figures)
        + "</main></html>\n"
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text(page, encoding="utf-8")
    return len(images)


def summary(directory, outcomes):
    lines = ["### Skyloom validation", "", f"Architecture: {os.getenv('BUILD_ARCH', 'local')}", ""]
    for name, outcome in outcomes.items():
        lines.append(f"- {name}: {outcome}")
    for path in sorted(directory.glob("*-tests.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        lines.extend(["", f"#### {path.stem}"])
        if "preflight" in result:
            lines.append("Runtime/display setup failed before tests ran.")
        else:
            lines.append(f"{result['tests']} tests; {len(result['skips'])} skips.")
            for kind in ("failures", "errors", "gate_errors"):
                lines.extend(f"- {kind}: `{value}`" for value in result[kind])
    if outcomes.get("native") == "failure" and not list(directory.glob("*-tests.json")):
        lines.append(
            "\nNative execution failed before a test report was produced; inspect setup/parity logs."
        )
    lines.append(
        f"\nVisual review: {contact_sheet(directory)} screenshots in the diagnostic artifact's `index.html`."
    )
    text = "\n".join(lines) + "\n"
    (directory / "summary.md").write_text(text, encoding="utf-8")
    if destination := os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(destination).open("a", encoding="utf-8") as output:
            output.write(text)
    print(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    summary(args.directory, json.loads(os.getenv("CI_OUTCOMES", "{}")))


if __name__ == "__main__":
    main()
