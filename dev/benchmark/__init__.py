"""dev/benchmark — local robustness benchmark for the candidate corpus.

Scores the corpus under a permissive baseline (OptimalGuardrail) and a seeded
ensemble of stricter stochastic guardrails, reporting a survival ratio. Developer
tooling only: no change to attack.py or the submission. See README.md.
"""
