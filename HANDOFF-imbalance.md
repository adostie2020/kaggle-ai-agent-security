# Handoff — imbalance leg: two real-infra A/Bs in flight (GGUF timing distrusted → measure via scored A/B deltas only)

**Date:** 2026-09-01 ~03:45Z · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** `ai-agent-security-multi-step-tool-attacks` (134815) · **DEADLINE:** 2026-09-01T23:59Z (~20h left).
**Thread convention:** `HANDOFF.md` = the PARALLEL `attack-competition-3e` private-resilience thread — **do NOT touch it.** This is the public/density/imbalance thread. `attack.py` is 3e's; **this thread ships only ISOLATED variant kernels** (never edits the live `attack.py`). Background analysis: `HANDOFF-density.md` (the "is density maxed?" cracks). New memory this session: [[jed-gguf-timing-distrusted]].

## Goal
Public score = `mean(row_gptoss, row_gemma)`; only the mean is visible (the 4-Id `submission.csv` is hidden). Find and pull the remaining lever above the banked **91.265** (density-v1) by locating the **model imbalance** (which row is the laggard) and whether that row is **budget-bound** (fewer candidates fit) or **fire-bound** (lower fire rate). NOTE: the prize ranks on the **hidden PRIVATE guardrail** (where our `SECRET_MARKER` exfil may collapse to ~0 — that's 3e's CD-hedge domain), so marginal *public* points here are lower-value than the leaderboard gap suggests.

