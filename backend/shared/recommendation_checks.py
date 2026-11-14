"""Recommendations that are wrong for the problem they are attached to.

Found in the P1 baseline: a finding about a public Lambda function URL
recommended putting the function in a VPC. A VPC does not restrict who can
call a function URL, and moving a function into a VPC can cut its outbound
access, so the fix neither works nor is safe. Kept in one place so the
reasoning step's verification and the P1 regression guards agree.
"""

from __future__ import annotations

import re

_FUNCTION_URL = re.compile(r"function[ _]url", re.IGNORECASE)
# "attach/place/move ... in a VPC": the recommendation to do it. A dot inside
# an identifier (aws_lambda_function.name) is not the end of the sentence.
_VPC_FIX = re.compile(
    r"\b(attach|place|put|move|run|deploy|connect|add)\w*\b(?:[^.;]|\.(?=\w)){0,80}\bvpc\b",
    re.IGNORECASE,
)
# ... unless the sentence says it does not help ("a VPC does not restrict ...").
_NEGATION = re.compile(r"\b(not|never|cannot|can't|doesn't|no)\b", re.IGNORECASE)
_SENTENCES = re.compile(r"(?<=[.;])\s+")


def recommends_vpc_for_function_url(finding_text: str, recommendation: str) -> bool:
    """A function-URL finding whose fix is to place the function in a VPC."""
    if not _FUNCTION_URL.search(finding_text or ""):
        return False
    return any(
        _VPC_FIX.search(sentence) and not _NEGATION.search(sentence)
        for sentence in _SENTENCES.split(recommendation or "")
    )
