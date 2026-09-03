# Handoff — Working-Note writeup: outcome-correction pass APPLIED (research brief §05), committed

**Date:** 2026-09-02 (updated) · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** *AI Agent Security — Multi-Step Tool Attacks* (comp 134815; hosts OpenAI/Google/IEEE; $50k).
**Working Note deadline: 2026-09-08 23:59 UTC.**

> Repo convention: this is the **writeup** topic handoff (`HANDOFF-<topic>.md`). Do **NOT** overwrite
> `HANDOFF.md` (master, owns `attack.py`) or the other `HANDOFF-*.md` files.

## ⭐ THE OPEN ITEM (start here)

**Verify the realized private scores on Kaggle.** The entire reframe below rests on one premise that
has **not** been machine-verified in any session:

- Slot A, density-v1 (`55916596`, public 91.265) → **private ZERO** (killed by a `data`-payload
  `SECRET_MARKER` grep = the pre-registered `det_marker_data` world).
- Slot B, CD v1 (`55918818`, public 16.695) → **survived and carried 174 / 4252**.

This came from the user's own report and is recorded in memory `jed-realized-outcome-cd-v1-won`. Both
the deep-research session and this one hit **`Unauthenticated`** on the Kaggle MCP server
(`mcp__kaggle__authorize` returns a schema-invalid payload), so it is asserted, not confirmed. The
distinction that matters: **"zeroed" vs merely "low"** — "zeroed by the marker grep" is a claim about
*which defender world occurred*, and it is load-bearing for every §5/§8 claim in the note.

**Recovery path:** the REST recipe in `HANDOFF-resubmit.md` ("One-shot status check") using the file
token in `~/.claude/.credentials.json`, plus the documented OAuth refresh. Confirm `privateScore` on
both refs before the note is submitted for judging.

## What this deliverable is

The optional organizer-judged **Working Note** (separate award track from the leaderboard; 2 × $2,500).
Deliverable = **`WORKING_NOTE.ipynb`** (repo root), a runnable notebook — now **19 cells** (5 code
cells, pre-executed, outputs untouched throughout). **`README.md`** is the short version for the
GitHub landing page.

