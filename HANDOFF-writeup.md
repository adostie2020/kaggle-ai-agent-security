# Handoff — Working-Note writeup: professional/scientific tone pass DONE (two-lever reframe), UNCOMMITTED

**Date:** 2026-09-01 (updated) · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** *AI Agent Security — Multi-Step Tool Attacks* (comp 134815; hosts OpenAI/Google/IEEE; $50k). **Final rank: 174 / 4252 (private).**

> Repo convention: this is the **writeup** topic handoff (`HANDOFF-<topic>.md`). Do **NOT** overwrite
> `HANDOFF.md` (master, owns `attack.py`) or the other `HANDOFF-*.md` files.

## ⭐ THE OPEN ITEM (start here)

**RESOLVED this session, then left UNCOMMITTED.** The user gave the concrete note that was missing:
*"update the writeup copy. Tone should be professional, scientific. NOT SLOP."* plus a verbatim new
README top-summary (the exemplar). Two decisions were confirmed via AskUserQuestion:
- **Poker depth = "light analogy"** — lead with the two levers, name poker exactly *once* per file as
  the intuition for "polarized," cut all the gambling color (value bet / bluff / dominated hand).
- **Scope = whole writeup + README** — full de-slop pass across all markdown cells; code cells +
  outputs untouched.

The tone pass is **done in the working tree** (README.md, WORKING_NOTE.ipynb markdown cells,
HANDOFF-writeup.md). It is **NOT committed or pushed** — the user asked to *update the copy*, not to
commit; per repo/Bash rule "commit or push only when the user asks." **Next session's first move:
ask whether to commit + push both branches (`master` + `repro-gguf-repoint`) to the public repo**, or
iterate further on tone.

The rewrite's spine is now the user's **two orthogonal levers**: **Lever 1 = candidate density**
(§0.2, §1 second bullet, README "Lever 1"), **Lever 2 = prompt diversity** (§3 retitled "Prompt
diversity and the correlated tail", README "Lever 2"). "Polarized" is kept as the strategy term;
"poker" appears once in cell-0 and once in the README only. Title changed **"…Polarized Range…" →
"…Polarized Portfolio…"** in both files (notebook `metadata.title` patched via the python text-swap
trick, since NotebookEdit can't reach it). One redundant README subsection ("Why the second bet has to
be structurally different") was deleted — Lever 2 already covers it. The one intentional Stackelberg
contrast line in §1 was kept.

## What this deliverable is

The optional organizer-judged **Working Note** (separate award track from the leaderboard; the note
itself is due **2026-09-08 23:59 UTC**). Deliverable = **`WORKING_NOTE.ipynb`** (repo root), a runnable
Jupyter notebook — the native Kaggle Working-Note form; 17 cells (5 code cells, pre-executed with
embedded stdout). A short-form **`README.md`** summarizes it for the GitHub landing page.

**Judging criteria** (from `dev/comp_pages.txt` "Working Note Judging Criteria"): (1) technical
clarity & reproducibility; (2) methodological contribution; (3) security insight; (4) usefulness to
the benchmark community; (5) responsible communication (benchmark-only; NO real-system attack
instructions). Keep every future edit responsible-comms clean: RFC 2606 / example.com hosts only,
defensive framing, each "attack" paired with its guardrail fix.

## Current progress (this session, 2026-09-01)

- **Metaphor reframed Stackelberg → poker** in BOTH the note and the README, per the user's explicit
  correction: *"i don't think stackelberg is the right metaphor... I like poker as a better example of
  an incomplete information game where polarized strategies are a good way to get value from more of
  the game tree."* Rationale captured in memory [[jed-poker-framing-not-stackelberg]]: the private
  guardrail is **fixed in advance and never best-responds** to our commit, so there is no
  leader/follower — it's an **incomplete-information (poker)** game, and *"polarized"* is a native
  poker term (value bet + bluff, skip the dominated middle → extract value from more of the game tree)
  that maps the two-slot submission exactly (Slot A density exfil = value bet; Slot B CD hedge =
  bluff; a 2nd exfil variant = the dominated medium hand you skip).
- **Cells edited (markdown only — all code cells + outputs untouched):** cell-0 (title + intro),
  cell-2 (§1 "The game"), cell-11 (§5 pick-2 decision), cell-13 (§7 — added the final private rank),
  cell-16 (§9 sources), plus the notebook's top-level `metadata.title`. One *intentional* "Stackelberg"
  mention remains in §1 as a didactic contrast ("*not* a leader/follower Stackelberg game...").
- **README.md written** (repo root, 12.6 KB): poker framing, a dedicated plain-language "polarized
  strategy" section (value bet / bluff / dominated medium hand, with the `E[max(0, B−A)]` formal
  backup), scoring/board/rig/defensive-takeaways summary, repo layout, repro commands.
- **Final rank 174 / 4252** recorded in the README headline and §7 (framed as the polarized portfolio
  transferring to the private board, up from public 396/4243).
- **Committed + published.** Commits `21cd91d` (README) and `fc1f5f6` (writeup reframe) on **both**
  `master` (default) and `repro-gguf-repoint`, pushed to GitHub. **Repo made PUBLIC** at the user's
  request: **https://github.com/adostie2020/kaggle-ai-agent-security** (competition closed, leak
  concern moot). Note: this supersedes the old "attack.py/writeup untracked by design" rule for these
  files — the user asked to commit + publish.

