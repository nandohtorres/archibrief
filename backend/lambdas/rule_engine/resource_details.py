"""Structured facts for resources whose risk lives in nested blocks.

resource_summary.py reads one value per allowlisted setting. Some of the
riskiest configuration doesn't fit that shape: a security group's
ingress rules, who a role trusts and on what condition, which actions a
policy grants, where a CloudFront origin points and how it connects, and
whether a container definition carries a credential in plain text. A
hard test review missed every one of these because the model never saw
them.

The same rules as the summary apply. Nothing free-form reaches the
model: every string is a fixed label from this module, a value from an
allowlist, or a resource name cleaned by display_name(). Policy actions
are reported only when they are on SENSITIVE_ACTIONS; other actions are
counted. Environment variable names and values are never copied, only
counted. Anything that can't be resolved statically is "unknown".
"""

from __future__ import annotations

import re

from backend.lambdas.rule_engine.hcl_eval import policy_statements, resolve
from backend.shared.terraform_scope import display_name

UNKNOWN = "unknown"
MAX_RULES = 10
MAX_STATEMENTS = 10
MAX_CONTAINERS = 10
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


def _as_list(value: object) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _is_reference(value: object) -> bool:
    return isinstance(value, str) and "${" in value


# --- Security groups ----------------------------------------------------


def inline_ingress_rules(body: dict, parsed: dict, module: str) -> list[dict]:
    """A security group's ingress blocks, including `dynamic "ingress"`
    blocks whose for_each resolves to something non-empty (the
    `var.enabled ? [1] : []` switch). A dynamic block that can't be
    resolved is left out; ingress_rules() reports it as conditional."""
    rules = [rule for rule in _as_list(body.get("ingress")) if isinstance(rule, dict)]
    for block in _dynamic_ingress(body):
        for_each = resolve(block.get("for_each"), parsed, module)
        if isinstance(for_each, (list, dict)) and for_each:
            rules.extend(c for c in _as_list(block.get("content")) if isinstance(c, dict))
    return rules


def _dynamic_ingress(body: dict) -> list[dict]:
    blocks = []
    for dynamic in _as_list(body.get("dynamic")):
        block = dynamic.get("ingress") if isinstance(dynamic, dict) else None
        if isinstance(block, dict):
            blocks.append(block)
    return blocks


def _ports(rule: dict, parsed: dict, module: str, protocol_key: str = "protocol") -> str:
    protocol = str(resolve(rule.get(protocol_key), parsed, module))
    if protocol in ("-1", "all"):
        return "all"
    start = resolve(rule.get("from_port"), parsed, module)
    end = resolve(rule.get("to_port"), parsed, module)
    try:
        start, end = int(start), int(end)
    except (TypeError, ValueError):
        return UNKNOWN
    return str(start) if start == end else f"{start}-{end}"


_PROTOCOLS = {"tcp", "udp", "icmp", "icmpv6", "-1", "all", "6", "17"}


def _source(rule: dict, parsed: dict, module: str) -> str:
    cidrs = [
        str(c)
        for c in _as_list(resolve(rule.get("cidr_blocks"), parsed, module))
        + _as_list(resolve(rule.get("ipv6_cidr_blocks"), parsed, module))
    ]
    if any(c in _OPEN_CIDRS for c in cidrs):
        return "internet (0.0.0.0/0 or ::/0)"
    if rule.get("security_groups") or rule.get("source_security_group_id"):
        return "another security group"
    if rule.get("prefix_list_ids"):
        return "prefix list"
    if rule.get("self"):
        return "same security group"
    if cidrs:
        return "unknown" if any(_is_reference(c) for c in cidrs) else "specific address range"
    return UNKNOWN


def _ingress_fact(rule: dict, parsed: dict, module: str, conditional: bool) -> dict:
    protocol = str(resolve(rule.get("protocol"), parsed, module)).lower()
    fact = {
        "ports": _ports(rule, parsed, module),
        "protocol": protocol if protocol in _PROTOCOLS else UNKNOWN,
        "source": _source(rule, parsed, module),
    }
    if conditional:
        fact["created"] = "only when a condition in the code holds (dynamic block)"
    return fact


