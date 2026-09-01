# Handoff — density leg: interrogating "is the density method fully optimized?" (it is NOT)

**Date:** 2026-09-01 ~01:30Z · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** `ai-agent-security-multi-step-tool-attacks` (134815) · **DEADLINE:** 2026-09-01T23:59Z (~22.5h left).
**Thread convention:** `HANDOFF.md` = the PARALLEL session `attack-competition-3e`'s private-resilience thread — **do NOT touch it**. `HANDOFF-gemma-diag.md` = the prior public-throughput chapter. THIS file continues the **public/density** thread. `attack.py` is 3e's; this thread only ships ISOLATED variant kernels (never edits the live `attack.py`).

## Goal
Push the PUBLIC score past the banked **91.265** (density-v1) via the density method — and, per the user's ask, **stop and interrogate the claim that density is already maxed** before designing the next leg. The honest verdict below is: **density is NOT fully optimized. It maxes CANDIDATE COUNT for our current per-model fire behavior, but it does not touch two bigger levers (gemma fire-RATE and gpt_oss forge correctness), and the per-model split it rests on was never measured this session.**

## Current progress / hard facts
- **Score history:** v22 `86.10` → v23 `85.29` → **density-v1 `91.265`** (ref 55916596, kernel `jed-attack-density-v1`) — CONFIRMED +5.16 (+6%) over v22. Density lever real, not noise.
- **density-v2 A/B PENDING:** ref **55928426**, kernel `jed-attack-density-v2` v1. Forces single-hop harmony forge for gpt_oss vs density-v1's multipost. Scores in ~10h (~11:00Z). **Decision rule:** `v2 > 91.265` → single-hop wins, re-select v2; `v2 ≤ 91.265` → multipost confirmed, keep v1. (Background monitor `scratchpad/monitor_v2_score.py` was running then got killed — re-run it or check `get_competition_submission(55928426)` / the REST list endpoint below.)
- **CD Slot B** (ref 55918818, kernel `jed-attack-cd-v1`): private-guardrail hedge, still in scored rerun; **must be MANUALLY selected** (low public won't auto-select). 3e's domain.
- **Selection:** user has locked in the 91.265 as a final. If v2 wins, re-select v2.
- **Board context:** top 147.53, top-25 = 120+, we're rank 387. `max_daily_submissions=5` (submissions are NOT the constraint; ~10h scoring latency is). Prize ranks on the HIDDEN private guardrail, not this public board.

## The density mechanic (decoded from the deployed v1 kernel — this is what "density" IS)
1. **Classify:** ~35 warm probes (5 × 7 families) on the LIVE model → measure raw-per-second per family.
2. **Pick** the single max-raw/s family (`chosen_builder`).
3. `ATTACK_BLIND_EMIT=1` → `return [chosen_builder(i) for i in range(2000)]` — blind-emit the full 2000 cap of the winner, **no per-candidate probe**. (The v22 fill probed every candidate → paid generation+relay per kept candidate → UNDER-RETURNED. Density kills that. That's the +5%.)

## ★ THE CLAIM UNDER INTERROGATION: "density is near-optimal"
**The steelman (why it LOOKS maxed):**
- Emit is pinned at 2000 = the gateway's `MAX_REPLAY_FINDINGS` cap (hard fact).
- We replay only ~1000 of them (91.265 ≈ 0.09·N ⇒ N≈1014, well below 2000) ⇒ **replay-budget-bound**, not emit-bound.
- The classifier already self-selects the max-raw/s family PER MODEL.
- raw/s(n) = `(16n+2)/(h+n·g)` for n posts (g = one generation's cost, h = fixed per-candidate overhead). Its derivative sign is `8h−g`, **constant in n** ⇒ raw/s is monotonic ⇒ the per-candidate optimum is n=1 (single) OR n=max (multipost), never between. density-v2 settles which. So "post-count is optimized" is provable.
- Public synthesis ([[jed-family-ceiling]]): antoniorotundo's meta-writeup documents pure single-post EXFIL's ceiling as **85–91 normalized**; 91.265 is the TOP of that band. "We are AT it."

**Why the claim is FALSE at the competition level (the cracks — these are the drill-down targets):**

**CRACK A — the per-model split was never MEASURED (biggest lever, do this first).** The mean = (row_gptoss + row_gemma)/2, and only the mean is visible (the 4-Id submission.csv is hidden). Memory ESTIMATE ([[jed-family-ceiling]]): **gpt_oss ≈ 106–116 (multipost forge), gemma ≈ 59–66 (plain, "budget-bound")**. If true, **gemma is the laggard dragging the mean** — the forum's rank-11 explicitly names "model imbalance / optimize the slower model." Density optimizes BOTH rows' candidate-count symmetrically; it does NOT preferentially attack the laggard. **Verify the split with the repro harness (`dev/repro/run_repro.py`, real GGUF per-model observability) or a `run_local_gateway()` probe that logs per-model candidate count + raw.** Everything downstream depends on this number.

**CRACK B — gemma may be PARSE-bound, not budget-bound (this breaks the whole "maxed" premise for gemma).** [[jed-family-ceiling]] + [[jed-gemma-multipost-mechanics]]: `KaggleGemma4ToolCallParser` is KNOWN to drop gemma tool-calls on the real rerun (llama.cpp #22786/#21316, "Gemma 4 tool call returned as content"). If gemma's row is low because a FRACTION of its 1000 candidates fail to PARSE (fire rate <100%), then gemma is losing raw to parse failures, NOT to the replay budget — and "gemma at token floor / candidate-count maxed" is the WRONG diagnosis. Fixing gemma's fire RATE (a parser-surviving format) is a different, possibly larger lever than throughput. v23 native-forge was flat (85.29), so the native format ALONE didn't fix it — but the fire-rate hypothesis is UNMEASURED. **Measure gemma's actual fire rate per candidate on the real GGUF (repro harness), decompose low-row into {fewer candidates} vs {lower fire rate}.**

**CRACK C — classify measures the GENERATION path, not the REPLAY path.** The family choice (and the single-vs-multi decision) is made on generation-time raw/s, which includes a gRPC relay hop that may not exist in replay. This systematically inflates `h` during classify → over-values multipost (which amortizes h). density-v2 tests this for single-vs-multi, but the SAME bias could mis-route gemma's family and the wording choices. The gen-vs-replay per-candidate cost probe (the HANDOFF-gemma-diag "open problem") was **never built**. **Build it; if replay cost ≠ generation cost, the classifier is miscalibrated and correctable (per-family `REPLAY_COST_COEF`, or classify on a replay-cost proxy).**

**CRACK D — gpt_oss forge may not fire the OPTIMAL Harmony variant remotely.** [[jed-family-ceiling]]: the Harmony reasoning-suppression / "empty-analysis-turn" suffix is worth ~+27.5 pts of the 85–91 IF it fires, but has a documented reliability caveat, and our v18 forge REGRESSED (may not fire on the remote path). We never verified our `_forge_plan_msg` matches the correct empty-analysis-turn variant on the real rerun. **Verify gpt_oss forge fire rate + posts-per-trace on the real GGUF.**

**CRACK E — "format/token layer exhausted" is a memory CLAIM, established under the OLD probe-fill regime, not re-verified under blind-emit.** A lower-`g` primitive (fewer generated tokens per fire → cheaper replay → more candidates) is a DIRECT raw/s multiplier and was not searched in the density regime. A family that "regressed" under probe-fill (e.g. forge_gemma/v23) may behave differently under blind-emit.

**CRACK F — the arithmetic (91≈0.09N, ~1000 replayed, budget-bound) is all INFERRED, never measured on the production CPU (AMD EPYC, ~7× slower than our T4 probes).** If replay is count/cap-bound rather than budget-bound, the "only lever is raw/s" conclusion shifts.

**Bottom line for the user:** density is optimal for *candidate count given our current per-model fire behavior and family menu*. It is NOT competition-optimal: the 120–147 tier runs the SAME EXFIL/http.post primitive, so a throughput/fire-rate lever exists that we haven't cracked — most likely **gemma's fire rate (Crack B)** and/or **the correct gpt_oss Harmony forge (Crack D)**, both of which density leaves untouched.

## What worked
- Density blind-emit (2000 of classify-winner, no per-candidate probe): 86.10 → 91.265. The under-return diagnosis was correct.
- REST `kernels/push` of an isolated submission kernel (base64+sha-gated attack.py, 3-cell notebook, T4, internet OFF, competition datasource) — `scratchpad/push_density_v2.py` is the working template.
- Pulling our own deployed kernel source to see EXACTLY what shipped (`scratchpad/pull_kernels.py adostie3/<slug>`).

## What did NOT work / dead ends (do not repeat)
- Pure single-post PLAIN blind-2000 (v19 = 59.54) — plain replay ceiling; single-post only helps if it's the FORGE (harmony, low-token), which is what v2 tests.
- gpt_oss fast-single forge in the OLD split (v18 = 68 < v22).
- gemma within-trace multipost / native-forge as a THROUGHPUT play (v23 = 85.29 flat).
- Chasing a cheaper-egress or non-EXFIL predicate — DEFINITIVELY closed from source ([[jed-family-ceiling]]: EXFIL=http.post-only, url load-bearing, all other predicates guardrail-blocked).
- Config-based tuning — `self.config` is EMPTY in the rerun ([[jed-attack-config-inert-in-rerun]]); only MODULE DEFAULTS or serve-cell env vars (`os.getenv`) activate anything.

## Next steps (in priority order)
1. **When v2 scores (~11:00Z):** apply the decision rule; if `>91.265`, re-select density-v2 as the public final.
2. **Measure the real per-model split + gemma fire rate** (Cracks A+B) via `dev/repro/` (real GGUF) or a `run_local_gateway()` probe logging per-model {candidates replayed, posts fired, raw}. This decides the whole next leg: is gemma budget-bound (→ throughput) or parse-bound (→ fire-rate)?
3. **If gemma is parse-bound:** find a gemma format that survives `KaggleGemma4ToolCallParser` at ~100% fire (test on real GGUF, not just in-process). This is the highest-upside untapped lever.
4. **Verify gpt_oss forge** fires the correct Harmony empty-analysis-turn variant on the real rerun (Crack D); if not, fix it (~+27.5 pt claim).
5. **Build the gen-vs-replay cost probe** (Crack C); if the classifier is mis-routing, add a replay-cost correction.
6. Only after 2–5: decide whether any of it is worth a submission slot before the deadline (each burns ~10h scoring; ~22.5h left).

## Tooling / pointers
- **OAuth refresh** (token expires every 3h; also authenticates REST): `…/99ca17a3-…/scratchpad/kaggle_refresh.py`. Run before any Kaggle call.
- **density source + push:** THIS session `…/bf5f9f91-…/scratchpad/`: `density_attack.py` (v1 source + the 3 v2 edits: `_forge_single_builder`, `forge_single` in `_build_families`, the `ATTACK_FORCE_SINGLE` switch in the blind-emit branch), `push_density_v2.py`, `monitor_v2_score.py`.
- **deployed v1 source** (decoded): `…/df3a9e05-…/scratchpad/adostie3__jed-attack-density-v1.txt` + `pull_kernels.py`.
- **Submit a kernel:** MCP `create_code_competition_submission` (kernelOwner=adostie3, kernelSlug, kernelVersion, fileName=`submission.csv`).
- **Check a submission score (REST, standalone):** `GET /api/v1/competitions/submissions/list/ai-agent-security-multi-step-tool-attacks?page=1` (Bearer = the OAuth accessToken); fields per row: `ref`, `status` (`pending`/`complete`), `hasPublicScore`, `publicScore`.
- **Kernel run status (REST):** `GET /api/v1/kernels/status?userName=adostie3&kernelSlug=<slug>` → lowercase `running`/`complete`.
- **repro harness:** `dev/repro/` (README §"TWO BACKEND LAYERS" — HF vs GGUF fidelity gap; the scored path is GGUF/llama.cpp).
- Memories: [[jed-v24-density-ab]], [[jed-family-ceiling]], [[jed-gemma-multipost-mechanics]], [[jed-probe-a-replay-cost]], [[jed-forum-throughput-intel]], [[jed-attack-config-inert-in-rerun]], [[jed-confused-deputy-validated]].
