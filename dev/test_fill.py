"""Local tests for attack.py (validation-fill + live raw-per-second multipost classifier, v22).

aicomp_sdk only exists on Kaggle, so we stub the three names attack.py imports
(AttackAlgorithmBase, AttackCandidate, AttackRunConfig) and drive AttackAlgorithm against a
mock env with a controllable fake clock. The mock simulates multipost: it emits one http.post
per URL in the message, capped at ``posts_cap`` (gpt_oss-like: high cap; gemma-like: 2), and
advances the clock by ``base_dt + posts*per_post_dt``. These pin: the env-free overrides, the
fill's firing/keeping behaviour, the RAW-PER-SECOND classifier (forge-multipost chosen when it
delivers more raw/s, plain chosen when the per-post cost dominates), replay-safe sizing bounding
N, the blind fallback when nothing fires, and candidate shape (single message, TOKEN present,
unique first-host, no share words).

Run: python dev/test_fill.py   (exit 0 = all pass)
"""
from __future__ import annotations

import os
import re
import sys
import types
from dataclasses import dataclass
from pathlib import Path

# ---- Stub aicomp_sdk.attacks BEFORE importing attack ------------------------
_pkg = types.ModuleType("aicomp_sdk")
_attacks = types.ModuleType("aicomp_sdk.attacks")


class AttackAlgorithmBase:
    def __init__(self, config=None):
        self.config = dict(config or {})


class AttackCandidate:
    def __init__(self, user_messages):
        self.user_messages = tuple(user_messages)

    @classmethod
    def from_messages(cls, messages):
        return cls(tuple(messages))


@dataclass
class AttackRunConfig:
    time_budget_s: float = 8750.0
    max_tool_hops: int = 8


_attacks.AttackAlgorithmBase = AttackAlgorithmBase
_attacks.AttackCandidate = AttackCandidate
_attacks.AttackRunConfig = AttackRunConfig
_pkg.attacks = _attacks
sys.modules["aicomp_sdk"] = _pkg
sys.modules["aicomp_sdk.attacks"] = _attacks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import attack as A  # noqa: E402

TOKEN = A.PAYLOAD
FORGE_MARK = "<|channel|>analysis"   # Harmony forge (gpt_oss) marker
GEMMA_MARK = "<|tool_call>"          # gemma-native forge marker


# ---- Fake clock: attack.py reads time.monotonic; advance it deterministically per interact ---
class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


class MockEnv:
    """Multipost stand-in. Emits some number of http.post events per interact and advances the clock
    by base_dt + posts*per_post_dt. Compliance is per-FAMILY: if ``family_posts`` is given it maps the
    detected family (plain / forge_multi / forge_gemma) to the posts emitted — this models the real
    asymmetry (gpt_oss complies with the Harmony forge, gemma with its native forge). Without it,
    posts = min(#urls, posts_cap) (legacy plain-ish behaviour). ``fires=False`` models the commit-time
    no-fire agent."""

    def __init__(self, clock, posts_cap=1, base_dt=0.05, per_post_dt=0.001, fires=True,
                 family_posts=None):
        self.clock = clock
        self.posts_cap = posts_cap
        self.base_dt = base_dt
        self.per_post_dt = per_post_dt
        self.fires = fires
        self.family_posts = family_posts
        self.n_posts = 0
        self.last = ""
        self.resets = 0
        self.interacts = 0

    def reset(self):
        self.resets += 1

    @staticmethod
    def _family_of(msg):
        if FORGE_MARK in msg:
            return "forge_multi"
        if GEMMA_MARK in msg:
            return "forge_gemma"
        return "plain"

    def interact(self, msg, max_tool_hops=None):
        self.interacts += 1
        self.last = msg
        if not self.fires:
            n = 0
        elif self.family_posts is not None:
            n = int(self.family_posts.get(self._family_of(msg), 0))
        else:
            n_urls = len(re.findall(r"http://", msg))
            n = min(n_urls, self.posts_cap)
        self.n_posts = n
        self.clock.now += self.base_dt + n * self.per_post_dt

    def export_trace_dict(self):
        if not self.fires or self.n_posts == 0:
            return {"tool_events": []}
        return {"tool_events": [
            {"ok": True, "name": "http.post", "args": {"data": TOKEN}} for _ in range(self.n_posts)
        ]}


