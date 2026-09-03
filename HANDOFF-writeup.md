# Handoff — Working-Note writeup: NEXT = research corpus into `docs/` + competition background + real-world hook

**Date:** 2026-09-02 (updated) · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** *AI Agent Security — Multi-Step Tool Attacks* (comp 134815; slug `ai-agent-security-multi-step-tool-attacks`; hosts OpenAI/Google/IEEE; $50k).
**Working Note deadline: 2026-09-08 23:59 UTC.**

> Repo convention: this is the **writeup** topic handoff (`HANDOFF-<topic>.md`). Do **NOT** overwrite
> `HANDOFF.md` — that is the master handoff for the `attack.py` engineering track (dated 2026-08-30,
> Phase-2 v24 + validator + GGUF runner) and is a different topic. The `/handoff` skill's default
> filename was deliberately not used for that reason.

---

## Goal

Three changes to the public writeup, in priority order:

1. **Lead the README with real-world context** — a hook on **decision-making under uncertainty and
   agentic risk** — so a reader who has never heard of this competition understands why the problem
   matters before meeting the mechanics.
2. **Add brief background on the competition**, with a link to the competition overview page, near
   the opening. Right now the README assumes the reader already knows what comp 134815 is.
3. **Copy the deep-research corpus into `docs/`** so it survives — it currently lives only in a
   `AppData\Local\Temp` scratchpad subject to cleanup. **Read the hard constraint in §3 below before
   copying anything: the corpus is 61% refuted material and must not be published as-is.**

## Current progress