def ingress_rules(body: dict, parsed: dict, module: str) -> dict:
    rules: list[dict] = []
    for rule in _as_list(body.get("ingress")):
        if isinstance(rule, dict):
            rules.append(_ingress_fact(rule, parsed, module, conditional=False))
    for block in _dynamic_ingress(body):
        for_each = resolve(block.get("for_each"), parsed, module)
        if isinstance(for_each, (list, dict)) and not for_each:
            continue  # switched off
        known = isinstance(for_each, (list, dict))
        for content in _as_list(block.get("content")):
            if isinstance(content, dict):
                fact = _ingress_fact(content, parsed, module, conditional=not known)
                if known:
                    fact["created"] = "yes (dynamic block, enabled by its current inputs)"
                rules.append(fact)
    return {
        "ingress": rules[:MAX_RULES],
        "ingress_total": len(rules),
    }


# --- IAM ----------------------------------------------------------------

# Actions worth naming to a reviewer: privilege escalation paths, data
# access and destructive operations. Anything else is only counted.
SENSITIVE_ACTIONS = frozenset(
    {
        "iam:PassRole",
        "iam:CreateRole",
        "iam:CreateUser",
        "iam:CreateAccessKey",
        "iam:CreateLoginProfile",
        "iam:UpdateLoginProfile",
        "iam:AttachRolePolicy",
        "iam:AttachUserPolicy",
        "iam:AttachGroupPolicy",
        "iam:PutRolePolicy",
        "iam:PutUserPolicy",
        "iam:PutGroupPolicy",
        "iam:CreatePolicyVersion",
        "iam:SetDefaultPolicyVersion",
        "iam:UpdateAssumeRolePolicy",
        "iam:AddUserToGroup",
        "sts:AssumeRole",
        "lambda:CreateFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:InvokeFunction",
        "lambda:AddPermission",
        "ec2:RunInstances",
        "ecs:RunTask",
        "ecs:RegisterTaskDefinition",
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "glue:CreateDevEndpoint",
        "codebuild:CreateProject",
        "ssm:SendCommand",
        "ssm:StartSession",
        "ssm:GetParameter",
        "ssm:GetParameters",
        "secretsmanager:GetSecretValue",
        "kms:Decrypt",
        "kms:CreateGrant",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:PutBucketPolicy",
        "s3:PutBucketAcl",
        "s3:DeleteBucket",
        "dynamodb:Scan",
        "dynamodb:DeleteTable",
        "rds:DeleteDBCluster",
        "rds:DeleteDBInstance",
        "rds:ModifyDBInstance",
        "rds:ModifyDBCluster",
        "ec2:ModifyInstanceAttribute",
        "ec2:AuthorizeSecurityGroupIngress",
        "organizations:LeaveOrganization",
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
    }
)
# Service prefixes a wildcard like "iam:*" may be reported with.
_SERVICES = frozenset(
    {
        *(action.split(":", 1)[0] for action in SENSITIVE_ACTIONS),
        "sqs",
        "sns",
        "logs",
        "cloudwatch",
        "xray",
        "events",
        "states",
        "ecr",
        "elasticache",
        "elasticloadbalancing",
        "cloudfront",
        "route53",
        "apigateway",
        "execute-api",
        "athena",
        "kinesis",
        "firehose",
        "bedrock",
        "account",
        "acm",
        "wafv2",
        "backup",
        "config",
        "guardduty",
        "securityhub",
    }
)
_SENSITIVE_LOWER = {action.lower(): action for action in SENSITIVE_ACTIONS}


def _action_facts(actions: list) -> tuple[list[str], int]:
    named: set[str] = set()
    other = 0
    for action in actions:
        text = str(action)
        if text == "*":
            named.add("* (every action)")
        elif text.lower() in _SENSITIVE_LOWER:
            named.add(_SENSITIVE_LOWER[text.lower()])
        elif text.endswith(":*") and text[:-2].lower() in _SERVICES:
            named.add(f"{text[:-2].lower()}:* (every {text[:-2].lower()} action)")
        else:
            other += 1
    return sorted(named), other


def _resource_scope(statement: dict) -> str:
    if statement.get("NotResource") is not None:
        return "everything except listed resources (NotResource)"
    resources = [str(r) for r in _as_list(statement.get("Resource"))]
    if not resources:
        return UNKNOWN
    if "*" in resources:
        return "all resources (*)"
    if any(r.endswith((":*", "/*")) for r in resources):
        return "specific resources (some with wildcards)"
    return "specific resources"


