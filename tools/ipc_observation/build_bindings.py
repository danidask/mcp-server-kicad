"""Build the investigation pins into an isolated experimental wheel.

Downloads official sources by immutable commit. No third-party source is copied
into this repository. See docs/ipc-observation.md for license/provenance and gates.
Run under the locked Python 3.13 environment with --output outside the checkout.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BINDINGS = "87b945a0d56b26a78bf547db9771ff9bf3a057ea"
PROTOCOL = "dcadf9baa30d43d7d1b3d0342345f05ec0da26e1"


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def repair_imports(wheel: Path) -> int:
    """Qualify generated imports; the pinned upstream Windows build leaves them bare."""
    with zipfile.ZipFile(wheel) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    changed = 0
    for name, data in list(files.items()):
        if name.startswith("kipy/proto/") and name.endswith((".py", ".pyi")):
            repaired = re.sub(
                rb"(?m)^from (common|board|schematic)([. ]+)", rb"from kipy.proto.\1\2", data
            )
            changed += repaired != data
            files[name] = repaired
    (record,) = [name for name in files if name.endswith(".dist-info/RECORD")]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    for name, data in files.items():
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow([name, "sha256=" + digest, len(data)])
    writer.writerow([record, "", ""])
    files[record] = buffer.getvalue().encode()
    with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New disposable build directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive = download(
        f"https://gitlab.com/kicad/code/kicad-python/-/archive/{BINDINGS}/"
        f"kicad-python-{BINDINGS}.tar.gz"
    )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        bundle.extractall(output, filter="data")
    source = output / f"kicad-python-{BINDINGS}"
    hashes = {}
    page = 1
    while True:
        entries = json.loads(
            download(
                "https://gitlab.com/api/v4/projects/kicad%2Fcode%2Fkicad/repository/tree"
                f"?ref={PROTOCOL}&path=api/proto&recursive=true&per_page=100&page={page}"
            )
        )
        if not entries:
            break
        for entry in entries:
            if entry["type"] != "blob":
                continue
            path = entry["path"]
            if not path.startswith("api/proto/") or ".." in Path(path).parts:
                raise ValueError("unexpected protocol source path")
            data = download(f"https://gitlab.com/kicad/code/kicad/-/raw/{PROTOCOL}/{path}")
            target = source / "kicad" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            hashes[path] = hashlib.sha256(data).hexdigest()
        page += 1
    wheels = output / "wheels"
    with (output / "build.log").open("w", encoding="utf-8") as log:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(wheels), str(source)],
            stdout=log,
            stderr=log,
            check=True,
        )
    (wheel,) = wheels.glob("*.whl")
    repaired = repair_imports(wheel)
    evidence = {
        "bindings_commit": BINDINGS,
        "protocol_commit": PROTOCOL,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "protocol_file_sha256": hashes,
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "generated_import_files_repaired": repaired,
        "generated_api_version": "unknown (source archive has no git describe metadata)",
        "gui_acceptance": "not run",
    }
    (output / "build-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(wheel)
    print("SHA256:", evidence["wheel_sha256"])
    print("Build evidence:", output / "build-evidence.json")


if __name__ == "__main__":
    main()