**Judging criteria** (verified first-party via the authenticated Kaggle API during the research
session, from the Evaluation page's "Working Note Judging Criteria (Optional)"): (1) technical clarity
& reproducibility — *names "assumptions" explicitly*; (2) methodological contribution; (3) security
insight; (4) usefulness to the benchmark community; (5) responsible communication. **Rank is not a
criterion** — the page states the awards "will not be determined solely by leaderboard rank."

## What changed this session (2026-09-02)

Applied §05 "Prioritized edits" of the **Working Note Revision Brief**, the deliverable of deep-research
session `c21db418` (5 angles, 110 claims, 75 adversarial verification votes; Artifact:
https://claude.ai/code/artifact/c2c3319b-00fd-4783-b177-2a26cff3a48c). That session was **read-only** —
it produced the brief and a memory note but never edited the repo, which is why these edits were
outstanding.

**P1 — the accuracy fix (do not regress this).** The README previously described the
`StochasticGuardrail` blake2b draw and the payoff matrix in adjacent paragraphs, which asserted the
matrix came from *"sampling a distribution of defenders."* It does not. Verified in source:
`cd_hedge_matrix.py:92` runs `base_seed=0, k=1` (an ensemble of one) and the CD worlds are `det_*`
profiles whose rules are declared `p=1.0` at `guardrails.py:272-279`. Both documents now frame the
matrix as **exact enumeration over a specified defender space** — a census, not an estimate — and
state that the stochastic mode (`--seeds`, default `k=16`, `fresh_seed_value_at_risk()`) exists and
was **not** used. Two supporting specifics: survival values are exact design fractions
(`CD_TWO_MSG_FRACTION["cd_v3"] = 1/3`, v4 `= 1/8`, `benchmark.py:162`) and the 0.41 crossover is a
closed-form root (`cd_hedge_matrix.py:118-137`).

**P1 — the outcome reframe.** Both documents were written before the private board resolved and cast
the pair as transferring intact, with Slot A as the value bet. Corrected everywhere: the value bet
died, the hedge was the whole result, and the rig **pre-registered the world that occurred**
(`SELECTION_MATRIX_FINDINGS.md`, `det_marker_data`: every exfil family 0, every CD family 1.00). The
coarse/fine asymmetry is now the note's spine — since all four CD variants survive that world, holding
*and manually selecting* a decorrelated asset was worth everything while the variant analysis was
worth nothing, and the winner (v1) is the build the matrix ranked last, chosen on operational grounds.
The **auto-select trap** is stated in both files.

**P2 — rank demoted.** README no longer opens with `Final rank: 174 / 4252`; it opens with the
methodological contribution and carries the rank beneath as corroboration.

**P2 — assumptions promoted.** New **§7 Assumptions** cell (A1–A6: mock-agent compliance, unverified
2-turn real-model compliance, distrusted GGUF/T4 wall-clock, the defender-space boundary, single-run
public scores, inert `config`). Old §7 "honest limits" content moved here; sections renumbered
**7→8, 8→9, 9→10** and all cross-references updated.

**P2 — seed engagement promoted** out of the sources list into a named §7 subsection, *"The variance
boundary."* Cites the Go-Explore 8× finding with the authors' own hedge, applies it to the
**generation pipeline** (evidenced by our own 91.265 / 85.255 / 60.510 spread), and explicitly states
where it does **not** apply — the deterministic replay score and the analytic crossover.

**P3 — claims→cells table** added to both files, and a named **"Responsible communication"**
subsection added to §6.

**Accuracy repairs found while editing (not in the brief).** Naming v1 as the selected build exposed
two now-wrong statements: the README's polarized table described Slot B as the *"two-message variant"*
(v1 is domain-only, single-message — the seam is v3/v4 only), and Lever 2 credited the two-message
seam with the decorrelation that actually paid. Both fixed: the CD channel is decorrelated because it
**carries no marker** (that is what paid); the seam additionally survives a *word-based share-gate*
(which did not occur). The README's "Submitted references" line also omitted `55918818` entirely —
the build that carried the result — and now leads with it.

## What did NOT change

- **No code cell was touched**; all 5 retain their embedded stdout, so nothing needs re-execution.
- **No numbers were invented.** Every figure written was verified against the working tree this
  session (`k=1`, `p=1.0`, the design fractions, `density_of_fraction`, the closed-form root, the
  `det_marker_data` row) — except the realized private scores, per THE OPEN ITEM.

## Notebook-editing mechanics (updated — reuse these)

- **`Edit` refuses `.ipynb`.** Under auto/Bash-first mode the reliable path is a **python JSON patch
  script**: `json.loads(io.open(p,encoding='utf-8',newline='').read())` → string-replace on cell
  sources with `assert old in s` guards → write back with
  `json.dumps(nb, indent=1, ensure_ascii=False)`, `newline=''`. **Verified byte-exact round-trip** on
  this notebook, so diffs stay minimal.
- **`cell['source']` is `str` for most cells but a `list` for some** (cell 15 was a list). Normalize
  with `s if isinstance(s,str) else ''.join(s)` before matching, or the `in` test silently checks list
  membership and fails.
- **Do not compose large patch scripts in a bash heredoc** — quoting breaks on this content. Write the
  script to the scratchpad and run it.
- **Anchor on exact line wrapping.** Several failed matches this session were the same sentence
  wrapped differently in the notebook than in the README.
- **Validate after editing:** re-parse, print `len(nb['cells'])` and the `## ` heading map to confirm
  section numbering is sequential.

## What worked
- **Applying a pre-verified brief.** The research session had already killed ~60% of its own candidate
  claims by adversarial vote; what survived was directly actionable and each item named its target
  file and section.
- **Verifying the source claims again before writing them.** Cheap, and it is what caught the two
  extra accuracy repairs above.

## What did NOT work / traps (don't repeat)
- **The builder is STALE.** `scratchpad/build_working_note.py` still emits the pre-poker text.
  **Re-running it reverts everything.** The `.ipynb` is the source of truth.
- **Kaggle MCP auth is broken** (`Unauthenticated`; `authorize` returns a malformed result that fails
  schema validation). Use the REST recipe in `HANDOFF-resubmit.md`.
- **`kaggle-writeup/repo`** (`C:\Users\adost\kaggle-writeup\repo`) is a **second clone** of this repo
  made by the research session for read-only inspection. It is CRLF-checked-out and not where work
  should happen. Edit **`C:\Users\adost\attack-competition`**.

## Next steps
1. **Verify the private scores** (THE OPEN ITEM) and, if they differ, correct §5/§8 and the README
   outcome section before submitting.
2. **Re-read the brief's §02** for the rubric detail and §04 for what must *not* be claimed about seed
   variance — both are already reflected, but the brief is the reference if wording is revisited.
3. **Optional, P3-weight only:** the brief flags its own angle-3/angle-4 material (write-up craft and
   artifact-evaluation conventions) as carrying lighter evidentiary weight than the rubric and seed
   angles.
4. **Preserve the research corpus if it is still wanted** — `claims.md` (59 KB), `votes.md` (322 KB)
   and the workflow journal live under the session scratchpad in `AppData\Local\Temp`, which is
   subject to cleanup.

## Pointers / where the detail lives
- **The note:** `WORKING_NOTE.ipynb` (19 cells). **The summary:** `README.md`. **Builder (STALE):**
  `scratchpad/build_working_note.py`.
- **The pre-registration that makes the forecast claim work:** `dev/benchmark/SELECTION_MATRIX_FINDINGS.md`
  (dated 2026-09-01, before the private board resolved). Do not edit it — its value is that it is a
  dated prior record.
- **Revision brief:** https://claude.ai/code/artifact/c2c3319b-00fd-4783-b177-2a26cff3a48c
- **Memories:** [[jed-realized-outcome-cd-v1-won]] (the outcome + its three consequences),
  [[jed-poker-framing-not-stackelberg]], [[jed-working-note-built]], [[jed-cd-hedge-stress-test]],
  [[jed-hedge-shared-death-cd-seam]], [[jed-only-exfil-fireable]], [[jed-family-ceiling]].
- **Underlying analysis artifacts:** `dev/benchmark/cd_hedge_matrix.py` → `_cd_hedge_matrix.{json,md}`;
  SDK source under `vendor/jed/aicomp_sdk/` for the `file:line` citations.