def policy_facts(document: object, parsed: dict, module: str) -> dict | None:
    statements = policy_statements(document, parsed, module)
    if not statements:
        return None
    facts = []
    for statement in statements[:MAX_STATEMENTS]:
        effect = statement.get("Effect", "Allow")
        fact: dict = {"effect": effect if effect in ("Allow", "Deny") else UNKNOWN}
        if statement.get("NotAction") is not None:
            excluded, other = _action_facts(_as_list(statement.get("NotAction")))
            fact["actions"] = "every action except those listed (NotAction)"
            fact["excluded_sensitive_actions"] = excluded
            fact["excluded_other_actions"] = other
        else:
            named, other = _action_facts(_as_list(statement.get("Action")))
            fact["sensitive_actions"] = named
            fact["other_actions"] = other
        fact["resources"] = _resource_scope(statement)
        fact["has_condition"] = bool(statement.get("Condition"))
        facts.append(fact)
    return {"statements": facts, "statements_total": len(statements)}


# Condition keys a trust policy's safety depends on.
_TRUST_KEYS = {
    "sts:externalid": "sts:ExternalId",
    "aws:principalorgid": "aws:PrincipalOrgID",
    "aws:multifactorauthpresent": "aws:MultiFactorAuthPresent",
    "aws:sourcearn": "aws:SourceArn",
    "aws:sourceaccount": "aws:SourceAccount",
    "token.actions.githubusercontent.com:sub": "token.actions.githubusercontent.com:sub",
    "token.actions.githubusercontent.com:aud": "token.actions.githubusercontent.com:aud",
}
_OPERATORS = {
    "StringEquals",
    "StringLike",
    "StringNotEquals",
    "StringNotLike",
    "ArnEquals",
    "ArnLike",
    "Bool",
    "ForAnyValue:StringLike",
    "ForAnyValue:StringEquals",
    "ForAllValues:StringLike",
    "ForAllValues:StringEquals",
}
_SERVICE_PRINCIPAL = re.compile(r"^[a-z0-9-]{2,40}(\.[a-z0-9-]{2,40}){0,2}\.amazonaws\.com$")
_ACCOUNT_ARN = re.compile(r"^(?:arn:aws[a-z-]*:iam::)?(\d{12})(?::root)?$")


def _github_scope(values: list[str]) -> str:
    """What a GitHub OIDC `sub` condition admits, as a fixed label."""
    scopes = set()
    for value in values:
        if "${" in value and not value.startswith("repo:"):
            scopes.add(UNKNOWN)
            continue
        rest = value.removeprefix("repo:")
        repo, _, qualifier = rest.partition(":")
        if repo.endswith("/*") or repo == "*" or "*" in repo:
            scopes.add("any repository in the organization (wildcard)")
        elif qualifier in ("*", ""):
            scopes.add("any branch, tag, pull request or environment of one repository")
        elif qualifier.startswith("ref:refs/heads/") and "*" not in qualifier:
            scopes.add("one branch")
        elif qualifier.startswith("ref:refs/heads/"):
            scopes.add("branches matching a wildcard")
        elif qualifier.startswith("environment:") and "*" not in qualifier:
            scopes.add("one deployment environment")
        elif qualifier == "pull_request":
            scopes.add("pull requests")
        elif "*" in qualifier:
            scopes.add("wildcard")
        else:
            scopes.add("specific subject")
    return ", ".join(sorted(scopes)) or UNKNOWN