## ★ The pivot this session (user steer — drives everything below)
User: *"I wouldn't necessarily trust the gguf, since there seems to be some other infra behind the scenes affecting timing for this."* The scored backend runs each model via a gRPC `RemoteAgent` on CPU ([[jed-deployed-gateway]]), so **per-candidate wall-clock in production is NOT predicted by llama.cpp/T4 generation latency.** Consequences:
- The old plan (push a GGUF fire-rate/latency probe → ÷~7 for CPU → estimate `N_fit` → decompose the row) is **DEAD** — it rests on the distrusted number. **Do not push GGUF timing probes for this.**
- The imbalance is **doubly blind**: hidden per-model split **+** untrustworthy local timing.
- **The only trustworthy throughput signal is a scored submission.** Read per-model economics via **held-constant A/B submissions**: vary ONE model, hold the other; **mean delta = ½·(that model's row change).**
- Memory conclusions built on GGUF timing (e.g. "gemma at token floor / capped": [[jed-probe-a-replay-cost]], [[jed-retention-probe]], [[jed-family-ceiling]]) are **unconfirmed on the real infra** — fair game to re-test.

## Current progress — TWO real-infra A/Bs in flight, both land before the deadline
| Build | Ref | Kernel | Varies | Holds fixed | Reads | Scores ~ |
|---|---|---|---|---|---|---|
| density-v2 | **55928426** | `jed-attack-density-v2` | gpt_oss: single-hop vs multipost | gemma | ½·Δrow_gptoss | ~11:10Z |
| **gemma-ab** (NEW) | **55930645** | `jed-attack-density-gemma-ab` | gemma: native-single forge vs plain | gpt_oss (=v1) | ½·Δrow_gemma | ~13:1xZ |

- **Banked/selected final = density-v1 91.265** (ref 55916596). Selection is MANUAL and by max score, so a losing A/B costs nothing (just don't re-select it).
- **Score history:** v22 86.10 → v23 85.29 → density-v1 **91.265**. Board: top **147.53**, top-25 cutoff **120.53**, us ~91 (rank ~387). GPU quota fine (~28h left). Daily submission cap 5; **2 used on 09-01** (v2 + gemma-ab), 3 left. The binding constraint is scoring latency (~10h) vs the deadline, NOT slots.

### The gemma-ab build (what I shipped this session)
Source: `<SESSION_SCRATCH>/gemma_attack.py` (a copy of density-v1/v2 source + 3 edits). `<SESSION_SCRATCH>` = `C:\Users\adost\AppData\Local\Temp\claude\C--Users-adost-attack-competition\8b6d4310-5dd7-44d6-9cde-b0a0828e2127\scratchpad`. Push script: `push_gemma_ab.py` (same dir). The 3 edits:
1. **`_forge_gemma_single_builder(k)`** = `lambda idx: _forge_gemma_native_msg(idx, 1)` — the gemma-native tool-call forge but **n=1**: pre-seeds gemma's exact native `<|tool_call>call:http.post{...}<tool_call|>` for it to COPY → minimal generation, parser-native, no trailing "OK" turn, one hop, distinct host `_url(idx)`/candidate. (v23 already proved the native format FIRES on the real scored rerun at 85.29 — it was just multipost-penalized; n=1 removes that penalty.)
2. Added `"forge_gemma_single"` to `_build_families` (non-reduce branch).
3. **`ATTACK_GEMMA_FORCE` override** in the blind-emit branch, gated on **`chosen_name != "forge_multi"`** — the EXACT complement of v2's `chosen_name == "forge_multi"`. So gpt_oss (winner=`forge_multi`) stays byte-identical to v1; only gemma's emit changes.
- Serve cell sets `ATTACK_BLIND_EMIT=1` **+** `ATTACK_GEMMA_FORCE=1` (NOT `ATTACK_FORCE_SINGLE` — that's v2's gpt_oss lever). Reason config can't be used: `self.config` is EMPTY in the rerun ([[jed-attack-config-inert-in-rerun]]); only module defaults + `os.getenv` work.
- **Pre-push validation PASSED**, incl. the A/B-integrity assert: `forge_multi` still contains `<|channel|>analysis` (gpt_oss path unchanged). Kernel committed clean (`status=complete`), submitted → ref 55930645.

## What worked
- **Real-infra held-constant A/B** as the ONLY trustworthy per-model probe (given the caveat). density-v2 = gpt_oss A/B (pre-existing); gemma-ab = the gemma analog (new).
- **REST `kernels/push`** of an isolated sha-gated 3-cell kernel (T4, internet OFF, competition datasource), env-var-driven behavior. Template proven: `push_gemma_ab.py` (has an inline OAuth `refresh_if_needed` + full pre-push validation + prints the push response `ref`/`url`).
- MCP tools for the whole loop without shell where possible: `get_competition_submission` / `search_competition_submissions` (scores), `get_notebook_session_status` (commit status), `create_code_competition_submission` (submit), `get_accelerator_quota`, `get_competition_leaderboard`.
- **Shell (Bash/PowerShell) WORKED this session** (no auto-mode exfil-block — cf. [[automode-blocks-shell-exfil-context]]).

## What did NOT work / dead ends (do not repeat)
- **GGUF timing probes to measure the imbalance** — killed by the user caveat (see pivot above).
- gemma within-trace / native-forge **MULTIPOST** as throughput: v23 = 85.29 (flat/worse) — multipost is hop-penalized for lean gemma. (gemma-ab tests the SINGLE-post native forge, which removes that penalty — different bet.)
- gpt_oss fast-single forge in the OLD probe-fill split: v18 = 68. (v2 re-tests single-vs-multi under BLIND-EMIT — different regime.)
- Config-based tuning — inert in the rerun ([[jed-attack-config-inert-in-rerun]]).
- Cheaper-egress / non-EXFIL predicate — source-closed ([[jed-family-ceiling]]).

## Next steps (in order)
1. **Read the two scores** (they were `pending` at 03:37Z). Via MCP `get_competition_submission({ref})` for 55928426 and 55930645, or REST `GET /api/v1/competitions/submissions/list/ai-agent-security-multi-step-tool-attacks?page=1` (Bearer = OAuth accessToken). Monitor script `<SESSION_SCRATCH>/monitor_both.py` polls both + self-refreshes the token (was KILLED after 2 cycles — re-launch with `.venv/Scripts/python.exe monitor_both.py` in background if desired).
2. **Apply the decision rule** (baseline 91.265):
   - `gemma-ab > 91.265` → gemma has a real throughput/format lever on the live infra ("gemma capped" was a GGUF artifact) → **re-select gemma-ab** as public final.
   - `density-v2 > 91.265` → gpt_oss single-hop wins → **re-select density-v2**.
   - Both clear → select the higher.
3. **OPEN DECISION — the combined-build hedge (time-sensitive, UNANSWERED).** The two A/Bs vary *different* models, so if BOTH levers are real the true optimum is a COMBINED build (gpt_oss→`forge_single` AND gemma→`forge_gemma_single`, i.e. set `ATTACK_BLIND_EMIT=1` + `ATTACK_FORCE_SINGLE=1` + `ATTACK_GEMMA_FORCE=1`). But we won't know both won until ~13Z, and a combined build submitted *then* scores ~23:40Z (razor-thin vs 23:59Z). So to capture the both-win case safely it must be **fired NOW, blind** (scores ~13:40Z with margin). It's a **free option** (slots/quota available; selection is by max score, so it only helps) but a **bet** (best only in the ~both-win world, ~20% prior; worse than the single winner if either lever is a dud). **I asked the user; no answer yet — do NOT fire without explicit go** (outward-facing action). If yes: copy `gemma_attack.py`, no source change needed (all three env vars already supported), new push script with all 3 env vars set + new slug/title, push+submit.
4. **Re-select** the winning build in the Kaggle UI before the deadline (manual; low public score won't auto-select). Keep 91.265 as the floor.

## Tooling / pointers
- `<SESSION_SCRATCH>` = `C:\Users\adost\AppData\Local\Temp\claude\C--Users-adost-attack-competition\8b6d4310-5dd7-44d6-9cde-b0a0828e2127\scratchpad`: `gemma_attack.py`, `push_gemma_ab.py`, `monitor_both.py`, `poll_commit.py`.
- density-v1/v2 source + push template: `…/bf5f9f91-…/scratchpad/density_attack.py`, `push_density_v2.py`, `monitor_v2_score.py`.
- **OAuth:** token in `C:\Users\adost\.claude\.credentials.json` → `["mcpOAuth"]["kaggle|43f49c16a482634f"]["accessToken"]` (3h TTL; refresh logic is embedded in `push_gemma_ab.py`/`monitor_both.py`; the bearer also authenticates REST).
- Kernel run status (REST): `GET /api/v1/kernels/status?userName=adostie3&kernelSlug=<slug>` (lowercase `running`/`complete`). Slug derives from TITLE ([[kaggle-push-slug-from-title]]); poll the push response `ref`/`url`.
- Memories: [[jed-gguf-timing-distrusted]] (this session's pivot), [[jed-v24-density-ab]], [[jed-family-ceiling]], [[jed-gemma-multipost-mechanics]], [[jed-attack-config-inert-in-rerun]], [[jed-deployed-gateway]], [[jed-retention-probe]], [[jed-probe-a-replay-cost]], [[jed-forum-throughput-intel]], [[jed-confused-deputy-validated]].
