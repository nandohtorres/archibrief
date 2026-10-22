"""Static resolution of the Terraform expressions rules care about.

python-hcl2 leaves expressions as strings like "${var.x}" or
"${jsonencode({...})}". Rules that compared those strings directly missed
policies written with jsonencode(), aws_iam_policy_document data sources,
values hidden in variable defaults, and references through locals (trap
suite t01-t05, t13, f02, f03). This module resolves those few forms
statically. It never evaluates arbitrary expressions and never runs
anything: an expression it doesn't recognize is returned unchanged, and
rules treat that as "unknown", not as safe.
"""

from __future__ import annotations

import json
import re

import hcl2
from hcl2.utils import SerializationOptions

from backend.shared.terraform_scope import module_of, scoped_key

_OPTIONS = SerializationOptions(strip_string_quotes=True, with_comments=False)
_MAX_DEPTH = 6
_REFERENCE = re.compile(r"^\$\{\s*(.+?)\s*\}$", re.DOTALL)
_VAR = re.compile(r"^var\.([A-Za-z0-9_-]+)$")
_LOCAL = re.compile(r"^local\.([A-Za-z0-9_-]+)$")
_POLICY_DOC = re.compile(r"^data\.aws_iam_policy_document\.([A-Za-z0-9_-]+)\.json$")
_JSONENCODE = re.compile(r"^jsonencode\((.*)\)$", re.DOTALL)
_ATOM = r"(?:var\.[A-Za-z0-9_-]+|local\.[A-Za-z0-9_-]+|true|false|\d+)"
_CONDITIONAL = re.compile(rf"^({_ATOM})\s*\?\s*({_ATOM})\s*:\s*({_ATOM})$")
# python-hcl2 keeps heredoc markers: "<<POLICY\n{...}\nPOLICY".
_HEREDOC = re.compile(r"^<<-?([A-Za-z_][A-Za-z0-9_]*)\n(.*)\n\s*\1\s*$", re.DOTALL)


def _lookup_scoped(table: dict, module: str, name: str) -> object | None:
    key = scoped_key(module, name)
    return table.get(key) if key in table else None


def resolve(value: object, parsed: dict, module: str = "", depth: int = 0) -> object:
    """Resolve var./local./policy-document/jsonencode references, recursively."""
    if depth > _MAX_DEPTH:
        return value
    if isinstance(value, list):
        return [resolve(item, parsed, module, depth + 1) for item in value]
    if isinstance(value, dict):
        return {k: resolve(v, parsed, module, depth + 1) for k, v in value.items()}
    if not isinstance(value, str):
        return value

    match = _REFERENCE.match(value)
    if not match:
        return value
    expression = match.group(1)

    if conditional := _CONDITIONAL.fullmatch(expression.strip()):
        def atom(text: str) -> object:
            if text in ("true", "false"):
                return text == "true"
            if text.isdigit():
                return int(text)
            return resolve("${" + text + "}", parsed, module, depth + 1)

        condition = atom(conditional.group(1))
        if isinstance(condition, bool):
            return atom(conditional.group(2 if condition else 3))
        return value

    if m := _VAR.match(expression):
        variable = _lookup_scoped(parsed.get("variables", {}), module, m.group(1))
        if isinstance(variable, dict):
            if "value" in variable:
                return resolve(variable["value"], parsed, module, depth + 1)
            if "default" in variable:
                return resolve(variable["default"], parsed, module, depth + 1)
        return value
    if m := _LOCAL.match(expression):
        local = _lookup_scoped(parsed.get("locals", {}), module, m.group(1))
        return value if local is None else resolve(local, parsed, module, depth + 1)
    if m := _POLICY_DOC.match(expression):
        document = _lookup_scoped(
            parsed.get("data", {}).get("aws_iam_policy_document", {}), module, m.group(1)
        )
        if isinstance(document, dict):
            return render_policy_document(document, parsed, module, depth + 1)
        return value
    if m := _JSONENCODE.match(expression):
        try:
            decoded = hcl2.loads(f"x = {m.group(1)}\n", serialization_options=_OPTIONS)
        except Exception:  # noqa: BLE001 — unparseable means unknown, not an error
            return value
        return resolve(decoded.get("x"), parsed, module, depth + 1)
    return value


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def render_policy_document(document: dict, parsed: dict, module: str, depth: int = 0) -> dict:
    """aws_iam_policy_document statement blocks -> an IAM policy dict."""
    statements = []
    for block in _as_list(document.get("statement")):
        if not isinstance(block, dict):
            continue
        statement: dict = {
            "Effect": resolve(block.get("effect", "Allow"), parsed, module, depth),
        }
        for source, target in (
            ("actions", "Action"), ("not_actions", "NotAction"),
            ("resources", "Resource"), ("not_resources", "NotResource"),
        ):
            if source in block:
                statement[target] = resolve(block[source], parsed, module, depth)
        for source, target in (("principals", "Principal"), ("not_principals", "NotPrincipal")):
            principals: dict = {}
            for principal in _as_list(block.get(source)):
                if isinstance(principal, dict):
                    kind = principal.get("type", "AWS")
                    identifiers = _as_list(resolve(principal.get("identifiers", []), parsed, module, depth))
                    merged = principals.setdefault(kind, [])
                    merged.extend(identifier for identifier in identifiers if identifier not in merged)
            if principals:
                statement[target] = "*" if principals == {"*": ["*"]} else principals
        conditions: dict = {}
        for condition in _as_list(block.get("condition")):
            if not isinstance(condition, dict):
                continue
            test = condition.get("test")
            variable = condition.get("variable")
            if isinstance(test, str) and isinstance(variable, str):
                values = _as_list(resolve(condition.get("values", []), parsed, module, depth))
                conditions.setdefault(test, {}).setdefault(variable, []).extend(values)
        if conditions:
            statement["Condition"] = conditions
        statements.append(statement)
    return {"Version": "2012-10-17", "Statement": statements}


def policy_statements(value: object, parsed: dict, module: str = "") -> list[dict] | None:
    """The statements of a policy attribute, or None if it can't be resolved."""
    resolved = resolve(value, parsed, module)
    if isinstance(resolved, str):
        if heredoc := _HEREDOC.match(resolved.strip()):
            resolved = heredoc.group(2)
        if resolved.lstrip().startswith("${"):
            return None
        try:
            resolved = json.loads(resolved)
        except ValueError:
            return None
    if not isinstance(resolved, dict):
        return None
    statements = resolved.get("Statement")
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list):
        return None
    return [s for s in statements if isinstance(s, dict)]


def is_created(body: object, parsed: dict) -> bool:
    """False when count/for_each statically resolve to nothing (trap f01)."""
    if not isinstance(body, dict):
        return True
    module = module_of(body)
    if "count" in body:
        count = resolve(body["count"], parsed, module)
        if count in (0, "0", False):
            return False
    if "for_each" in body:
        for_each = resolve(body["for_each"], parsed, module)
        if for_each in ({}, []):
            return False
    return True


def truthy(value: object, parsed: dict, module: str = "") -> bool | None:
    """A resolved boolean attribute: True/False, or None when unknown."""
    resolved = resolve(value, parsed, module)
    if isinstance(resolved, bool):
        return resolved
    if isinstance(resolved, str):
        if resolved.lower() == "true":
            return True
        if resolved.lower() == "false":
            return False
    return None