def trust_facts(body: dict, parsed: dict, module: str) -> dict | None:
    statements = policy_statements(body.get("assume_role_policy"), parsed, module)
    if not statements:
        return None
    facts = []
    for statement in statements[:MAX_STATEMENTS]:
        principal = statement.get("Principal")
        fact: dict = {"effect": statement.get("Effect", "Allow")}
        if principal == "*" or (isinstance(principal, dict) and principal.get("AWS") == "*"):
            fact["trusted"] = "anyone (*)"
        elif isinstance(principal, dict):
            trusted = []
            for service in _as_list(principal.get("Service")):
                service = str(service)
                trusted.append(
                    f"AWS service {service}"
                    if _SERVICE_PRINCIPAL.fullmatch(service)
                    else "an AWS service"
                )
            for account in _as_list(principal.get("AWS")):
                account = str(account)
                if "aws_caller_identity" in account:
                    trusted.append("this account")
                elif _ACCOUNT_ARN.fullmatch(account) or "${var." in account:
                    # The code can't say whether the ID is this account.
                    trusted.append(
                        "a whole AWS account by ID (any role or user that account allows)"
                    )
                else:
                    trusted.append("a specific AWS role or user")
            for federated in _as_list(principal.get("Federated")):
                federated = str(federated)
                if (
                    "githubusercontent" in federated
                    or "openid_connect_provider.github" in federated
                ):
                    trusted.append("GitHub Actions (OIDC)")
                elif "saml-provider" in federated or "saml_provider" in federated:
                    trusted.append("a SAML identity provider")
                else:
                    trusted.append("a federated identity provider")
            fact["trusted"] = sorted(set(trusted)) or UNKNOWN
        else:
            fact["trusted"] = UNKNOWN
        conditions: dict[str, str] = {}
        condition = statement.get("Condition")
        github_values: list[str] = []
        if isinstance(condition, dict):
            for operator, pairs in condition.items():
                if not isinstance(pairs, dict):
                    continue
                for key, values in pairs.items():
                    label = _TRUST_KEYS.get(str(key).lower())
                    if not label:
                        continue
                    shown = operator if operator in _OPERATORS else "other operator"
                    conditions[label] = shown
                    if label.endswith(":sub"):
                        github_values += [str(v) for v in _as_list(values)]
        fact["condition_keys"] = conditions
        if github_values:
            fact["github_subject_admits"] = _github_scope(github_values)
        facts.append(fact)
    return {"trust": facts}


# AWS-managed policies a reviewer should see by name. Others are
# described generically so a made-up name never reaches the model.
_KNOWN_MANAGED_POLICIES = frozenset(
    {
        "AdministratorAccess",
        "PowerUserAccess",
        "ReadOnlyAccess",
        "ViewOnlyAccess",
        "SecurityAudit",
        "IAMFullAccess",
        "AmazonS3FullAccess",
        "AmazonS3ReadOnlyAccess",
        "AmazonDynamoDBFullAccess",
        "AmazonEC2FullAccess",
        "AmazonRDSFullAccess",
        "AmazonSQSFullAccess",
        "AmazonSNSFullAccess",
        "AmazonSSMFullAccess",
        "AWSLambda_FullAccess",
        "SecretsManagerReadWrite",
        "AWSLambdaBasicExecutionRole",
        "AWSLambdaVPCAccessExecutionRole",
        "AmazonECSTaskExecutionRolePolicy",
        "AmazonSSMManagedInstanceCore",
        "CloudWatchAgentServerPolicy",
    }
)
_MANAGED_ARN = re.compile(
    r"^arn:aws[a-z-]*:iam::aws:policy/(?:[A-Za-z0-9_+=,.@-]+/)*([A-Za-z0-9_+=,.@-]+)$"
)


def attachment_facts(body: dict, parsed: dict, module: str) -> dict:
    arn = resolve(body.get("policy_arn"), parsed, module)
    if isinstance(arn, str) and (match := _MANAGED_ARN.fullmatch(arn)):
        name = match.group(1)
        policy = (
            f"AWS managed: {name}"
            if name in _KNOWN_MANAGED_POLICIES
            else "another AWS managed policy"
        )
    elif _is_reference(arn):
        policy = "a policy defined in this code" if "aws_iam_policy." in str(arn) else UNKNOWN
    else:
        policy = "a customer managed policy"
    return {"policy": policy}


# --- CloudFront ---------------------------------------------------------

_ORIGIN_POLICIES = {"http-only", "https-only", "match-viewer"}
_VIEWER_POLICIES = {"allow-all", "https-only", "redirect-to-https"}
_TLS_MINIMUMS = {
    "SSLv3",
    "TLSv1",
    "TLSv1_2016",
    "TLSv1.1_2016",
    "TLSv1.2_2018",
    "TLSv1.2_2019",
    "TLSv1.2_2021",
    "TLSv1.2_2025",
    "TLSv1.3_2025",
}


def _points_to(domain: object) -> str:
    text = str(domain)
    if "aws_s3_bucket." in text:
        return "S3 bucket"
    if "aws_lb." in text or "aws_alb." in text or ".elb.amazonaws.com" in text:
        return "load balancer"
    if "aws_api_gateway" in text or "aws_apigatewayv2" in text or "execute-api" in text:
        return "API Gateway"
    if "aws_lambda_function_url" in text:
        return "Lambda function URL"
    return UNKNOWN if _is_reference(domain) else "another domain"


