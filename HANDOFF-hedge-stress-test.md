# Handoff — POST-submission hedge stress-test & final selection

**Date:** 2026-09-01 ~15:32Z · **Repo:** `C:\Users\adost\attack-competition` · **Interpreter:** `.venv/Scripts/python.exe`
**Competition:** `ai-agent-security-multi-step-tool-attacks` (134815, $50k, OpenAI) · **DEADLINE 2026-09-01T23:59:00Z.**

## The ask (why this handoff exists)
All 5 daily submission slots are spent — **no new submission can land before the deadline.** The job is
now: **stress-test the already-submitted CD hedges OFFLINE, so that when the public scores land this
evening we can select the best CD final with full information.** Public final is already settled; the
open decision is *which* of the four CONFUSED_DEPUTY (CD) submissions to select as the second final.

## Which handoff is this? (do not confuse / do not clobber)
- **THIS file** = the active entry point for post-deadline stress-test + final selection.
- `HANDOFF.md` = the older (2026-08-30) 3e private-resilience doc; **owns `attack.py`; do NOT overwrite.**
- `HANDOFF-private-guardrail.md` = the entropy-maximization design discussion that LED here (now resolved:
  the survey proved CD is the unique R1a-surviving predicate; the CD-entropy builds below were shipped).
- `HANDOFF-imbalance.md` = prior public/density state.

## Current submission state (polled 15:32Z)
| ref | build | status | public | role |
|---|---|---|---|---|
| **55916596** | density-v1 (EXFIL, blind-emit 2000) | complete | **91.265** | **PUBLIC FINAL — LOCKED** |
| 55928426 | density-v2 (force single-hop gpt_oss) | complete | 60.510 | lost (multipost load-bearing) |
| 55930645 | gemma-ab | complete | 85.255 | lost (< 91.265) |
| 55918818 | **CD v1** — domain(8) only, single-msg | complete | 16.695 | CD candidate (guaranteed selectable) |
| 55939702 | **CD v2** — domain + suffix-wording, single-msg | pending → ~23:12Z | — | CD candidate |
| 55940278 | **CD v3** — domain + wording + 2-msg @ K=3 (~33%) | pending → ~23:41Z | — | CD candidate (all 3 axes) |
| 55941340 | **CD v4** — domain + wording + 2-msg @ K=8 (~12%) | pending → ~00:47Z | — | CD candidate (all 3 axes; LIKELY MISSES deadline) |

Scoring is **parallel, ~11h/submission** (confirmed: density-v2 01:10→11:59Z ≈10.8h; gemma-ab 03:17→14:19Z ≈11.0h, overlapping ⇒ not serial). So v2/v3 should complete before 23:59Z (v3 thin, ~18 min), **v4 likely completes ~00:47Z — after the deadline, so likely NOT selectable.**

## The decision to make
Select **2 finals** (manual — no API; the low-public CD will NOT auto-select):
1. **Public → `55916596`** (density-v1, 91.265). Locked.
2. **CD/private → the best-*robust* build among those that COMPLETED** by selection time. That ranking is
   what the stress-test produces.

## RESULTS — offline stress-test DONE (2026-09-01)
Built the mixed-family validator + density-folded ranking (methodology steps 1–4). Artifacts:
`dev/benchmark/cd_hedge_matrix.py` (driver) → `dev/benchmark/_cd_hedge_matrix.{json,md}` (the lookup).
New validator families `cd_v3` (K=3) / `cd_v4` (K=8) mirror `cd_attack._candidate_msgs` exactly;
`benchmark.CD_TWO_MSG_FRACTION` + `density_of_fraction(f)=1/(1+f)` fold the ~2× two-message replay cost.
Two-message seam **re-verified end-to-end** through the real oracle (`det_cd_sharegate`: single dies,
two-msg fires; `optimal`: both fire; `det_cd_block`: both die). All CD builds survive both marker-grep
worlds (`det_marker_data`/`det_marker_prompt`) at 1.0 — the world v2 owns.

**Score matrix** (`density × survival`, normalized permissive/v2 = 1.000):