**Done and pushed — commit `056f336`** on `master` + `repro-gguf-repoint`
(`github.com/adostie2020/kaggle-ai-agent-security`). That commit applied §05 of the deep-research
**Working Note Revision Brief** (Artifact: https://claude.ai/code/artifact/c2c3319b-00fd-4783-b177-2a26cff3a48c),
which the research session had produced but never applied to the repo. In summary:

- **P1 accuracy fix.** The README had implied the payoff matrix came from *"sampling a distribution of
  defenders."* It does not — `cd_hedge_matrix.py:92` runs `base_seed=0, k=1` and the CD worlds are
  `det_*` profiles at `p=1.0` (`guardrails.py:272-279`). Both documents now say **exact enumeration
  over a specified defender space** (a census, not an estimate), note the design fractions (`1/3`,
  `1/8`) and the closed-form crossover, and state the stochastic mode exists but was not used.
- **P1 outcome reframe.** Density-v1 (`55916596`, public 91.265) was **zeroed**; CD v1 (`55918818`,
  public 16.695) carried **174 / 4252** alone — the world the rig pre-registered as `det_marker_data`.
  Framed as a validated forecast, with the coarse/fine asymmetry as the spine and the **auto-select
  trap** stated in both files.
- **P2/P3.** Rank demoted out of the README opening; new **§7 Assumptions** (A1–A6) with sections
  renumbered 7→8, 8→9, 9→10; the Go-Explore seed material promoted into a named variance-boundary
  subsection; claims-to-cells tables; a named responsible-communication subsection.

**Notebook is 19 cells.** All five code cells and their embedded outputs are untouched — nothing needs
re-execution.

## ⭐ STILL OPEN — verify the realized private scores

Unchanged from the last pass and **not** blocked by the new work, but it must be closed before the
note is submitted for judging. The whole reframe rests on one premise that has never been
machine-verified:

- `55916596` (density-v1, public 91.265) → **private ZERO**, killed by a `data`-payload
  `SECRET_MARKER` grep = the pre-registered `det_marker_data` world.
- `55918818` (CD v1, public 16.695) → **survived, carried 174 / 4252**.

Source is the user's own report, recorded in memory `jed-realized-outcome-cd-v1-won`. Kaggle MCP
returned `Unauthenticated` in both the research session and the session that applied the edits
(`mcp__kaggle__authorize` returns a payload that fails schema validation). **"Zeroed" vs merely "low"
is the load-bearing distinction** — it is a claim about *which defender world occurred*. Recovery path:
the REST recipe in `HANDOFF-resubmit.md` ("One-shot status check") plus the documented OAuth refresh.

---

## The task in detail

### 1. The hook — decision-making under uncertainty and agentic risk

Goes at the **top of `README.md`** (before the current "A red-team submission that treats the
competition as…" paragraph) and, in a compressed form, in **`WORKING_NOTE.ipynb` cell 0**, which
currently opens straight into "What this note argues."

The angle the user asked for, and it happens to be the honest one for what this repo now shows:

- **The agentic-risk frame.** Production agents are being handed real tool access — HTTP, email,
  filesystem. The security question stops being "can the model be jailbroken" and becomes "what
  happens when a tool-using agent is *induced to act*." That is what all four predicates in this
  benchmark model: exfiltration, confused deputy, untrusted-to-action, destructive write.
- **The uncertainty frame, which is the real subject.** You must commit a fixed defense — or here, a
  fixed attack — **before** you know which rules will apply, with no feedback until the outcome is
  realized. That is the ordinary condition of security engineering: controls ship before the adversary
  arrives. This competition is an unusually clean laboratory for it, because the hidden guardrail is
  *fixed in advance and never adapts*, so the problem is pure decision-making under uncertainty rather
  than a game against a reactive opponent.
- **The payoff, which the repo can now actually demonstrate.** The result here is not "we ranked
  174th." It is that a pre-registered forecast **resolved**: the rig named the defender world before
  it arrived, and the outcome inverted the intuition — the high-scoring build died, the insurance
  carried everything, and the elaborate optimization inside the hedge turned out to be worth nothing.
  **Structure beat optimization.** That is the transferable lesson and it is what the hook should be
  pointing at.

**Constraints — do not break these while adding the hook:**

- **Do not regress the two P1 corrections.** No "sampling a distribution of defenders"; no "the
  portfolio transferred" framing that implies the pair survived as a pair.
- **Rank stays demoted.** It is explicitly *not* a judging criterion (the Evaluation page states the
  awards "will not be determined solely by leaderboard rank"). Do not let the hook drift back into
  leading with 174 / 4252.
- **Stay benchmark-scoped.** Criterion 5 is responsible communication, and the note's whole posture
  depends on it. The hook may *motivate* with real deployment risk, but it must then narrow
  explicitly — everything here runs against an offline, fixture-backed sandbox, and none of it is
  guidance for attacking real systems. Motivate, then fence. The existing scope blockquote and the §6
  "Responsible communication" subsection are the model; keep them.
- **Do not overclaim transfer.** Do not assert that findings about this benchmark's mock guardrail
  generalize to production defenses. The defensible claim is about *method* — how to decide under an
  unobservable defender — not about specific attacks working anywhere else.

### 2. Competition background + link

Short — a paragraph or a small block, not a section that competes with the argument. Should cover:
what the benchmark is (an offline, replay-scored agent-security benchmark on the JED framework),
the two-leaderboard structure (public proxy, private decides), that the private guardrail is never
observed, and the Working Note award track.

**Link:** https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks

Existing material to reuse rather than re-derive: `docs/data-description.md` (the `/data` page and
trace schema), `docs/references.md` (the JED framework docs at `mbhatt1.github.io/competitionscratch`),
`dev/comp_pages.txt` (raw dump of the competition pages). The rubric detail is in §02 of the revision
brief and was pulled first-party through the authenticated Kaggle API — **note that public `WebFetch`
on Kaggle pages returns only the SPA shell**, so do not try to re-fetch and "confirm" it that way.

### 3. The research corpus → `docs/` — READ THIS BEFORE COPYING

**Source (volatile — in `Temp`, could be cleaned at any time):**
`C:\Users\adost\AppData\Local\Temp\claude\C--Users-adost-kaggle-writeup\c21db418-c5fd-46db-af70-6fb7f6ab0168\scratchpad\`

| File | Size | What it is |
|---|---:|---|
| `claims.md` | 59 KB | 110 claims extracted from 22 sources, grouped under `### SOURCE quality=… date=…`, each tagged `[central]` / `[supporting]` |
| `votes.md` | 322 KB | 75 adversarial verification votes, each headed `===== VOTE n refuted=True/False confidence=… counterSource=…` |
| `working-note-brief.html` | 32 KB | The synthesized brief — the thing that was actually actioned |

**The hard constraint.** Of the 75 votes, **46 are `refuted=True` and 29 are `refuted=False` — 61%
refuted.** `claims.md` is the *pre-verification* extraction: it contains the refuted material with no
marking whatsoever. Copying it into a public repo as-is would publish a majority-wrong document
alongside a note whose credibility rests on being careful about exactly this. The brief's own §06
names the failure pattern: nearly every refuted claim paired an accurate quotation with an inference
the source did not license.

So: **never ship `claims.md` alone.** Options, roughly in order of preference —

- **Ship both, with an index that explains the verdicts** — a `docs/research-corpus/README.md`
  carrying provenance (session `c21db418`, 2026-09-02, 5 angles, 103/104 agents, the final synthesis
  step failed and the brief was recovered from the journal), the 46/29 split, how to map a claim to
  its vote, and a plain warning that `claims.md` is unverified input, not findings.
- **Or ship a filtered corpus** — only claims whose votes confirmed them, with the verdict inline.
  Cleaner for a reader, more work, and it loses the negative results that the competition host
  explicitly said are worth publishing.
- **Or keep it out of the public repo** and preserve it elsewhere. Ask the user if unsure — this is a
  public repo and a judged artifact.

**Conventions to follow.** Existing `docs/*.md` files open with a `**Source:** <url>` line and a
`Recorded <date>` stamp (see `docs/data-description.md:1-4`) — match that. Note `votes.md` at 322 KB
is large but well within reason for git; it is prose, and it diffs fine.

**Also worth capturing:** the brief itself is currently only an Artifact URL. A markdown rendering in
`docs/` would make it durable and reviewable in-repo.

---

## What worked

- **Applying a pre-verified brief.** The research pass had already killed ~60% of its own candidate
  claims by adversarial vote, so what remained was directly actionable and each item named its target
  file and section. Cheap to apply, high hit rate.
- **Re-verifying every source claim before writing it.** This is what caught three accuracy repairs
  the brief had not spotted: the README's Slot B row described a "two-message variant" when the
  selected build (v1) is single-message; Lever 2 credited the seam with the decorrelation that
  actually paid (the CD channel is decorrelated because it **carries no marker** — that is what paid);
  and the submitted-references line omitted `55918818` entirely, the build that carried the result.
- **A byte-exact JSON round-trip check on the notebook before editing it** (`json.dumps(nb, indent=1,
  ensure_ascii=False)` reproduced the file exactly), which made programmatic edits safe and kept the
  diff to 30 lines.

## What did NOT work / traps — don't repeat these

- **`Edit` refuses `.ipynb`.** Under auto/Bash-first mode the reliable path is a **python JSON patch
  script**: `json.loads(io.open(p,encoding='utf-8',newline='').read())` → string-replace on cell
  sources guarded by `assert old in s` → write back with `json.dumps(nb, indent=1, ensure_ascii=False)`
  and `newline=''`.
- **`cell['source']` is a `str` for most cells but a `list` for some** (cell 15 was a list). Normalize
  with `s if isinstance(s,str) else ''.join(s)` before matching, or `in` silently tests list
  membership and the assert fires for the wrong reason.
- **Do not compose large patch scripts in a bash heredoc** — quoting broke twice on this content.
  Write the script to the scratchpad and run it.
- **Anchor on exact line wrapping.** Two failed matches were the same sentence wrapped differently in
  the notebook than in the README. Print the surrounding text first, match against that.
- **The builder is STALE.** `scratchpad/build_working_note.py` still emits the pre-poker text.
  **Re-running it reverts everything.** The `.ipynb` is the source of truth.
- **Kaggle MCP auth is broken** (`Unauthenticated`; `authorize` returns a malformed result). Use the
  REST recipe in `HANDOFF-resubmit.md`. **Public `WebFetch` on Kaggle pages returns only the SPA
  shell** — it cannot verify page content.
- **`C:\Users\adost\kaggle-writeup\repo` is a second clone** of this repo, made by the research session
  for read-only inspection. It is CRLF-checked-out. **Edit `C:\Users\adost\attack-competition`.**

## Next steps

1. **Decide the corpus disposition** (§3) — filtered, or both-with-an-index, or out of the public
   repo. This is a judgement call about a public, judged artifact; if there is any doubt, ask the user
   rather than defaulting to "copy it all in."
2. **Copy the corpus into `docs/`** with a provenance-and-verdicts index, matching the existing
   `docs/` header convention. Do it early — the source is in `Temp`.
3. **Write the hook** at the top of `README.md`, then mirror a compressed version into
   `WORKING_NOTE.ipynb` cell 0, honouring the four constraints in §1.
4. **Add the competition background + link** near the opening of both documents.
5. **Verify the private scores** (the ⭐ open item) and correct §5/§8 and the README outcome section
   if they differ.
6. **Re-check after editing:** re-parse the notebook, print the `## ` heading map to confirm section
   numbering is still sequential, confirm all five code cells still carry outputs, and grep for the
   regressed phrases — `sampling a distribution`, `portfolio transferred`, `Final rank: 174` in the
   README's opening position.
7. **Commit + push both branches** (`git push origin master repro-gguf-repoint` — they are kept in
   sync; both are currently at `056f336`).

## Pointers / where the detail lives

- **The note:** `WORKING_NOTE.ipynb` (19 cells). **The summary:** `README.md`. **Builder (STALE):**
  `scratchpad/build_working_note.py`.
- **The pre-registration that makes the forecast claim work:** `dev/benchmark/SELECTION_MATRIX_FINDINGS.md`
  (dated 2026-09-01, *before* the private board resolved). **Do not edit it** — its entire value is
  that it is a dated prior record.
- **Revision brief:** https://claude.ai/code/artifact/c2c3319b-00fd-4783-b177-2a26cff3a48c
- **Competition:** https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks
- **Memories:** [[jed-realized-outcome-cd-v1-won]] (the outcome, its three consequences, and a note
  that they are already applied in `056f336` — do not re-apply),
  [[jed-poker-framing-not-stackelberg]], [[jed-working-note-built]], [[jed-cd-hedge-stress-test]],
  [[jed-hedge-shared-death-cd-seam]], [[jed-only-exfil-fireable]], [[jed-family-ceiling]].
- **Underlying analysis artifacts:** `dev/benchmark/cd_hedge_matrix.py` → `_cd_hedge_matrix.{json,md}`;
  SDK source under `vendor/jed/aicomp_sdk/` for the `file:line` citations.
- **Source claims verified this session** (so they need not be re-derived): `cd_hedge_matrix.py:92`
  (`base_seed=0, k=1`), `guardrails.py:272-279` (`p=1.0` rules), `benchmark.py:162`
  (`CD_TWO_MSG_FRACTION`: v3 `1/3`, v4 `1/8`), `benchmark.py:170` (`density_of_fraction` → `0.750`,
  `0.889`), `cd_hedge_matrix.py:118-137` (closed-form crossover), `benchmark.py:389/447/538`
  (the unused `k=16` ensemble mode).