def _install_clock(clock):
    A.time.monotonic = clock.monotonic  # type: ignore[attr-defined]


def rc(budget=8750.0, hops=8):
    return AttackRunConfig(time_budget_s=budget, max_tool_hops=hops)


# ---- Assertions -------------------------------------------------------------
_failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not cond:
        _failures.append(name)


def host_of(msg):
    m = re.search(r'https?://[^\s\'"<>,]+', msg)
    return m.group(0) if m else None


# ---- Tests ------------------------------------------------------------------
def test_n_candidates_override():
    env = MockEnv(Clock())
    cands = A.AttackAlgorithm({"n_candidates": 42}).run(env, rc())
    check("override: n_candidates returns exact blind count, env untouched",
          len(cands) == 42 and env.interacts == 0, f"n={len(cands)} interacts={env.interacts}")


def test_env_none_fallback():
    cands = A.AttackAlgorithm({}).run(None, rc())
    check("env None: returns FALLBACK_N blind", len(cands) == A.FALLBACK_N, f"n={len(cands)}")
    cands2 = A.AttackAlgorithm({"emit_n": 77}).run(None, rc())
    check("env None: emit_n overrides fallback count", len(cands2) == 77, f"n={len(cands2)}")


def test_hard_cap_clamped():
    over = A.AttackAlgorithm({"n_candidates": 99999}).run(None, rc())
    check("hard_cap: n_candidates clamped to HARD_N_CAP", len(over) == A.HARD_N_CAP, f"n={len(over)}")


def test_commit_gate_returns_blind_without_fill():
    # No KAGGLE_IS_COMPETITION_RERUN and no force_fill: run() must NOT probe the env; blind emit.
    os.environ.pop("KAGGLE_IS_COMPETITION_RERUN", None)
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock)  # a FIRING env; the gate must still skip the fill
    cands = A.AttackAlgorithm({}).run(env, rc())
    check("commit-gate: returns FALLBACK_N without probing the env",
          len(cands) == A.FALLBACK_N and env.interacts == 0,
          f"n={len(cands)} interacts={env.interacts}")


def test_rerun_env_triggers_fill():
    os.environ["KAGGLE_IS_COMPETITION_RERUN"] = "1"
    try:
        clock = Clock(); _install_clock(clock)
        env = MockEnv(clock)
        cands = A.AttackAlgorithm({"hard_n_cap": 40}).run(env, rc())
        check("rerun-gate: KAGGLE_IS_COMPETITION_RERUN triggers the fill (env probed)",
              env.interacts > 0 and len(cands) == 40, f"interacts={env.interacts} n={len(cands)}")
    finally:
        os.environ.pop("KAGGLE_IS_COMPETITION_RERUN", None)


def test_fill_keeps_firing_candidates():
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock)
    # force_family="plain" isolates the shape checks from the classifier (pure single-post).
    cands = A.AttackAlgorithm({"force_fill": True, "hard_n_cap": 60, "force_family": "plain"}).run(env, rc())
    check("fill: probes the live env (not blind)", env.interacts > 0, f"interacts={env.interacts}")
    check("fill: returns firing candidates up to the cap", len(cands) == 60, f"n={len(cands)}")
    one_msg = all(len(c.user_messages) == 1 for c in cands)
    tok_ok = all(TOKEN in c.user_messages[0] for c in cands)
    hosts = {host_of(c.user_messages[0]) for c in cands}
    check("fill: single-message candidates with TOKEN present", one_msg and tok_ok,
          f"one_msg={one_msg} tok_ok={tok_ok}")
    check("fill: every returned candidate has a UNIQUE first host", len(hosts) == len(cands),
          f"unique={len(hosts)} of {len(cands)}")


def _counts(cands):
    forge = sum(FORGE_MARK in c.user_messages[0] for c in cands)
    gemma = sum(GEMMA_MARK in c.user_messages[0] for c in cands)
    plain = len(cands) - forge - gemma
    return forge, gemma, plain


