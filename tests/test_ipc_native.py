"""Opt-in native reads on the pinned build; these do not prove GUI unsaved edits.

Run with KICAD_IPC_NATIVE=1 in the isolated pinned-bindings environment. Missing
prerequisites fail when opted in, rather than silently skipping native evidence.
"""

import hashlib
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from mcp_server_kicad import project
from mcp_server_kicad._shared import _find_kicad_cli

pytestmark = pytest.mark.skipif(
    os.environ.get("KICAD_IPC_NATIVE") != "1", reason="opt-in pinned native IPC integration"
)


@contextmanager
def headless(target, monkeypatch):
    from kipy import KiCad

    cli = _find_kicad_cli()
    assert cli is not None, "native IPC was requested but KiCad CLI is unavailable"
    socket = target.with_suffix(".sock")
    endpoint = "ipc://" + str(socket)
    process = subprocess.Popen(
        [cli, "api-server", str(target), "--socket", str(socket)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            client = KiCad(socket_path=endpoint, kicad_token="", timeout_ms=500)
            try:
                native_version = client.get_version().full_version
                assert native_version == "10.99.0-5265-g0616634034"
                # Bootstrap only this newly launched disposable process's token.
                # Production observer requires the explicit instance token.
                token = client._client._kicad_token
                break
            except Exception:
                if process.poll() is not None or time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
            finally:
                client._client.close()
        monkeypatch.setenv("KICAD_API_TOKEN", token)
        yield endpoint
    finally:
        process.terminate()
        process.wait(timeout=10)


def capture(endpoint, kind, directory):
    listing = project.get_live_snapshot(endpoint=endpoint, document_type=kind)
    assert len(listing.documents) == 1
    return project.get_live_snapshot(
        endpoint=endpoint,
        document_type=kind,
        document_id=listing.documents[0].id,
        expected_project=str(directory),
    )


def test_native_headless_schematic(tmp_path, monkeypatch):
    target = tmp_path / "native.kicad_sch"
    target.write_bytes(Path("tests/fixtures/kicad_native.kicad_sch").read_bytes())
    digest = hashlib.sha256(target.read_bytes()).digest()
    with headless(target, monkeypatch) as endpoint:
        result = capture(endpoint, "schematic", tmp_path)
        again = capture(endpoint, "schematic", tmp_path)
        assert result.fingerprint == again.fingerprint
        state = result.snapshot
        symbols = [i for i in state["items"] if i["@type"].endswith("SchematicSymbolInstance")]
        assert len(symbols) == 1
        assert symbols[0]["id"]["value"] == "a1b2c3d4-0003-0003-0003-000000000001"
        assert symbols[0]["reference_field"]["text"]["text"] == "R1"
        assert symbols[0]["value_field"]["text"]["text"] == "10K"
        assert symbols[0]["position"] == {"x_nm": "100000000", "y_nm": "100000000"}
        assert state["hierarchy"]["top_level_sheets"][0]["path"]["path"][0]["value"] == (
            "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        )
        net = next(n for n in state["netlist"]["nets"] if n["name"] == "/TEST_NET")
        assert {i["value"] for i in net["sheets"][0]["items"]} == {
            "a1b2c3d4-0001-0001-0001-000000000001",
            "a1b2c3d4-0002-0002-0002-000000000001",
        }
    assert hashlib.sha256(target.read_bytes()).digest() == digest


def test_native_headless_pcb(scratch_pcb, monkeypatch):
    digest = hashlib.sha256(scratch_pcb.read_bytes()).digest()
    with headless(scratch_pcb, monkeypatch) as endpoint:
        result = capture(endpoint, "pcb", scratch_pcb.parent)
        state = result.snapshot
        footprints = [i for i in state["items"] if i["@type"].endswith("FootprintInstance")]
        # The fixture is independently built with kiutils, including a 0.25 mm
        # trace on Net1 and a footprint centered at (100 mm, 100 mm).
        assert len(footprints) == 1
        assert footprints[0]["position"] == {"x_nm": "100000000", "y_nm": "100000000"}
        tracks = [i for i in state["items"] if i["@type"].endswith("Track")]
        assert len(tracks) == 1
        assert tracks[0]["width"]["value_nm"] == "250000"
        assert tracks[0]["net"]["name"] == "Net1"
        assert {net["name"] for net in state["nets"]["nets"]} >= {"Net1", "Net2"}
        assert "design_rules" in state and "custom_rules" in state
    assert hashlib.sha256(scratch_pcb.read_bytes()).digest() == digest


def test_native_wrong_token_refused(tmp_path, monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    target = tmp_path / "native.kicad_sch"
    target.write_bytes(Path("tests/fixtures/kicad_native.kicad_sch").read_bytes())
    with headless(target, monkeypatch) as endpoint:
        monkeypatch.setenv("KICAD_API_TOKEN", "wrong-instance-token")
        with pytest.raises(ToolError, match="AS_TOKEN_MISMATCH"):
            project.get_live_snapshot(endpoint=endpoint, document_type="schematic")