def cloudfront_facts(body: dict, parsed: dict, module: str) -> dict:
    origins = []
    for origin in _as_list(body.get("origin"))[:MAX_RULES]:
        if not isinstance(origin, dict):
            continue
        fact: dict = {"points_to": _points_to(origin.get("domain_name"))}
        custom = _first(origin.get("custom_origin_config"))
        if isinstance(custom, dict):
            policy = resolve(custom.get("origin_protocol_policy"), parsed, module)
            fact["connection_to_origin"] = policy if policy in _ORIGIN_POLICIES else UNKNOWN
        elif origin.get("origin_access_control_id"):
            fact["access_control"] = "origin access control"
        elif isinstance(_first(origin.get("s3_origin_config")), dict):
            fact["access_control"] = "origin access identity (legacy)"
        else:
            fact["access_control"] = "none declared"
        origins.append(fact)

    def viewer(block: object) -> str:
        policy = (
            resolve(block.get("viewer_protocol_policy"), parsed, module)
            if isinstance(block, dict)
            else None
        )
        return policy if policy in _VIEWER_POLICIES else UNKNOWN

    certificate = _first(body.get("viewer_certificate"))
    certificate = certificate if isinstance(certificate, dict) else {}
    minimum = resolve(certificate.get("minimum_protocol_version"), parsed, module)
    return {
        "origins": origins,
        "default_viewer_protocol": viewer(_first(body.get("default_cache_behavior"))),
        "other_behaviors_viewer_protocol": [
            viewer(b) for b in _as_list(body.get("ordered_cache_behavior"))[:MAX_RULES]
        ],
        "web_acl_attached": bool(body.get("web_acl_id")),
        "uses_default_cloudfront_certificate": bool(
            resolve(certificate.get("cloudfront_default_certificate"), parsed, module) is True
        ),
        "minimum_viewer_tls": minimum
        if minimum in _TLS_MINIMUMS
        else ("not set" if minimum is None else UNKNOWN),
        "access_logging": bool(body.get("logging_config")),
    }


# --- Credentials in configuration ---------------------------------------

_SECRET_NAME = re.compile(
    r"(?i)(secret|passw|pwd|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|auth)"
)


def _variable_counts(pairs: list[tuple[object, object]]) -> dict:
    """Counts only: never a variable's name or value."""
    literal_secret_like = 0
    secret_like_from_reference = 0
    for name, value in pairs:
        if not _SECRET_NAME.search(str(name)):
            continue
        if isinstance(value, str) and value and not _is_reference(value):
            literal_secret_like += 1
        else:
            secret_like_from_reference += 1
    return {
        "variables": len(pairs),
        "secret_like_names_with_literal_values": literal_secret_like,
        "secret_like_names_from_references": secret_like_from_reference,
    }


def _image_tag(image: object) -> str:
    text = str(image)
    if "@sha256:" in text:
        return "pinned by digest"
    tail = text.rsplit("/", 1)[-1]
    if ":" not in tail:
        return "no tag (defaults to latest)"
    tag = tail.rsplit(":", 1)[1]
    if tag == "latest":
        return "latest"
    return UNKNOWN if "${" in tag else "fixed tag"


def task_definition_facts(body: dict, parsed: dict, module: str) -> dict | None:
    containers = resolve(body.get("container_definitions"), parsed, module)
    if not isinstance(containers, list):
        return None
    facts = []
    for container in containers[:MAX_CONTAINERS]:
        if not isinstance(container, dict):
            continue
        env = [
            (item.get("name"), item.get("value"))
            for item in _as_list(container.get("environment"))
            if isinstance(item, dict)
        ]
        privileged = container.get("privileged")
        read_only = container.get("readonlyRootFilesystem")
        facts.append(
            {
                "image_tag": _image_tag(container.get("image")),
                "environment": _variable_counts(env),
                "secrets_from_a_secret_store": len(_as_list(container.get("secrets"))),
                "privileged": privileged
                if isinstance(privileged, bool)
                else "not set (default: false)",
                "read_only_root_filesystem": read_only
                if isinstance(read_only, bool)
                else "not set (default: false)",
            }
        )
    return {"containers": facts, "containers_total": len(containers)}


def lambda_facts(body: dict, parsed: dict, module: str) -> dict:
    environment = _first(body.get("environment"))
    variables = environment.get("variables") if isinstance(environment, dict) else None
    variables = resolve(variables, parsed, module)
    pairs = list(variables.items()) if isinstance(variables, dict) else []
    return {
        "runs_in_a_vpc": bool(body.get("vpc_config")),
        "environment": _variable_counts(pairs),
        "dead_letter_target": bool(body.get("dead_letter_config")),
    }


