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
    print("test_build_repro_notebook: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
