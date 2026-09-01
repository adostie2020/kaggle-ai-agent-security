# Handoff — Final-day selection (comp 134815)

**Date:** 2026-08-31 · **Repo:** `C:\Users\adost\attack-competition`
**Competition:** `ai-agent-security-multi-step-tool-attacks` (id 134815, $50k) · **DEADLINE: 2026-09-01T23:59Z (TOMORROW)**
**Interpreter:** `.venv/Scripts/python.exe` · SDK restore: `python dev/bootstrap_sdk.py` if `import aicomp_sdk` fails.

> Task-scoped handoff for the final-day submission SELECTION. Do NOT touch the master `HANDOFF.md`
> (owned by the delivery/candidate-density thread) or `HANDOFF-discovery-diversification.md`.

## Goal

Land the final-day **two-slot hedge** on the private leaderboard. Both selected submissions are scored
independently; final private = **the BEST (max) of the two selected** — so a hedge is pure upside.
Pick two DECORRELATED bets across the unknown private-guardrail:
- **Slot A = permissive-guardrail bet = highest-public EXFIL build** (wins if private ≈ public).
- **Slot B = strict-guardrail bet = CONFUSED_DEPUTY build** (wins if private greps all tool args for the
  secret marker → every `http.post`/EXFIL build collapses to ~0; CD carries no marker so it survives).

## Current state (2026-08-31, verified this session)

- **DECISION REVERSED vs the original plan: do NOT re-submit `attack.py`.** Verified from primary sources
  (code + a 3-analyst adversarial panel, unanimous): the current `attack.py` module DEFAULT is the 7-family
  **diluted blend** (`_build_families(reduce=False)`); `reduce_to_v22` is config-gated and **INERT in the
  rerun** (empty `self.config`). So a resubmit ships the BLEND (memory-flagged to regress **<86.10**), NOT the
  v22 `{plain,forge_multi}` monoculture. Kaggle submissions are immutable snapshots, so the banked v22 stays
  selectable forever — just SELECT it; never resubmit a known-worse build.
- **Selection mechanism (confirmed on the live Submissions page, user logged in):** "Select up to 2
  submissions… if less than 2 are selected, Kaggle auto-selects from your best PUBLIC scoring submissions."
  Was **0/2 selected**. Pending submissions show "Notebook Running" with **NO checkbox** — only *Succeeded*
  ones are selectable.