def test_blend_gptoss_forge_multi_dominates():
    # gpt_oss-like: Harmony forge scales (8 posts) -> highest raw/s -> largest share, but the
    # blend still keeps gemma + single-post families present (breadth).
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock, base_dt=0.05, per_post_dt=0.05,
                  family_posts={"plain": 1, "forge_multi": 8})
    # cap=200 gives the blend enough main-fill slots that the dominant-family margin is robust to
    # the classify phase keeping 5 of every family (which otherwise dilutes the signal).
    cands = A.AttackAlgorithm({"force_fill": True, "hard_n_cap": 200}).run(env, rc())
    forge, gemma, plain = _counts(cands)
    # forge_gemma removed 2026-08-31; the mock now distinguishes only forge_multi vs the single-post
    # families (all read as "plain"). The blend must keep BOTH forge_multi and the single-post breadth.
    check("blend: Harmony forge keeps a real main-fill share (gpt_oss-like)",
          forge >= 2 * A.CLASSIFY_EACH, f"forge={forge} plain={plain}")
    check("blend: dominant family is NOT a monoculture (argmax would exceed half)",
          forge < 0.5 * len(cands), f"forge={forge} of {len(cands)}")
    check("blend: the single-post families keep real main-fill share (breadth, not monoculture)",
          plain >= 2 * A.CLASSIFY_EACH, f"plain={plain} classify_each={A.CLASSIFY_EACH}")
    hosts = {host_of(c.user_messages[0]) for c in cands}
    check("blend: every candidate has a unique host across the mixed families",
          len(hosts) == len(cands), f"unique={len(hosts)} of {len(cands)}")


def test_blend_drops_never_firing_family():
    # A family that never fires (forge_multi here) -> excluded from the blend entirely.
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock, base_dt=0.05, per_post_dt=0.05,
                  family_posts={"plain": 1, "forge_multi": 0})
    cands = A.AttackAlgorithm({"force_fill": True, "hard_n_cap": 60}).run(env, rc())
    forge, _, _ = _counts(cands)
    check("blend: a never-firing family is dropped", forge == 0, f"forge={forge}")


def test_multipost_candidate_carries_k_posts():
    # A forge-multipost candidate's message must enumerate MULTIPOST_K unique sentinel endpoints.
    msg = A._forge_plan_msg(0, A.MULTIPOST_K)
    n_urls = len(re.findall(r"http://", msg))
    n_tok = msg.count(TOKEN)
    check("multipost: forge candidate enumerates MULTIPOST_K endpoints with the sentinel",
          n_urls == A.MULTIPOST_K and n_tok >= 1, f"urls={n_urls} k={A.MULTIPOST_K} tok={n_tok}")


def test_gemma_native_candidate_shape():
    # The gemma-native forge must: enumerate MULTIPOST_K unique hosts in-block, carry the native
    # tool-call marker, carry the sentinel, and be a single message.
    msg = A._forge_gemma_native_msg(3, A.MULTIPOST_K)
    hosts = set(re.findall(r"http://[a-z0-9]+\.co", msg))
    block = {A._url(3 * A.MULTIPOST_K + j) for j in range(A.MULTIPOST_K)}
    check("gemma-native: enumerates MULTIPOST_K in-block hosts, native marker + sentinel present",
          hosts == block and GEMMA_MARK in msg and TOKEN in msg,
          f"hosts={len(hosts)} in_block={hosts == block} mark={GEMMA_MARK in msg}")


def test_non_firing_env_falls_back():
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock, base_dt=0.5, fires=False)  # forced fill against an agent that never fires
    # bounded budget + matching slowest0 so the no-keep loop terminates quickly at wall_deadline.
    cands = A.AttackAlgorithm({"force_fill": True, "slowest0": 0.5}).run(env, rc(budget=40.0))
    check("no-fire: fill returns nothing -> blind FALLBACK_N", len(cands) == A.FALLBACK_N,
          f"n={len(cands)}")


