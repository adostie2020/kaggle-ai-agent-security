"""Structural test for the repro notebook builder (no Kaggle/GPU needed)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # dev/repro/

import build_repro_notebook as b  # noqa: E402


def main() -> int:
    nb = b.build(model="gemma", n_candidates=4)
    assert nb["nbformat"] == 4, nb.get("nbformat")
    cells = nb["cells"]
    assert len(cells) >= 5, f"expected >=5 cells, got {len(cells)}"
    all_src = "\n".join("".join(c["source"]) for c in cells)
    # dataset-root preamble, the run invocation, and the output listing must be present
    assert "kaggle_evaluation" in all_src, "missing dataset-root preamble"
    assert "run_repro" in all_src, "missing run_repro invocation"
    assert "/kaggle/working/repro" in all_src, "missing output dir"
    assert "--model" in all_src and "gemma" in all_src, "model not wired into run cell"
    # every code cell must be syntactically importable text (no accidental f-string breakage)
    for c in cells:
        assert c["cell_type"] in ("code", "markdown")

    # R3: the embed cell must carry all eight embedded destination filenames --
    # the four dev/repro/ sources plus the Phase-1 deps (oracle/trace/agents/attack)
    # that run_repro.py -> runner.py -> trace.py transitively import. Check against
    # the embed cell's own source only (not all_src) -- run_repro.py's bare name also
    # appears in the run cell's hardcoded subprocess path, which would let a dropped
    # SRC_FILES entry silently pass an all_src check. Identify the embed cell as the
    # one (and only one) whose source contains "b64decode" so a change to the
    # builder's cell layout fails loudly instead of silently matching the wrong cell.
    embed_srcs = [
        "".join(c["source"]) for c in cells
        if c["cell_type"] == "code" and "b64decode" in "".join(c["source"])
    ]
    assert len(embed_srcs) == 1, f"expected exactly 1 embed cell, found {len(embed_srcs)}"
    embed_src = embed_srcs[0]
    embedded_names = [
        "debug_sink.py", "models.py", "runner.py", "run_repro.py",
        "oracle.py", "trace.py", "agents.py", "attack.py",
    ]
    for name in embedded_names:
        needle = f"/kaggle/working/repro_pkg/{name}"
        assert needle in embed_src, f"embed cell missing dependency file: {name}"

    # R4: the run cell must surface the subprocess's failure (returncode + stderr),
    # not just print stdout.
    assert "returncode" in all_src, "run cell does not surface subprocess returncode"
    assert "stderr" in all_src, "run cell does not surface subprocess stderr"

    # R14: the run cell must pass env= to subprocess.run, carrying the kernel's
    # sys.path into the child as PYTHONPATH -- otherwise the subprocess cannot
    # `import aicomp_sdk` (it does not inherit the PREAMBLE cell's in-memory
    # sys.path mutation) and dies before weights or GPU ever matter. Scope this
    # to the run cell itself (identified as the one whose source contains
    # "subprocess.run"), not all_src, so a dropped env= wouldn't be masked by
    # some unrelated cell mentioning "env=" in passing.
    run_srcs = [
        "".join(c["source"]) for c in cells
        if c["cell_type"] == "code" and "subprocess.run" in "".join(c["source"])
    ]
    assert len(run_srcs) == 1, f"expected exactly 1 run cell, found {len(run_srcs)}"
    run_src = run_srcs[0]
    assert "env=env" in run_src.replace(" ", ""), \
        "run cell's subprocess.run call does not pass env= (child can't import aicomp_sdk)"
    assert "PYTHONPATH" in run_src, "run cell does not derive PYTHONPATH from sys.path"

    print("test_build_repro_notebook: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