# --- Queues and parameter groups ----------------------------------------

_SQS_ARN_REFERENCE = re.compile(r"^\$\{aws_sqs_queue\.([A-Za-z0-9_-]+)\.arn\}$")


def queue_facts(body: dict, parsed: dict, module: str) -> dict:
    redrive = resolve(body.get("redrive_policy"), parsed, module)
    if not body.get("redrive_policy"):
        return {"dead_letter_queue": "none"}
    if not isinstance(redrive, dict):
        return {"dead_letter_queue": UNKNOWN}
    target = str(redrive.get("deadLetterTargetArn", ""))
    match = _SQS_ARN_REFERENCE.fullmatch(target)
    queues = parsed.get("resources", {}).get("aws_sqs_queue", {})
    name = UNKNOWN
    if match:
        key = next(
            (k for k in queues if k == match.group(1) or k.endswith("." + match.group(1))), None
        )
        name = display_name(key) if key else UNKNOWN
    receives = redrive.get("maxReceiveCount")
    return {
        "dead_letter_queue": name,
        "max_receive_count": receives if isinstance(receives, int) else UNKNOWN,
    }


# Database parameters that change security or what gets logged.
_DB_PARAMETERS = frozenset(
    {
        "rds.force_ssl",
        "require_secure_transport",
        "ssl",
        "log_min_duration_statement",
        "log_statement",
        "log_connections",
        "log_disconnections",
        "pgaudit.log",
        "general_log",
        "slow_query_log",
        "server_audit_logging",
        "tls_version",
        "ssl_min_protocol_version",
    }
)
_PARAMETER_VALUES = re.compile(
    r"^(-?\d{1,9}|ON|OFF|on|off|true|false|all|none|ddl|mod|TLSv1(\.[0-3])?)$"
)


def parameter_group_facts(body: dict, parsed: dict, module: str) -> dict:
    parameters = {}
    for parameter in _as_list(body.get("parameter")):
        if not isinstance(parameter, dict):
            continue
        name = str(resolve(parameter.get("name"), parsed, module))
        if name not in _DB_PARAMETERS:
            continue
        value = resolve(parameter.get("value"), parsed, module)
        text = str(value)
        parameters[name] = text if _PARAMETER_VALUES.fullmatch(text) else UNKNOWN
    return {"security_relevant_parameters": parameters}


# --- Entry point --------------------------------------------------------

_EXTRACTORS = {
    "aws_security_group": ingress_rules,
    "aws_iam_role": trust_facts,
    "aws_iam_role_policy_attachment": attachment_facts,
    "aws_iam_group_policy_attachment": attachment_facts,
    "aws_iam_user_policy_attachment": attachment_facts,
    "aws_cloudfront_distribution": cloudfront_facts,
    "aws_ecs_task_definition": task_definition_facts,
    "aws_lambda_function": lambda_facts,
    "aws_sqs_queue": queue_facts,
    "aws_rds_cluster_parameter_group": parameter_group_facts,
    "aws_db_parameter_group": parameter_group_facts,
}
_POLICY_DOCUMENTS = {
    "aws_iam_role_policy": "policy",
    "aws_iam_policy": "policy",
    "aws_iam_group_policy": "policy",
    "aws_iam_user_policy": "policy",
}


# Types that get a "details" object.
DETAILED_TYPES = frozenset(_EXTRACTORS) | frozenset(_POLICY_DOCUMENTS)


def resource_details(resource_type: str, body: dict, parsed: dict, module: str) -> dict | None:
    """Fixed-vocabulary facts for one resource, or None for other types."""
    if resource_type in _POLICY_DOCUMENTS:
        return policy_facts(body.get(_POLICY_DOCUMENTS[resource_type]), parsed, module)
    extractor = _EXTRACTORS.get(resource_type)
    if extractor is None:
        return None
    details = extractor(body, parsed, module)
    if resource_type == "aws_iam_role":
        inline = [
            facts
            for block in _as_list(body.get("inline_policy"))
            if isinstance(block, dict)
            and (facts := policy_facts(block.get("policy"), parsed, module))
        ]
        if inline:
            details = {**(details or {}), "inline_policies": inline}
    return details
