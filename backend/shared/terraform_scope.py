"""Module-aware naming for parsed Terraform.

Terraform treats each directory as its own module, so two modules can both
declare `aws_s3_bucket.logs`. Keying parsed resources by bare name let one
silently overwrite the other (trap t14). Resources in the root module keep
their bare name; anything in a subdirectory is keyed "<module>/<name>",
where <module> is the directory relative to the archive root.
"""

from __future__ import annotations

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
    *module_parts, name = key.split("/")
    name = _IDENTIFIER_UNSAFE.sub("", name)
    if len(name) > MAX_DISPLAY_NAME:
        name = name[: MAX_DISPLAY_NAME - 1] + "…"
    parts = [_IDENTIFIER_UNSAFE.sub("", part)[:MAX_DISPLAY_NAME] for part in module_parts]
    return "/".join([*parts, name])
