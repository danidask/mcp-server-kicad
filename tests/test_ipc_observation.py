"""Policy/error tests for experimental read-only IPC, independent of KiCad."""

from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_kicad import _ipc, project
from mcp_server_kicad.models import LiveDocument


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("KICAD_API_SOCKET", "ipc://explicit-instance")
    monkeypatch.setenv("KICAD_API_TOKEN", "secret-instance-token")


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"document_type": "invalid"}, "document_type"),
        ({"timeout_ms": 0}, "timeout_ms"),
        ({"timeout_ms": 10001}, "timeout_ms"),
        ({"endpoint": "tcp://remote"}, "explicit ipc://"),
        ({"document_id": "id"}, "both document_id"),
        ({"expected_project": "directory"}, "both document_id"),
        ({"document_id": "id", "expected_project": "relative"}, "absolute"),
    ],
)
def test_invalid_target_never_connects(configured, monkeypatch, kwargs, message):
    def forbidden():
        pytest.fail("invalid requests must fail before loading transport")

    monkeypatch.setattr(_ipc, "_load_bindings", forbidden)
    with pytest.raises(ToolError, match=message):
        project.get_live_snapshot(**kwargs)


def test_no_guessed_endpoint_or_token(monkeypatch):
    monkeypatch.delenv("KICAD_API_SOCKET", raising=False)
    monkeypatch.delenv("KICAD_API_TOKEN", raising=False)
    with pytest.raises(ToolError, match="default socket is never guessed"):
        project.get_live_snapshot()
    with pytest.raises(ToolError, match="Set KICAD_API_TOKEN"):
        project.get_live_snapshot(endpoint="ipc://explicit")


def test_missing_bindings_actionable(configured, monkeypatch):
    def missing(_):
        raise _ipc.PackageNotFoundError

    monkeypatch.setattr(_ipc, "version", missing)
    with pytest.raises(ToolError, match="No disk fallback"):
        project.get_live_snapshot()


def test_released_bindings_refused(configured, monkeypatch):
    monkeypatch.setattr(_ipc, "version", lambda _: "0.8.0")
    with pytest.raises(ToolError, match="Released 0.8.0 is insufficient"):
        project.get_live_snapshot()


def test_allowlist_blocks_mutator_before_transport():
    reader = _ipc._Reader.__new__(_ipc._Reader)
    command = SimpleNamespace(
        DESCRIPTOR=SimpleNamespace(full_name="kiapi.common.commands.SaveDocument")
    )
    with pytest.raises(ToolError, match="read-only allowlist"):
        reader.send(command, object)


def test_transport_errors_do_not_leak_secrets():
    reader = _ipc._Reader.__new__(_ipc._Reader)
    reader.bindings = {}

    def failure(*_):
        raise RuntimeError("secret-instance-token and secret endpoint")

    reader.client = SimpleNamespace(send=failure)
    command = SimpleNamespace(
        DESCRIPTOR=SimpleNamespace(full_name="kiapi.common.commands.GetItems", name="GetItems")
    )
    with pytest.raises(ToolError) as error:
        reader.send(command, object)
    assert "secret" not in str(error.value)
    assert "No disk fallback" in str(error.value)


@pytest.fixture
def fake_reader(configured, monkeypatch, tmp_path):
    doc = SimpleNamespace(project=SimpleNamespace(path=str(tmp_path)))
    identity = LiveDocument(id="selected", identity={"project": {"path": str(tmp_path)}})

    class Reader:
        snapshots = [{"items": [{"id": "stable", "position": 1}]}] * 2
        entries = [(identity, doc)]
        closed = False

        def __init__(self, *_):
            self.client = SimpleNamespace(close=self.close)

        def close(self):
            type(self).closed = True

        def send(self, *_):
            return {"version": {"full_version": "native"}}

        def as_dict(self, value):
            return value

        def documents(self, *_):
            return self.entries

        def snapshot(self, *_):
            return self.snapshots.pop(0)

    monkeypatch.setattr(_ipc, "_Reader", Reader)
    monkeypatch.setattr(
        _ipc,
        "_load_bindings",
        lambda: {
            "version": "experimental",
            "api": SimpleNamespace(KICAD_API_VERSION="known"),
            "base": SimpleNamespace(GetVersion=lambda: None, GetVersionResponse=None),
        },
    )
    return Reader, str(tmp_path)


@pytest.mark.parametrize("case", ["missing", "ambiguous", "wrong_project", "changed"])
def test_target_and_stale_refusals_close_transport(fake_reader, case):
    reader, directory = fake_reader
    if case == "missing":
        reader.entries = []
    elif case == "ambiguous":
        reader.entries *= 2
    elif case == "wrong_project":
        directory += "/other"
    else:
        reader.snapshots = [{"items": []}, {"items": [{"id": "external-edit"}]}]
    with pytest.raises(ToolError):
        project.get_live_snapshot(document_id="selected", expected_project=directory)
    assert reader.closed


def test_new_observation_rereads_and_has_no_cached_state(fake_reader):
    reader, directory = fake_reader
    first = project.get_live_snapshot(document_id="selected", expected_project=directory)
    reader.snapshots = [{"items": [{"id": "stable", "position": 2}]}] * 2
    second = project.get_live_snapshot(document_id="selected", expected_project=directory)
    assert first.fingerprint != second.fingerprint
    assert first.snapshot["items"][0]["id"] == second.snapshot["items"][0]["id"]
    assert reader.closed