## Notebook-editing mechanics (learned this session — reuse these)

- **Cell prose:** use **`NotebookEdit`** (`cell_id` from the Read render, e.g. `cell-2`; `edit_mode`
  defaults to replace). You MUST `Read` the notebook in-conversation first.
- **Top-level `metadata.title`:** `NotebookEdit` only edits *cells*, and the plain `Edit` tool
  **refuses `.ipynb`** ("Use the NotebookEdit tool"). Workaround used: a tiny python text-replace
  script — `scratchpad/patch_title.py` (surgical string swap, `newline=""` to preserve line endings,
  no full JSON re-dump). Reuse that pattern for any non-cell field.
- **Validate after editing:** `.venv/Scripts/python.exe -c "import json; nb=json.load(open(r'...WORKING_NOTE.ipynb',encoding='utf-8')); print(len(nb['cells']), nb['metadata'].get('title'))"` — parses clean at 17 cells.
- **Re-commit + push:** working tree edits → `git add` → commit (trailer convention in `.git`) →
  `git push origin master repro-gguf-repoint` (both branches track; keep them in sync). Shell (git +
  `.venv` python) works in the current permission mode.

## What worked
- **Poker/polarized framing** is a genuinely better fit than Stackelberg — it *explains* the barbell
  instead of labeling it, and "polarized" is literally the poker term for it. The user liked the
  direction.
- **Markdown-only edits** kept the reproducibility intact (no re-execution needed; code cells + their
  embedded stdout are unchanged and still valid).

## What did NOT work / traps (don't repeat)
- **The builder is now STALE.** The note was originally generated by `scratchpad/build_working_note.py`,
  which still emits the **old Stackelberg** text. **Re-running it REVERTS the poker reframe.** The
  **`.ipynb` is now the source of truth** — edit the notebook directly; only touch the builder if you
  also port the poker changes into it first. (Recorded in memory [[jed-working-note-built]].)
- **`Edit` won't touch `.ipynb`** — don't fight it; use `NotebookEdit` for cells and the python
  text-patch trick for metadata.
- (Earlier) Stackelberg was the wrong frame — see the reframe above; don't reintroduce it beyond the
  one didactic contrast line.

## Next steps
1. **Clarify the copy ask (BLOCKING on the user).** Find out what specifically about the writeup prose
   isn't landing — see the ⭐ section's probe list. Let them lead.
2. **Revise the notebook prose** (NotebookEdit; markdown cells only unless a number changes). Keep the
   README in sync with any framing/wording change.
3. **Re-validate + re-commit + push** to the public repo (both branches). If numbers change, re-run
   the relevant code cell so embedded outputs stay honest.
4. **Optional:** if a rendered, shareable web page is ever wanted, an Artifact version was offered but
   not built (user chose the notebook) — would need the `artifact-design` skill and must not
   impersonate the competition/orgs.

## Pointers / where the detail lives
- **The note:** `WORKING_NOTE.ipynb` (repo root). **The summary:** `README.md`. **Builder (STALE):**
  `scratchpad/build_working_note.py`.
- **The thesis + judging criteria + source map** (still valid reference): earlier in this file's git
  history, and the design memories below.
- **Memories:** [[jed-poker-framing-not-stackelberg]] (the framing preference + why), [[jed-working-note-built]]
  (build status, publication, builder-drift warning), [[jed-cd-hedge-stress-test]],
  [[jed-hedge-shared-death-cd-seam]], [[jed-only-exfil-fireable]], [[jed-family-ceiling]],
  [[jed-v24-density-ab]], [[deliverables-go-in-working-dir]].
- **Underlying analysis artifacts:** `dev/benchmark/cd_hedge_matrix.py` → `_cd_hedge_matrix.{json,md}`
  (the survival×density matrix the note embeds); SDK source under `vendor/jed/aicomp_sdk/` for the
  `file:line` citations.