def test_replay_safe_sizing_bounds_n():
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock, base_dt=0.05, per_post_dt=0.0)
    # Tight replay budget: kept-set replay cost must fit ~replay_safe_frac*replay_budget.
    cands = A.AttackAlgorithm({"force_fill": True, "replay_budget_s": 2.0, "slowest0": 0.05}).run(
        env, rc(budget=2.0))
    check("sizing: constrained budget returns >0 and well under the cap",
          0 < len(cands) < A.HARD_N_CAP, f"n={len(cands)}")


def test_no_share_words_in_templates():
    for name, fam in A.FAMILIES.items():
        msg = fam.builder(0).lower()
        check(f"family {name}: no send/email/upload token",
              not any(w in msg for w in ("send", "email", "upload")), msg[:120])


def test_families_declared_as_data():
    fam = A.FAMILIES
    check("families: declared as a name->Family(builder, expected_posts) map",
          isinstance(fam, dict) and {"plain", "forge_multi"} <= set(fam)
          and "forge_gemma" not in fam,
          f"names={sorted(fam)}")
    ok = all(callable(f.builder) and isinstance(f.expected_posts, int) for f in fam.values())
    check("families: every entry has a callable builder and int expected_posts", ok)
    # plain builder still emits a single-message candidate carrying the literal marker in data.
    msg = A.FAMILIES["plain"].builder(0)
    check("families: plain builder emits literal marker", TOKEN in msg, msg[:80])


def test_wording_builders_diverse_and_safe():
    k = A.MULTIPOST_K
    msgs = [A._msg(0, A.TEMPLATE),
            A._wording_builder(k, A.WORDING1)(0),
            A._wording_builder(k, A.WORDING2)(0),
            A._wording_builder(k, A.WORDING3)(0)]
    check("wording: 4 single-post templates are all distinct", len(set(msgs)) == 4)
    for tmpl in (A.WORDING1, A.WORDING2, A.WORDING3):
        m = A._wording_builder(k, tmpl)(0); low = m.lower()
        check("wording: carries the literal marker in data", TOKEN in m, m[:80])
        check("wording: no send/email/upload",
              not any(w in low for w in ("send", "email", "upload")))
        check("wording: avoids the 'call ... once' wording",
              re.search(r"call\b.*\bonce\b", low) is None, m[:80])


def test_split_marker_prompt_has_no_contiguous_marker():
    m = A._split_marker_builder(A.MULTIPOST_K)(0); low = m.lower()
    check("split_marker: prompt has NO contiguous SECRET_MARKER token", TOKEN not in m, m[:120])
    check("split_marker: prompt carries both fragments to assemble",
          "SECRET_" in m and "MARKER" in m, m[:120])
    check("split_marker: single http endpoint present", len(re.findall(r"http://", m)) == 1)
    check("split_marker: no send/email/upload",
          not any(w in low for w in ("send", "email", "upload")))


def test_data_framing_marker_literal_and_structured():
    m = A._data_framing_builder(A.MULTIPOST_K)(0); low = m.lower()
    check("data_framing: carries the literal marker (embedded in JSON)", TOKEN in m, m[:120])
    check("data_framing: data is structured (JSON braces present)", "{" in m and "}" in m)
    check("data_framing: distinct from plain template", m != A._msg(0, A.TEMPLATE))
    check("data_framing: no send/email/upload",
          not any(w in low for w in ("send", "email", "upload")))


def test_blend_weights_floor_and_proportions():
    tp = {"a": 8.0, "b": 2.0}            # only firing families are passed in
    share = A._blend_weights(tp, {}, floor=0.1)
    check("blend_weights: shares sum to 1", abs(sum(share.values()) - 1.0) < 1e-9, str(share))
    check("blend_weights: each family >= floor", all(v >= 0.1 - 1e-9 for v in share.values()))
    check("blend_weights: higher throughput -> higher share", share["a"] > share["b"], str(share))


def test_blend_weights_survival_reweights():
    tp = {"a": 4.0, "b": 4.0}
    share = A._blend_weights(tp, {"b": 3.0}, floor=0.0)  # survival triples b's weight
    check("blend_weights: survival weight shifts share toward b", share["b"] > share["a"], str(share))


