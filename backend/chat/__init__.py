"""Grounded report chat (ADR-0046 §4, ADR-0050).

One bounded model call per question, about one stored review. Shared by
the ask_question Lambda and the paid chat eval, so both run the same
context building, prompt and verification.
"""
