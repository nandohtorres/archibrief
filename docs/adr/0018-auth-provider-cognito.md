# ADR 0018: Auth Provider — Amazon Cognito

**Status:** Accepted (2026-09-03) — **amended by
[ADR-0042](0042-minor-amendments-batch.md)** (2026-09-03): Cognito
choice stands; specifies user-pool-only (not identity-pool AWS-credential
issuance) with server-side token/role validation. **Superseded by
[ADR-0044](0044-no-user-accounts-admin-pre-shared-credential.md)**
(2026-09-11): no user accounts, so no auth provider needed — Cognito is
dropped entirely in favor of a single pre-shared admin credential.

## Context

Weighed Cognito vs. Clerk vs. Auth0 for the real-accounts path locked in
ADR-0010. Research showed Cognito trails Clerk/Auth0 on developer
experience specifically (documented friction: clunky hosted UI, poor
docs) — it is not the "best" choice on UX grounds. It is, however,
AWS-native (billed on the AWS account, deep IAM integration) and widely
used in AWS-centric/enterprise/gov contexts and AWS reference
architectures.

## Decision

**Amazon Cognito**, chosen deliberately for AWS-native IAM integration
over Clerk's superior DX — accepting Cognito's rough edges in exchange
for identity living in the same account, IAM model, and bill as
everything else.

## Consequences

- Expect real friction during implementation (documented weakness, not
  a surprise) — budget extra time relative to a Clerk-based build.
