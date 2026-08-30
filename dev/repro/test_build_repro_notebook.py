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

    # GGUF run: setup cell installs the cu124 wheel + sets HF_HOME; run cell carries --backend
    g = b.build(model="gpt_oss", n_candidates=2, backend="gguf")
    gsrc = "\n".join("".join(c["source"]) for c in g["cells"])
    assert "--backend" in gsrc and "gguf" in gsrc, "backend not wired into gguf run cell"
    assert "llama-cpp-python" in gsrc, "gguf setup cell missing llama.cpp install"
    assert "cu124" in gsrc, "gguf setup cell missing cu124 extra-index-url"
    assert "HF_HOME" in gsrc and "/kaggle/temp" in gsrc, "gguf setup cell missing HF_HOME"
    # setup cell must not masquerade as the embed or run cell
    assert "subprocess.run" not in "".join(
        c2 for c in g["cells"] if "llama-cpp-python" in "".join(c["source"])
        for c2 in c["source"]
    ), "setup cell must not contain subprocess.run"

    # hf run: no llama install cell, still carries --backend hf
    h = b.build(model="gpt_oss", n_candidates=2, backend="hf")
    hsrc = "\n".join("".join(c["source"]) for c in h["cells"])
    assert "--backend" in hsrc and "hf" in hsrc
    assert "llama-cpp-python" not in hsrc, "hf run should not install llama.cpp"

    # deterministic gguf: no llama install (deterministic needs no GGUF backend)
    d = b.build(model="deterministic", n_candidates=2, backend="gguf")
    dsrc = "\n".join("".join(c["source"]) for c in d["cells"])
    assert "llama-cpp-python" not in dsrc, "deterministic must not install llama.cpp"

    # --guardrail wiring: a stochastic profile threads the selector into the run cell and
    # embeds the benchmark guardrails module so the kernel can import it (push-only path).
    gg = b.build(model="gpt_oss", n_candidates=2, guardrail="strict_default",
                 base_seed=0, member=1)
    gg_all = "\n".join("".join(c["source"]) for c in gg["cells"])
    assert "--guardrail" in gg_all and "strict_default" in gg_all, "guardrail not wired into run cell"
    assert "--member" in gg_all, "member not wired into run cell"
    gg_embed = ["".join(c["source"]) for c in gg["cells"]
                if c["cell_type"] == "code" and "b64decode" in "".join(c["source"])]
    assert len(gg_embed) == 1, f"expected 1 embed cell, found {len(gg_embed)}"
    assert "/kaggle/working/repro_pkg/guardrails.py" in gg_embed[0], \
        "stochastic guardrail run must embed the benchmark guardrails module"

    # LEAKAGE SAFETY: the default (optimal) build must NOT embed guardrails.py. The
    # committed reference notebook is built via main() at guardrail=optimal, so it must
    # never carry the held-out hypothesis rules (a base64 blob the attack.py session could
    # decode). Only the push path, built in memory with a stochastic --guardrail, embeds them.
    opt = b.build(model="gpt_oss", n_candidates=2)  # guardrail defaults to optimal
    opt_embed = ["".join(c["source"]) for c in opt["cells"]
                 if c["cell_type"] == "code" and "b64decode" in "".join(c["source"])][0]
    assert "/kaggle/working/repro_pkg/guardrails.py" not in opt_embed, \
        "optimal build must NOT embed the guardrails rules (leakage into committed notebook)"

    print("test_build_repro_notebook: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