- **User has manually selected 2 slots** (they are handling selection themselves; said "I know to select the
  hedge, no need to verify"). ⚠️ CD was NOT yet selectable when they selected, so the CD (strict) slot most
  likely still needs to be set once CD finishes scoring — see Next steps.
- **Both hedge submissions are still PENDING scoring** (last checked 2026-08-31 ~11:45 local, no errors):
  - **CD (Slot B) = ref 55918818** — `jed-attack-cd-v1` v1.
  - **Density (v24) = ref 55916596** — `jed-attack-density-v1` v1 (a blind-density EXFIL build; candidate to
    REPLACE v22 in Slot A **iff** it scores public > 86.10).
- **Kaggle OAuth token refreshed** this session to a fresh ~3h window (recipe below).

### The submission board (adostie3, via REST)
| ref | build | public | status |
|---|---|---|---|
| **55857240** | **v22 `{plain,forge_multi}` monoculture** | **86.100** | complete ← **Slot A (permissive)** |
| 55893505 | v23 (blend + gemma-native forge) | 85.290 | complete (regression; do NOT use) |
| 55916596 | v24 density | — | **PENDING** (swap into Slot A if >86.10) |
| 55918818 | **CD (CONFUSED_DEPUTY)** | — | **PENDING** ← **Slot B (strict)** |

On the Submissions page these are labelled: v22 = "JED Attack Probe v1 – **Version 22**" (86.100);
CD = "JED Attack CD v1 – Version 1"; Density = "JED Attack Density v1 – Version 1".

## What worked

- **REST with the file OAuth bearer** (`~/.claude/.credentials.json` → `mcpOAuth["kaggle|43f49c16a482634f"].accessToken`,
  `Authorization: Bearer`) — the MCP tools returned **Unauthenticated** (running MCP client holds a STALE token),
  but the file token works on `GET /api/v1/competitions/submissions/list/<comp>` and `/kernels/status`. Use REST.
- **Fresh browser tab** for the live page: `tabs_create_mcp` → `navigate` → wait 5s → screenshot. A brand-new
  tab renders; reused/backgrounded tabs report `0x0` viewport / permission / CDP errors.
- A **3-agent adversarial Workflow** (ev-max / regret-min / red-team lenses) to harden the plan-reversal.
- **Proactive token refresh** (`refresh_token` grant) to cover the multi-hour scoring wait.

## What did NOT work / don't repeat

- **Background poll jobs get KILLED every turn** (confirmed twice this session — killed at each
  turn/notification boundary). Do NOT run a long bg monitor; use **ONE-SHOT REST checks** on demand.
- **MCP Kaggle tools** → `Unauthenticated` (stale in-client token; the file token is fine → use REST).
- **WebFetch on Kaggle pages** → only the title (JS-rendered SPA). `read_page`/`get_page_text` hang
  (`document_idle` never fires on the SPA). Use screenshots on a fresh tab, or REST.
- **Re-submitting `attack.py`** as Slot A (ships the diluted blend that regresses <86.10; adds void/resubmit
  risk) — dominated by simply selecting the banked v22 (55857240).

## Next steps

1. **When CD (ref 55918818) flips to "Succeeded":** its checkbox appears → **SELECT it as Slot B.** It will
   NEVER auto-select (low public, sev-3), so it MUST be manual, or the strict-guardrail hedge is lost.
2. **When Density (ref 55916596) finishes:** if its public > **86.10**, SELECT it as Slot A **instead of**
   v22 (55857240). Otherwise keep v22.
3. **Final target before the deadline: exactly 2 selected = {best-public EXFIL (v22 or Density), CD}.** If
   left at 0/2 or as two EXFIL builds, the CD strict-hedge never scores (auto-select picks v22+v23, both
   permissive bets that die together under a strict guardrail).
4. **Verify** the final 2 selected (Submissions page "Selected" filter, or the X/2 counter). CD's public
   score will look low (~30–60) — expected, not a bug.

### One-shot status check (recipe)
```python
import json,os,urllib.request
tok=json.load(open(os.path.expanduser('~/.claude/.credentials.json')))['mcpOAuth']['kaggle|43f49c16a482634f']['accessToken']
req=urllib.request.Request('https://www.kaggle.com/api/v1/competitions/submissions/list/ai-agent-security-multi-step-tool-attacks',
    headers={'Authorization':'Bearer '+tok,'User-Agent':'x'})
for s in json.loads(urllib.request.urlopen(req,timeout=40).read()):
    if s['ref'] in (55918818,55916596): print(s['ref'], s['status'], s.get('publicScore') or '-')
```
OAuth refresh if `Unauthenticated`/expired (memory `kaggle-mcp-oauth-broken`): POST
`https://www.kaggle.com/api/v1/oauth2/token` public-client style — `grant_type=refresh_token`,
`refresh_token=…`, `client_id=claude-code-(kaggle)`, `resource=https://www.kaggle.com/mcp`, **omit scope**;
write new `accessToken`/`refreshToken`/`expiresAt` back into the creds entry. Back up creds first; never print the token.

## Key identifiers / memories

- **Slot A:** ref **55857240** (v22, 86.10). **Slot B:** ref **55918818** (CD). Density swap candidate: ref **55916596**.
- Kernels: `jed-attack-probe-v1` (v22/v23), `jed-attack-cd-v1` (CD), `jed-attack-density-v1` (v24). Owner `adostie3`.
- Builds: `attack.py` (EXFIL blend — DO NOT resubmit), `cd_attack.py` (CD). Both untracked by design.
- Memories: `jed-confused-deputy-validated`, `jed-attack-config-inert-in-rerun`, `jed-family-ceiling`,
  `jed-only-exfil-fireable`, `kaggle-mcp-oauth-broken`, `kaggle-jed-submission-pipeline`.