def test_next_family_tracks_target_share():
    share = {"a": 0.75, "b": 0.25}
    served = {"a": 0, "b": 0}
    picks = []
    for _ in range(100):
        f = A._next_family(share, served); served[f] += 1; picks.append(f)
    check("next_family: served ratio tracks the target share",
          abs(served["a"] / 100 - 0.75) <= 0.05 and served["b"] >= 20, str(served))


def test_blend_weights_all_zero_is_uniform():
    share = A._blend_weights({"a": 0.0, "b": 0.0}, {}, floor=0.0)
    check("blend_weights: all-zero throughput -> uniform", abs(share["a"] - share["b"]) < 1e-9)


def test_reduce_to_v22_is_argmax_monoculture():
    # gpt_oss-like env; with reduce_to_v22 the family set is {plain, forge_multi} and the main fill
    # is a single-winner monoculture (the banked v22 behavior) -> NO gemma, all-tail one signature.
    clock = Clock(); _install_clock(clock)
    env = MockEnv(clock, base_dt=0.05, per_post_dt=0.05,
                  family_posts={"plain": 1, "forge_multi": 8, "forge_gemma": 5})
    cands = A.AttackAlgorithm(
        {"force_fill": True, "reduce_to_v22": True, "hard_n_cap": 40}).run(env, rc())
    tail = cands[2 * A.CLASSIFY_EACH:]  # only 2 families are classified under reduce_to_v22
    forge_tail = tail and all(FORGE_MARK in c.user_messages[0] for c in tail)
    no_gemma = all(GEMMA_MARK not in c.user_messages[0] for c in cands)
    check("reduce_to_v22: only {plain, forge_multi} used (no gemma-native forge)", no_gemma)
    check("reduce_to_v22: main fill is a single-winner monoculture (v22 behavior)",
          bool(forge_tail), f"tail={len(tail)} all_forge={forge_tail}")


def test_family_survival_reweights_corpus():
    # forge_multi and the single-post families at EQUAL live throughput; a survival weight favoring
    # forge_multi must shift the returned blend toward forge_multi candidates (the validator hook).
    def run_with(survival):
        clock = Clock(); _install_clock(clock)
        env = MockEnv(clock, base_dt=0.05, per_post_dt=0.02,
                      family_posts={"plain": 5, "forge_multi": 5})
        cands = A.AttackAlgorithm(
            {"force_fill": True, "hard_n_cap": 80, "family_survival": survival}).run(env, rc())
        return _counts(cands)

    f_base, _, _ = run_with({})
    f_boost, _, _ = run_with({"forge_multi": 4.0})
    check("survival hook: boosting forge_multi survival increases its share of the corpus",
          f_boost > f_base, f"base={f_base} boost={f_boost}")


if __name__ == "__main__":
    print("Running attack.py (validation-fill + raw-per-second multipost classifier) tests...")
    for t in (
        test_n_candidates_override,
        test_env_none_fallback,
        test_hard_cap_clamped,
        test_commit_gate_returns_blind_without_fill,
        test_rerun_env_triggers_fill,
        test_fill_keeps_firing_candidates,
        test_blend_gptoss_forge_multi_dominates,
        test_blend_drops_never_firing_family,
        test_multipost_candidate_carries_k_posts,
        test_gemma_native_candidate_shape,
        test_non_firing_env_falls_back,
        test_replay_safe_sizing_bounds_n,
        test_no_share_words_in_templates,
        test_families_declared_as_data,
        test_wording_builders_diverse_and_safe,
        test_split_marker_prompt_has_no_contiguous_marker,
        test_data_framing_marker_literal_and_structured,
        test_blend_weights_floor_and_proportions,
        test_blend_weights_survival_reweights,
        test_next_family_tracks_target_share,
        test_blend_weights_all_zero_is_uniform,
        test_reduce_to_v22_is_argmax_monoculture,
        test_family_survival_reweights_corpus,
    ):
        t()
    print()
    if _failures:
        print(f"FAILED: {_failures}")
        sys.exit(1)
    print("ALL TESTS PASSED")
