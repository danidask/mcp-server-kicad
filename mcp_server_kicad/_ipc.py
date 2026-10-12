"""Experimental, explicitly targeted read-only IPC observation.

The optional development bindings are deliberately not a runtime dependency
until the GUI acceptance gate in docs/kicad11-migration.md is satisfied. This
module never opens, saves, exports, or mutates a document and never reads disk
design data as a substitute for IPC. All requests go through a read allowlist.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError

from mcp_server_kicad.models import LiveDocument, LiveSnapshotResult

_LOCK = threading.Lock()
_READ_COMMANDS = {
    "kiapi.common.commands.GetVersion",
    "kiapi.common.commands.GetOpenDocuments",
    "kiapi.common.commands.GetItems",
    "kiapi.schematic.commands.GetSchematicHierarchy",
    "kiapi.schematic.commands.GetSchematicNetlist",
    "kiapi.board.commands.GetNets",
    "kiapi.board.commands.GetBoardDesignRules",
    "kiapi.board.commands.GetCustomDesignRules",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load_bindings() -> dict[str, Any]:
    try:
        binding_version = version("kicad-python")
        if binding_version != "0.9.0.dev0":
            raise ToolError(
                "Live observation needs the pinned experimental kicad-python 0.9.0.dev0 "
                "build; see docs/ipc-observation.md. Released 0.8.0 is insufficient."
            )
        modules = {
            "client": "kipy.client",
            "base": "kipy.proto.common.commands.base_commands_pb2",
            "editor": "kipy.proto.common.commands.editor_commands_pb2",
            "types": "kipy.proto.common.types",
            "board": "kipy.proto.board.board_commands_pb2",
            "schematic": "kipy.proto.schematic.schematic_commands_pb2",
            "envelope": "kipy.proto.common.envelope_pb2",
            "json": "google.protobuf.json_format",
            "api": "kipy.kicad_api_version",
        }
        result: dict[str, Any] = {
            key: importlib.import_module(name) for key, name in modules.items()
        }
        result["version"] = binding_version
        return result
    except (ImportError, PackageNotFoundError):
        raise ToolError(
            "Experimental IPC bindings are missing or cannot load. Install the pinned "
            "wheel in the server's Python environment; see docs/ipc-observation.md. "
            "No disk fallback was attempted."
        ) from None


class _Reader:
    def __init__(self, bindings: dict[str, Any], endpoint: str, token: str, timeout_ms: int):
        self.bindings = bindings
        self.client = bindings["client"].KiCadClient(
            endpoint, "mcp-server-kicad-observer", token, timeout_ms
        )

    def send(self, command: Any, response_type: Any) -> Any:
        if command.DESCRIPTOR.full_name not in _READ_COMMANDS:
            raise ToolError("IPC observation refused a command outside its read-only allowlist.")
        try:
            return self.client.send(command, response_type)
        except Exception as exc:
            # Native errors may include endpoint/token or user-controlled data.
            # Only expose the status name, never the raw exception/message.
            code = getattr(exc, "code", None)
            status = "connection/busy/timeout or incompatible response"
            if isinstance(code, int):
                try:
                    status = self.bindings["envelope"].ApiStatusCode.Name(code)
                except ValueError:
                    status = "unknown API status"
            raise ToolError(
                f"IPC {command.DESCRIPTOR.name} failed ({status}). Check the selected "
                "instance, API setting and token; dismiss modal dialogs and observe again. "
                "No disk fallback was attempted."
            ) from None

    def as_dict(self, message: Any) -> dict[str, Any]:
        return self.bindings["json"].MessageToDict(
            message, preserving_proto_field_name=True, always_print_fields_with_no_presence=True
        )

    def documents(self, document_type: str) -> list[tuple[LiveDocument, Any]]:
        b = self.bindings
        command = b["editor"].GetOpenDocuments()
        command.type = getattr(b["types"].DocumentType, "DOCTYPE_" + document_type.upper())
        response = self.send(command, b["editor"].GetOpenDocumentsResponse)
        found = []
        for doc in response.documents:
            identity = self.as_dict(doc)
            found.append((LiveDocument(id=_digest(identity), identity=identity), doc))
        return sorted(found, key=lambda pair: pair[0].id)

    def snapshot(self, document: Any, document_type: str) -> dict[str, Any]:
        b = self.bindings
        command = b["editor"].GetItems()
        command.header.document.CopyFrom(document)
        prefix = "KOT_PCB_" if document_type == "pcb" else "KOT_SCH_"
        command.types.extend(
            value for name, value in b["types"].KiCadObjectType.items() if name.startswith(prefix)
        )
        items = self.send(command, b["editor"].GetItemsResponse)
        state: dict[str, Any] = {
            "items": sorted((self.as_dict(item) for item in items.items), key=_canonical)
        }
        if document_type == "schematic":
            for name, request, reply in (
                ("hierarchy", "GetSchematicHierarchy", "SchematicHierarchyResponse"),
                ("netlist", "GetSchematicNetlist", "SchematicNetlistResponse"),
            ):
                query = getattr(b["schematic"], request)()
                query.document.CopyFrom(document)
                state[name] = self.as_dict(self.send(query, getattr(b["schematic"], reply)))
        else:
            for name, request, reply in (
                ("nets", "GetNets", "NetsResponse"),
                ("design_rules", "GetBoardDesignRules", "BoardDesignRulesResponse"),
                ("custom_rules", "GetCustomDesignRules", "CustomRulesResponse"),
            ):
                query = getattr(b["board"], request)()
                query.board.CopyFrom(document)
                state[name] = self.as_dict(self.send(query, getattr(b["board"], reply)))
        return state


def observe(
    endpoint: str = "",
    document_type: Literal["pcb", "schematic"] = "pcb",
    document_id: str = "",
    expected_project: str = "",
    timeout_ms: int = 2000,
) -> LiveSnapshotResult:
    if document_type not in ("pcb", "schematic"):
        raise ToolError("document_type must be pcb or schematic.")
    if not isinstance(timeout_ms, int) or not 100 <= timeout_ms <= 10000:
        raise ToolError("timeout_ms must be between 100 and 10000.")
    endpoint = endpoint or os.environ.get("KICAD_API_SOCKET", "")
    token = os.environ.get("KICAD_API_TOKEN", "")
    if not endpoint.startswith("ipc://") or not endpoint.removeprefix("ipc://").strip():
        raise ToolError(
            "Select an explicit ipc:// endpoint or set KICAD_API_SOCKET from KiCad's "
            "plugin environment. The default socket is never guessed."
        )
    if not token:
        raise ToolError(
            "Set KICAD_API_TOKEN from the intended KiCad instance; tokens are not tool arguments."
        )
    if bool(document_id) != bool(expected_project):
        raise ToolError(
            "Provide both document_id and expected_project for a snapshot, or neither to enumerate."
        )
    if expected_project and not Path(expected_project).is_absolute():
        raise ToolError(
            "expected_project must be the absolute project directory returned by enumeration."
        )

    b = _load_bindings()
    with _LOCK:
        reader = _Reader(b, endpoint, token, timeout_ms)
        try:
            native_version = reader.as_dict(
                reader.send(b["base"].GetVersion(), b["base"].GetVersionResponse)
            )
            documents = reader.documents(document_type)
            result = LiveSnapshotResult(
                python_version=platform.python_version(),
                bindings_version=b["version"],
                protocol_version=b["api"].KICAD_API_VERSION,
                kicad_version=native_version,
                documents=[info for info, _ in documents],
                warnings=[
                    "Experimental protocol coverage; unknown native fields may be omitted.",
                    "Repeated reads detect observed changes but are not an atomic editor snapshot.",
                    "Dirty state, live ERC/DRC, complete rule evaluation and live writes "
                    "are unsupported.",
                ],
            )
            if not document_id:
                return result
            matches = [(info, doc) for info, doc in documents if info.id == document_id]
            if len(matches) != 1:
                raise ToolError(
                    "Live document identity is missing or ambiguous; enumerate the endpoint again."
                )
            ((selected, document),) = matches
            actual_project = document.project.path
            if os.path.normcase(os.path.normpath(actual_project)) != os.path.normcase(
                os.path.normpath(expected_project)
            ):
                raise ToolError("Selected live document belongs to a different project directory.")
            first = reader.snapshot(document, document_type)
            second = reader.snapshot(document, document_type)
            if first != second or documents != reader.documents(document_type):
                raise ToolError(
                    "Live state changed during observation; observe again after editing settles."
                )
            result.selected_document = selected
            result.snapshot = second
            result.fingerprint = _digest(second)
            result.observed_sections = list(second)
            return result
        finally:
            reader.client.close()