| world (exfil already dead) | v1 55918818 | v2 55939702 | v3 55940278 | v4 55941340 |
|---|---|---|---|---|
| cd_unconstrained (marker grep) | 1.000 | **1.000** | 0.750 | 0.889 |
| cd_domain (recipient whitelist) | 0.250 | **0.250** | 0.188 | 0.222 |
| cd_wording (phrase grep) | 0.000 | **0.833** | 0.625 | 0.741 |
| cd_sharegate (side-effect share-gate) | 0.000 | 0.000 | **0.250** | 0.111 |
| cd_block (channel blocked) | 0.000 | 0.000 | 0.000 | 0.000 |

**Verdict:**
- **v1 is weakly dominated by v2** (same density; v2 ≥ v1 everywhere, strictly better under wording) ⇒
  v1 is a completion-fallback only, never a first choice.
- **v2 (`cd_full_div`, 55939702) = the expected-value pick.** Wins under `marker_dominant`, `reasoned`,
  and `uniform` priors; owns every exfil-dead world except the side-effect share-gate; full density;
  **does not depend on the unverified 2-turn compliance.**
- **v3 (55940278) = maximin-robust** (only build with no zero off the unhedgeable floor). Wins only under
  a share-gate-dominant prior — crossover **P(share-gate) ≥ 0.41**.
- **v4 (55941340) = the balanced hedge** (2nd in almost every ranking; ~89% density + partial share-gate
  coverage) — but was submitted late and **likely completes ~00:47Z, after the deadline ⇒ probably NOT
  selectable**.

**Provisional pick (calibrate on public scores): `55916596` (public) + `55939702` (v2, CD).** Switch the
CD slot to **v4** only if v4 has COMPLETED *and* the public CD scores show the 2-turn cohort fired
(`v4_public ≈ v2_public × density`); switch to **v3** only if you specifically weight a *word-based*
side-effect share-gate as the dominant private (a narrow bet — a recipient-allowlist or unconditional
share-block kills v3 too). If v4 is unselectable and share-gate belief is low, the pick is **v2**; **v3**
only under a strong share-gate prior. The public-score compliance read (step 5) is the tiebreaker.

## STRESS-TEST METHODOLOGY (the answer to "what can we do")
The private score of a CD build ≈ **DENSITY** (candidates the deadline-aware fill returns within budget)
× **SURVIVAL** (fraction that fire under the *unknown* private guardrail). We can't see the private
guardrail, but we can score each SUBMITTED build's SURVIVAL across the full space of hypothesized private
worlds (the `dev/benchmark/` validator, already extended with the CD channel this session) and fold in an
analytic DENSITY model. Steps:

1. **Mirror each submitted build as a validator family** (with the correct single/two-message MIX):
   - CD v1 ≈ existing `cd_domain_div` (domain-diversified, one fixed wording, single-msg).
   - CD v2 ≈ existing `cd_full_div` (domain + suffix-wording, single-msg).
   - CD v3 / v4 = **NEW mixed families** — the validator currently has *pure* `cd_full_div` and *pure*
     `cd_twomsg` but not the realistic interleave. Add a parameterized builder mirroring
     `cd_attack._candidate_msgs`: single-message `cd_full_div` except every `K`-th candidate is the
     two-message `cd_twomsg` chain. Register `cd_v3` (K=3) and `cd_v4` (K=8). The validator's
     equal-candidate scoring then reports each mix's blended survival automatically (e.g. under
     `det_cd_sharegate`, cd_v3 ≈ 0.33 = the 2-msg third survives).

2. **Run the full private-world profile matrix** on all four build-families → a survival matrix
   (build × world). Worlds (profiles in `guardrails.py`): `baseline` (sanity, all fire), `det_cd_block`
   (floor, all 0), `det_cd_domain` (domain whitelist), `det_cd_wording` (phrase grep), `det_cd_sharegate`
   (unauthorized-share denier — the most natural CD defense), `cd_strict` (domain+wording). Optionally add
   a **stochastic mixed CD profile** (several CD rules at p<1, rerolled) for a realistic blended guardrail
   rather than the deterministic existential tests.

