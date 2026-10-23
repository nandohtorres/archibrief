"""Module-aware naming for parsed Terraform.

Terraform treats each directory as its own module, so two modules can both
declare `aws_s3_bucket.logs`. Keying parsed resources by bare name let one
silently overwrite the other (trap t14). Resources in the root module keep
their bare name; anything in a subdirectory is keyed "<module>/<name>",
where <module> is the directory relative to the archive root.
"""

from __future__ import annotations

import hashlib
import re

MODULE_FIELD = "__module__"

# What a Terraform identifier may contain. Anything else in a name that
# reaches finding text is dropped.
_IDENTIFIER_UNSAFE = re.compile(r"[^A-Za-z0-9_-]")
# Long enough for real names, short enough that a name can't carry a
# sentence-length instruction into text the model reads.
MAX_DISPLAY_NAME = 32


def scoped_key(module: str, name: str) -> str:
    return f"{module}/{name}" if module else name


def module_of(body: object) -> str:
    if isinstance(body, dict):
        value = body.get(MODULE_FIELD, "")
        return value if isinstance(value, str) else ""
    return ""


def display_name(key: str) -> str:
    """A resource key made safe to put in finding text.

    Keeps the module path, restricts each segment to identifier
    characters, and truncates the name itself.
    """
    parts = key.split("/")
    out = []
    for index, part in enumerate(parts):
        safe = _IDENTIFIER_UNSAFE.sub("", part)
        if safe != part or len(safe) > MAX_DISPLAY_NAME or not safe:
            identity = "/".join(parts[: index + 1])
            suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
            safe = safe[: MAX_DISPLAY_NAME - 9] + "_" + suffix
        out.append(safe)
    return "/".join(out)
