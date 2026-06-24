"""sw_batch_execute — elicitation-gated MCP seat PAE (the in-chat approve→EXECUTE loop).

The automatable half of the Directive #4 Seat PAE: it proves the FULL wire path
end-to-end against the LIVE seat WITHOUT Claude Desktop, by driving the real
FastMCP server over an in-process MCP transport with a client that advertises
the elicitation capability and answers the approval prompt programmatically.

What it proves (the same mtime + feature-node witnesses as spike_cli_batch_pae):

  A decline_noops  : an in-process client whose elicitation_callback returns
                     accept+approve=False → the tool returns aborted, the
                     .sldprt mtime is UNCHANGED and a reopen shows the feature
                     count UNCHANGED (the in-chat [N] truly blocks the write).
  B approve_commits: a second call whose callback returns accept+approve=True →
                     the tool returns ok=True / doc_saved=True / committed=3,
                     exercising the irreversible batch(dry_run=False) commit.
  C disk_updated   : the .sldprt mtime ADVANCES and a reopen shows the feature
                     count grew by >=3 — the features really materialized on disk
                     through the elicitation gate.

What it does NOT prove (inherently human — see the runbook in the module
docstring of docs/, or RUNBOOK below): that Claude Desktop *renders* the
approval prompt in its UI and a human *clicks* it. That is the final
human-in-the-loop witness; this spike proves everything up to the rendering.

Run (singleton seat; mind the dual-SLDWORKS ROT trap — ensure ONE instance):
    PYTHONPATH=<repo>/src python spikes/v0_2x/spike_mcp_batch_execute_pae.py

RUNBOOK (the human UI witness, run after this spike is GREEN):
  1. Add this server to Claude Desktop's mcpServers config:
       "ai-sw-bridge": {"command": "ai-sw-mcp"}
     (ensure the entry runs in an env where `ai-sw-mcp` resolves + SW is up).
  2. Open the part this spike wrote (spikes/v0_2x/_results/mcp_batch_execute_pae.sldprt)
     or any .sldprt, then close it in SW (batch refuses the ACTIVE doc).
  3. In Claude Desktop, ask the agent to run sw_batch_execute with the 3-feature
     batch (ref_plane / scale / com_point) against that path.
  4. WITNESS: the approval prompt appears IN THE CHAT SURFACE. Click approve.
  5. Verify the part's mtime advanced and the feature tree gained the 3 features.
  Decline path: re-run, click decline → no mtime change, tree unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
_SRC = _REPO / "src"
for _p in (str(_SRC), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import anyio  # noqa: E402
import pythoncom  # noqa: E402
import win32com.client as w32  # noqa: E402
from win32com.client import VARIANT  # noqa: E402

from mcp import ClientSession  # noqa: E402
from mcp.shared.context import RequestContext  # noqa: E402
from mcp.shared.memory import create_client_server_memory_streams  # noqa: E402
import mcp.types as types  # noqa: E402

from ai_sw_bridge.com.sw_type_info import wrapper_module  # noqa: E402
from ai_sw_bridge.features import verify  # noqa: E402
from ai_sw_bridge.mcp.runtime import ServerRuntime  # noqa: E402
from ai_sw_bridge.mcp.server import create_server  # noqa: E402
from ai_sw_bridge.sw_com import release_sw_app  # noqa: E402
import _feature_spike_fixtures as fx  # noqa: E402

_RESULTS = _HERE.parent / "_results"
_OUT = _RESULTS / "mcp_batch_execute_pae.json"
results: dict[str, Any] = {"pae": "mcp_batch_execute", "gates": {}}

PROPOSALS = [
    {
        "feature": {"type": "ref_plane", "distance_mm": 25.0},
        "target": {"plane": "Front Plane"},
    },
    {"feature": {"type": "scale", "scale_factor": 1.5}, "target": {}},
    {"feature": {"type": "com_point"}, "target": {}},
]


def gate(name: str, ok: bool, detail: str = "") -> bool:
    results["gates"][name] = {"ok": bool(ok), "detail": str(detail)}
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return bool(ok)


def _finish() -> int:
    all_pass = bool(results["gates"]) and all(
        g["ok"] for g in results["gates"].values()
    )
    results["verdict"] = "GREEN" if all_pass else "PARTIAL"
    _RESULTS.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nVerdict: {results['verdict']}  (wrote {_OUT})")
    return 0 if all_pass else 1


def _close_all(sw: Any) -> None:
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass


def _build_block_to_disk(sw: Any, path: Path) -> None:
    _close_all(sw)
    doc = fx.build_block(sw)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    doc.SaveAs3(str(path), 0, 0)
    _close_all(sw)


def _reopen_node_count(sw: Any, path: Path) -> int:
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    doc = sw.OpenDoc6(str(path), 1, 1, "", errs, warns)
    n = verify.feature_node_count(doc)
    _close_all(sw)
    return n


def _make_callback(approve: bool):
    """An elicitation_callback that auto-answers the in-chat approval prompt.

    Returns accept with the given approve flag — simulating a human clicking
    [approve] (True) or unticking it (False) in the client UI. Providing ANY
    non-default callback is what makes ClientSession advertise the elicitation
    capability, so the server's capability gate passes.
    """

    async def _cb(
        context: RequestContext["ClientSession", Any],
        params: types.ElicitRequestParams,
    ) -> types.ElicitResult:
        results.setdefault("prompts_seen", []).append(params.message[:120])
        return types.ElicitResult(action="accept", content={"approve": approve})

    return _cb


async def _call_execute(part: Path, approve: bool) -> dict | None:
    """Boot the real server in-process, connect an elicitation-capable client,
    call sw_batch_execute, and return the parsed manifest.

    HARNESS NOTE: this spike boots a SEPARATE ServerRuntime per call (decline,
    then approve) inside ONE process — something the real long-lived MCP server
    never does. Run 1's executor thread caches the SldWorks dispatch in the
    module-level ``sw_com`` cache, BOUND to that STA thread; ``shutdown()`` kills
    the thread but leaves the cache populated, so run 2's fresh executor would
    reuse a dead-thread handle and raise CO_E_OBJNOTCONNECTED (0x800401FD). We
    drop the cache before each boot so each runtime re-acquires a live dispatch
    on its OWN thread. (Not a tool concern — one process = one runtime in prod.)
    """
    release_sw_app()
    runtime = ServerRuntime.create()  # pywin32 adapter on Windows = live SW
    runtime.adapter.connect()
    runtime.executor.start()
    mcp = create_server(runtime)
    manifest: dict | None = None
    try:
        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: mcp._mcp_server.run(
                        server_read,
                        server_write,
                        mcp._mcp_server.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(
                        read_stream=client_read,
                        write_stream=client_write,
                        elicitation_callback=_make_callback(approve),
                    ) as session:
                        await session.initialize()
                        res = await session.call_tool(
                            "sw_batch_execute",
                            arguments={"file_path": str(part), "proposals": PROPOSALS},
                        )
                        # FastMCP envelope: content=[TextContent(text=<json>)].
                        for item in res.content:
                            txt = getattr(item, "text", None)
                            if txt:
                                manifest = json.loads(txt[txt.index("{") :])
                                break
                finally:
                    tg.cancel_scope.cancel()
    finally:
        runtime.shutdown()
    return manifest


def main() -> int:
    pythoncom.CoInitialize()
    _ = wrapper_module()
    _RESULTS.mkdir(parents=True, exist_ok=True)
    sw = w32.Dispatch("SldWorks.Application")

    part = _RESULTS / "mcp_batch_execute_pae.sldprt"
    try:
        # --- A decline first on a fresh block: the in-chat [N] blocks the write ---
        _build_block_to_disk(sw, part)
        nodes0 = _reopen_node_count(sw, part)
        mtime0 = part.stat().st_mtime_ns
        man_n = anyio.run(_call_execute, part, False)
        results["decline_manifest"] = man_n
        nodes_n = _reopen_node_count(sw, part)
        mtime_n = part.stat().st_mtime_ns
        gate(
            "decline_noops",
            bool(man_n)
            and man_n.get("aborted") is True
            and man_n.get("reason") in ("declined_in_form", "declined", "cancelled")
            and mtime_n == mtime0
            and nodes_n == nodes0,
            f"aborted={man_n.get('aborted') if man_n else None} "
            f"reason={man_n.get('reason') if man_n else None} "
            f"mtime_unchanged={mtime_n == mtime0} nodes {nodes0}->{nodes_n}",
        )

        # --- B + C approve on a fresh block: the commit must PERSIST ---
        _build_block_to_disk(sw, part)
        nodes_before = _reopen_node_count(sw, part)
        mtime_before = part.stat().st_mtime_ns
        man_y = anyio.run(_call_execute, part, True)
        results["commit_manifest"] = man_y
        gate(
            "approve_commits",
            bool(man_y)
            and man_y.get("ok") is True
            and man_y.get("approved") is True
            and man_y.get("committed_count") == 3
            and man_y.get("doc_saved") is True,
            f"ok={man_y.get('ok') if man_y else None} "
            f"approved={man_y.get('approved') if man_y else None} "
            f"committed={man_y.get('committed_count') if man_y else None} "
            f"kinds={[c.get('kind') for c in (man_y or {}).get('committed', [])]}",
        )

        nodes_after = _reopen_node_count(sw, part)
        mtime_after = part.stat().st_mtime_ns
        gate(
            "disk_updated",
            mtime_after > mtime_before and nodes_after >= nodes_before + 3,
            f"mtime_advanced={mtime_after > mtime_before} "
            f"nodes {nodes_before}->{nodes_after} (expect +3 materialized)",
        )
    finally:
        _close_all(sw)
        pythoncom.CoUninitialize()
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