3. **Fold in DENSITY** (the validator uses fixed n_per_family, so it does NOT capture that v3/v4 return
   fewer candidates under a real budget). A two-message candidate ≈ 2× replay cost, so for 2-msg fraction
   `f`: `density(f) ≈ 1/(1+f)` (v2 f=0 → 1.00; v4 f=0.125 → 0.89; v3 f=0.33 → 0.75). Absolute score model:
   `score(build, world) ∝ density(f_build) × survival_validator(build, world)`. (Share-gate is already
   captured inside the mixed family's survival, so apply density as the overall candidate-count scale.)

4. **Rank builds** by a decision criterion over a prior on worlds:
   - **Minimax (worst-case):** highest MINIMUM score across worlds = most robust to an adversarial private
     guardrail.
   - **Expected:** assign `P(world)` and maximize `Σ P(world)·score`. Suggested prior reasoning: a plain
     R1a marker-grep is the most-cited exfil kill but **all CD builds survive it fully** (no marker), so it
     doesn't discriminate the CD builds — density wins there (favors v2). **Share-gate** is the most
     natural *CD-specific* defense and zeros every single-message CD — only the 2-msg cohort scores
     (favors v3 > v4 > v2). Domain-whitelist: all domain-diversified builds tie. Wording-grep: suffix
     builds (v2/v3/v4) beat v1. Block-all: unhedgeable (all 0).
   - The v3-vs-v4-vs-v2 choice reduces to **P(share-gate)**: high → v3 (most 2-msg coverage that will
     complete in time); low → v2 (max density). v4's theoretical sweet spot is moot if it misses the
     deadline.

5. **When the public scores land — CALIBRATE and finalize:**
   - The public score of each CD build reveals its **realized density** (public CD ∝ density × [public
     guardrail passes CD, which it does]). Compare v2 vs v3 vs v4 public: if v3/v4 are much lower than v2
     *beyond* the `1/(1+f)` density prediction, the **two-message cohort is NOT firing on the real model**
     (wasted probes) → prefer v2. If they track the density prediction, the 2-msg cohort fires fine → the
     share-gate hedge is real → prefer v3. **This public-score comparison is the ONLY real-model signal we
     get on the (currently UNVERIFIED) 2-turn AUTHZ+ACK compliance** — it directly resolves the biggest open
     uncertainty.
   - Confirm which builds COMPLETED (selectable) vs errored/still-pending.
   - Select public `55916596` + the CD build maximizing the chosen criterion **among those completed**.

## What worked (this session)
- **Source survey settled the strategy:** exactly 4 scorer predicates; CD (`email.send`) is the UNIQUE
  R1a-surviving single-call predicate ⇒ predicate-entropy is a fixed 2-set {EXFIL, CD}; only INTRA-CD
  entropy is buildable. (`vendor/jed/aicomp_sdk/core/predicates.py`, `guardrails/optimal.py`, `env/sandbox.py`.)
- **The validator (`dev/benchmark/`) as the offline stress-test rig** — extended this session with the CD
  channel: `MockDeputyAgent` (agents.py), families `cd_mono/cd_domain_div/cd_full_div/cd_twomsg`, rules
  `cd_email_block/cd_domain_whitelist/cd_wording/cd_share_gate` + profiles, a `--families` selector, and
  `_as_chain` (multi-message chains). All tests green; README § "CONFUSED_DEPUTY entropy families".
- **Three intra-CD entropy axes proven (relative survival, "robust to our hypotheses"):** domain 0→0.25 vs
  a whitelist; suffix-wording 0→0.75 vs a phrase grep; **two-message share-gate 0→1.0 vs the natural CD
  defense** (single-msg CD dies, 2-msg survives — send fires on the AUTHZ turn, scored via the neutral ACK).
- **Held-constant scored A/Bs** as the only trustworthy per-model probe (GGUF/T4 timing distrusted).

## What did NOT work / traps
- **Submitting CD v4 too late (13:47Z).** With parallel ~11h latency + 23:59Z deadline, last-safe submit
  was ~12:50Z. v4 likely completes ~00:47Z ⇒ probably unselectable. (My earlier "push-by ~21:40Z" was
  wrong — it used too-short a latency.) Consequence is small: v3 carries the same 3 hedge axes and completes
  in time.
- **Background monitors do not survive here** — killed 3× by session interrupts. Poll on-demand instead
  (`<SCRATCH>/endgame_monitor.py` one-shot, or the inline poller below). Do NOT keep re-launching them.
- Marker-EXFIL is structurally 0 under a private R1a grep; predicate-entropy has no 3rd channel;
  config is INERT in the rerun (`[[jed-attack-config-inert-in-rerun]]`).
- **A parallel session is/was active on this repo** — it hand-edited `cd_attack.py` (added the two-message
  cohort) and pushed/submitted CD v3 `55940278` (K=3) between our pushes. Coordinate; don't assume the
  working tree is only ours.

## Next steps (concrete)
1. **Build the stress-test matrix now** (offline, no deadline pressure): add the mixed `cd_v3`/`cd_v4`
   families to `dev/benchmark/benchmark.py`, run the profile matrix (§ methodology step 2), apply the
   density model (step 3), and produce the ranked survival×density table + minimax/expected verdict.
   Write it to `dev/benchmark/` output so the selection is a lookup, not a scramble at 23:50Z.
2. **Poll the CD scores as they land** (~23:12Z v2, ~23:41Z v3, ~00:47Z v4). Calibrate density / detect
   2-msg compliance (step 5).
3. **Select the 2 finals before 23:59Z** (manual, Kaggle UI): `55916596` + best-completed CD per the
   ranking. If only v1/v2 have completed, the realistic pick is v3-if-done else v2 else v1.
4. **Verify the SELECTION deadline** — assumed = submission deadline 23:59Z. If selection needs a COMPLETED
   submission and v3 hasn't finished, fall back to v2; v1 is the guaranteed-complete last resort.

## Tooling / operational pointers
- **Validator:** `.venv/Scripts/python.exe dev/benchmark/benchmark.py --mode portfolio --families <names> --profile <p> --candidates 8 --seeds 1 --max-tool-hops 4`; SDK restore `python dev/bootstrap_sdk.py`; docs `dev/benchmark/README.md`. Tests (one at a time): `dev/benchmark/test_guardrails.py`, `test_benchmark.py`.
- **One-shot poll (inline):** list `https://www.kaggle.com/api/v1/competitions/submissions/list/ai-agent-security-multi-step-tool-attacks?page=1` with `Authorization: Bearer <tok>`; token at `~/.claude/.credentials.json → ["mcpOAuth"]["kaggle|43f49c16a482634f"]["accessToken"]`, 3h TTL, refresh recipe in `<SCRATCH>/endgame_monitor.py` / `[[kaggle-mcp-oauth-broken]]`. Never print/commit the token.
- **`<SCRATCH>`** (this session) = `C:\Users\adost\AppData\Local\Temp\claude\C--Users-adost-attack-competition\1a7d1d33-0f96-41e2-818e-e5009f9c11ca\scratchpad`: `endgame_monitor.py` (poll loop), `wait_v4_commit.py`.
- **Submitted refs:** public 55916596; CD v1 55918818 / v2 55939702 / v3 55940278 / v4 55941340. Kernel `adostie3/jed-attack-cd-v1` (v4 = latest version). `cd_attack.py` on disk = the v4 (K=8) source.
- **Memories:** `[[jed-confused-deputy-validated]]` (predicate survey + all 3 CD-entropy axes + ship refs), `[[jed-v24-density-ab]]` (public decision), `[[jed-gguf-timing-distrusted]]`, `[[jed-only-exfil-fireable]]`, `[[jed-attack-config-inert-in-rerun]]`, `[[kaggle-mcp-oauth-broken]]`.
- **Uncommitted working-tree changes** (leave for the user to commit): `dev/agents.py`, `dev/benchmark/{guardrails,benchmark,test_guardrails,test_benchmark}.py`, `dev/benchmark/README.md`, `cd_attack.py`.
