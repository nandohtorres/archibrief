// Stakeholder Brief (ADR-0062): the business view of a review.
//
// Presentation only. Severity, finding IDs, evidence and the stored record
// are never changed here; this module decides how a finding is explained
// to a reader without AWS expertise. Text is curated per finding type
// ("concern") and reviewed by hand. The model never writes it, and the
// model's own analogies stored in older reports are not shown.
//
// Works for every backend and report generation: the concern comes from
// the stored record, from the new backend's `brief` block, or from an
// older backend's (or demo sidecar's) stakeholder card. No money is shown:
// commitment is a qualitative tier, never a price.

import type { BriefMeta, Finding, ReportFinding, ReviewReport, Severity } from "./contracts";
import { assessmentFor, compareAssessments } from "./assessment";
import { declarationScopeMessage, qualityMessage, scopeMessage } from "./analysis-quality";
import { fieldWithoutMoney as withoutMoney } from "./money-policy";

export const PRESENTATION_VERSION = "stakeholder-brief@2026-11-15";

export type Tier = "light" | "moderate" | "major" | "needs-scoping";

export const TIER_LABELS: Record<Tier, string> = {
  light: "$ Light",
  moderate: "$$ Moderate",
  major: "$$$ Major",
  "needs-scoping": "Needs scoping",
};

// Read beside every tier. The symbols are qualitative labels, not amounts.
export const TIER_LEGEND = "Typical overall commitment, not a quote or a verified estimate.";

export const TIER_EXPLANATIONS: Record<Tier, string> = {
  light:
    "A bounded change to existing settings or permissions, plus the routine care to keep it in place. Not free and not risk-free: it still needs testing and can interrupt service if done carelessly.",
  moderate:
    "New parts to set up and look after, or a planned switch-over that needs coordination and a maintenance window.",
  major:
    "Standing equipment or a redesign that keeps costing time and attention for as long as it runs.",
  "needs-scoping":
    "The evidence does not support a typical size yet. Someone who knows the system needs to scope it.",
};

export const SAFETY_SENTENCE =
  "These changes reduce specific risks. They do not make the system completely safe.";

export type SceneKey =
  | "gate-rule"
  | "missing-latch"
  | "open-store"
  | "listed-address"
  | "entrance-check"
  | "logbook"
  | "sealed-logbook"
  | "key-list"
  | "standby-barn"
  | "dated-copies"
  | "removal-interlock"
  | "order-intake"
  | "failed-tray"
  | "sealed-records"
  | "covered-transport";

export type Principle =
  | "Defense in depth"
  | "Least privilege"
  | "Confidentiality"
  | "Integrity"
  | "Availability"
  | "Monitoring";

export interface BriefEntry {
  title: string;
  // One or two sentences, farm world. null: no fair comparison exists, so
  // the card is plain words only.
  analogy: string | null;
  scene: SceneKey | null;
  risk: string;
  work: string;
  prevents: string;
  stillExposed: string;
  // null: honestly unclassified (no supported typical size).
  tier: Tier | null;
  biggerIf?: string;
  principle: Principle;
}

// Every concern the rule engine, Trivy trusted checks and configuration
// checks can emit. tests/frontend/stakeholder-brief.test.ts reads the
// backend catalogs and fails if one is missing here.
export const BRIEF_ENTRIES: Record<string, BriefEntry> = {
  api_route_no_authorization: {
    title: "An API route has no gateway authorization check",
    analogy: null,
    scene: null,
    risk: "The plans explicitly set authorization to NONE on this route. The application or network may still check access; this does not prove private data is public.",
    work: "Confirm this route is meant to be public. Otherwise add the right access check and test allowed and blocked requests.",
    prevents: "Requests using this route without the intended gateway authorization check.",
    stillExposed: "Application flaws, stolen credentials and access allowed by other routes.",
    tier: "needs-scoping",
    biggerIf: "the change affects existing clients, publishers or access that the service needs.",
    principle: "Least privilege",
  },
  messaging_public_publish: {
    title: "A messaging policy allows anyone to send messages",
    analogy: null,
    scene: null,
    risk: "The plans allow anyone to send to a queue or publish to a topic without a policy condition. Other effective controls may still block requests.",
    work: "Confirm whether public sending is intended. Limit publishers to trusted identities or service sources and test the change.",
    prevents: "Untrusted messages accepted through this public permission.",
    stillExposed: "Bad messages from trusted publishers and permissions granted elsewhere.",
    tier: "needs-scoping",
    biggerIf: "the change affects existing clients, publishers or access that the service needs.",
    principle: "Least privilege",
  },
  iam_administrator_access_attachment: {
    title: "An identity is assigned the broad AdministratorAccess policy",
    analogy: null,
    scene: null,
    risk: "The plans attach an AWS policy granting broad administrative permissions. Boundaries, organization policies and explicit denies may limit effective access.",
    work: "Confirm why administrative access is needed. Replace it with narrower permissions where possible, testing required work before removing access.",
    prevents: "Operations allowed only by unnecessary administrative permissions.",
    stillExposed: "Misuse of permissions that remain and access granted through other identities.",
    tier: "needs-scoping",
    biggerIf: "the change affects existing clients, publishers or access that the service needs.",
    principle: "Least privilege",
  },
  cloudfront_plain_http: {
    title: "A website delivery setting accepts unencrypted connections",
    analogy: null,
    scene: null,
    risk: "A CloudFront behavior in the plans allows plain HTTP. Visitors may already use HTTPS, but this setting does not require it.",
    work: "Check client compatibility, then redirect affected requests to HTTPS or require HTTPS and test the change.",
    prevents: "Unencrypted viewer connections accepted by the affected behavior.",
    stillExposed: "Application attacks and the separate connection from CloudFront to its origin.",
    tier: "needs-scoping",
    biggerIf: "the change affects existing clients, publishers or access that the service needs.",
    principle: "Confidentiality",
  },
  database_literal_password: {
    title: "A database password is written directly in the plans",
    analogy: null,
    scene: null,
    risk: "A database password field contains a literal value. If it is a real credential, people with access to these files or copies could learn it. The value is withheld here.",
    work: "Use managed credentials or an approved secret source. Rotate a real exposed credential and check access to source history and state.",
    prevents: "Future direct storage of this credential in the configuration.",
    stillExposed:
      "Copies already made, old credentials until rotated, and access to state or the secret source.",
    tier: "needs-scoping",
    biggerIf: "the change affects existing clients, publishers or access that the service needs.",
    principle: "Confidentiality",
  },

  s3_public_access: {
    title: "The plans don't show all of a storage bucket's public-access blocks turned on",
    analogy:
      "The plans don't show the feed store's second latch fitted, the one that stops it being propped open to the road by mistake. Other locks may still hold.",
    scene: "missing-latch",
    risk: "The plans don't show all four of AWS's public-access blocks turned on for this bucket. If they are really off, one later permission mistake could make its files public. An account-wide block, which the code doesn't show, may already cover it. We did not find that the files are public now.",
    work: "Confirm whether an account-wide block applies. If not, turn on the bucket's public-access blocks and check that no intended public sharing depends on them being off.",
    prevents:
      "Files becoming public through a bucket policy or sharing setting added later by mistake.",
    stillExposed:
      "People and systems that already have legitimate access can still read or misuse the files.",
    tier: "light",
    biggerIf:
      "the bucket really is meant to serve the public, which needs a different, deliberate design.",
    principle: "Confidentiality",
  },
  s3_public_policy: {
    title: "A storage bucket's policy is written to let anyone in",
    analogy:
      "A sign on the feed store door says anyone may come in. The plans say so; another lock may override the sign, and we did not check who has walked in.",
    scene: "open-store",
    risk: "The bucket policy in the plans allows some actions to anyone, with no condition limiting who. Unless another setting blocks it, such as an account-wide public-access block the code doesn't show, whoever finds the bucket could do what the policy allows.",
    work: "Remove the public permission and grant access only to the people and services that need it.",
    prevents: "Strangers using the bucket through that policy.",
    stillExposed: "Misuse by anyone who is still allowed in, and copies already taken, if any.",
    tier: "light",
    biggerIf: "applications or partners rely on the public access and must move to another route.",
    principle: "Confidentiality",
  },
  sg_open_ingress: {
    title: "A firewall rule lets the whole internet reach sensitive ports",
    analogy:
      "The rule on a service gate says visitors from any address may knock. We have not confirmed whether there is a usable road to that gate.",
    scene: "gate-rule",
    risk: "A firewall rule in the plans allows the whole internet to reach database or admin ports. Whether anything can really be reached also depends on what the rule is attached to and on network routes, which this check doesn't follow. Automated scanners try such ports constantly.",
    work: "Limit those ports to your own network or the specific services that need them, and check that legitimate users keep access.",
    prevents: "Outsiders even attempting a connection to those ports through this rule.",
    stillExposed: "Attackers coming through another allowed route, or using stolen staff access.",
    tier: "light",
    biggerIf: "people or systems outside your network depend on reaching those ports directly.",
    principle: "Defense in depth",
  },
  sg_admin_ingress: {
    title: "A firewall rule opens remote admin login to the whole internet",
    analogy:
      "The staff gate is set to let anyone knock. We haven't confirmed whether outsiders can reach it.",
    scene: "gate-rule",
    risk: "A firewall rule in the plans opens remote administration (SSH or RDP) to the whole internet. If the rule is attached to a reachable server, attackers can try passwords and known flaws on it; they do this all day. Routing and whether a server is listening were not checked.",
    work: "Close the open rule and give staff a controlled way in, such as AWS Systems Manager Session Manager, then confirm they still have access.",
    prevents: "Outsiders reaching the admin login at all through this rule.",
    stillExposed: "Someone who has stolen a staff login, and any other open route.",
    tier: "light",
    biggerIf: "staff have no other way in today and a new access route must be set up first.",
    principle: "Defense in depth",
  },
  subnet_public_ip: {
    title: "New servers in a network get a public address by default",
    analogy:
      "Every new barn built in this field gets its own address on the public road, unless someone remembers to say otherwise.",
    scene: "listed-address",
    risk: "This is a default for servers launched later, not proof that one is exposed now. A server meant to be internal could get a public address without anyone choosing it; whether it is then reachable depends on other network rules.",
    work: "Turn the default off and give public addresses only to the servers that need one.",
    prevents: "Internal servers getting a public address without anyone choosing it.",
    stillExposed: "Servers given a public address on purpose, and other routes into the network.",
    tier: "light",
    biggerIf:
      "existing servers rely on their public address and need another way to reach the internet.",
    principle: "Defense in depth",
  },
  rds_public: {
    title: "The database is set to have a public internet address",
    analogy:
      "The herd's barn is listed on the public road's map. The fences may still keep visitors out; the listing makes it easier to try.",
    scene: "listed-address",
    risk: "The plans give the database a public address. Other network controls may still block outside access; we did not confirm either way.",
    work: "Make the database private, reach it only from inside the network, and check every application that connects to it.",
    prevents: "Direct connection attempts on the database from the internet.",
    stillExposed:
      "Weak or stolen database logins used from inside, and access the applications already have.",
    tier: "light",
    biggerIf:
      "people or services connect to the database from outside today and need a new private route.",
    principle: "Confidentiality",
  },
  rds_multi_az: {
    title: "The plans don't show a standby copy of the database in a second location",
    analogy:
      "The plans show the milking done in one barn, with no standby barn in another field. A standby could keep things going if the first barn is cut off.",
    scene: "standby-barn",
    risk: "The plans don't show Multi-AZ turned on for this database. If it really runs in one Availability Zone, a problem in that data center could take the database, and the applications that use it, down until AWS recovers it.",
    work: "Confirm how the database runs today. If it has no standby, turn on a managed standby in a second Availability Zone, plan the switch-over, and test a failover.",
    prevents: "A long database outage when one data center fails.",
    stillExposed:
      "Mistakes or bad data, which the standby copies too, and region-wide outages. A standby is not a backup.",
    tier: "major",
    biggerIf:
      "the database is very large or busy, which makes both the switch-over and the running commitment bigger.",
    principle: "Availability",
  },
  placement_single_az: {
    title: "Several copies of a part of the system share one location",
    analogy:
      "The herd is split into several pens, but all the pens are in the same field. If that field floods, every pen is affected.",
    scene: "standby-barn",
    risk: "The plans place several instances in one Availability Zone, so one zone failure could affect them all. Having several copies alone doesn't spread the risk.",
    work: "Spread the intended copies across Availability Zones and test that the system keeps working when one zone is lost.",
    prevents: "One data-center failure taking out every copy at once.",
    stillExposed:
      "Faults that affect every copy, such as bad releases or data errors. Placement does not guarantee recovery time.",
    tier: "moderate",
    biggerIf: "the copies hold state that must stay in step across locations.",
    principle: "Availability",
  },
  dynamodb_pitr: {
    title: "The plans don't show a way to rewind a table to before a mistake",
    analogy:
      "The plans show the herd records kept in one book with no dated copies. If a page is spoiled, there may be no earlier version to go back to.",
    scene: "dated-copies",
    risk: "Point-in-time recovery isn't shown turned on in the plans. If it is really off, a bad release or script that corrupts the table could not be undone that way. Other backups, such as AWS Backup plans set up outside this code, were not reviewed.",
    work: "Confirm what recovery the table has. If none covers this, turn on point-in-time recovery, which keeps up to 35 days of restorable history, and practise a restore.",
    prevents: "Losing the table's data to an accidental change within the recovery window.",
    stillExposed: "Mistakes noticed after the window, and other recovery needs we did not review.",
    tier: "light",
    biggerIf: "the table is very large, which raises the ongoing storage commitment.",
    principle: "Availability",
  },
  s3_versioning: {
    title: "The plans don't show earlier versions of files being kept",
    analogy:
      "The plans show each paper in the records room replaced when it changes, with no dated copies kept.",
    scene: "dated-copies",
    risk: "Versioning isn't shown turned on in the plans. If it is really off, a mistake, a bad script or ransomware could remove files with no earlier copy in the bucket to restore. Other recovery arrangements were not reviewed.",
    work: "Confirm what recovery the bucket has. If none covers this, turn on versioning, with a rule for how long old copies are kept.",
    prevents: "Losing a file to an accidental overwrite or delete within the retention window.",
    stillExposed:
      "Someone with enough access deleting the old copies too, unless further locks are added.",
    tier: "light",
    biggerIf: "the bucket holds a lot of frequently changed data, which raises ongoing storage.",
    principle: "Availability",
  },
  versioned_retention_gap: {
    title: "A storage clean-up rule keeps old file versions with no end date",
    analogy: null,
    scene: null,
    risk: "The bucket keeps old versions, and its clean-up rule removes current files but says nothing about old versions. The plans do not show when old versions are really deleted.",
    work: "Decide how long old versions must be kept, add a matching rule, and review backups and legal holds separately.",
    prevents: "Keeping data longer, or shorter, than the retention requirement intends.",
    stillExposed: "Other copies of the data elsewhere, which this review did not cover.",
    tier: "light",
    principle: "Integrity",
  },
  rds_backup_retention: {
    title: "The plans don't show the database keeping more than a day of backups",
    analogy:
      "The plans show the herd records copied each night, with at most one night's copy kept. A mistake found two days later can't be undone from them.",
    scene: "dated-copies",
    risk: "The plans keep automated backups for a day or less, or leave the period to AWS's default, which may also be a day. A problem noticed later may not be recoverable from those backups.",
    work: "Set how long backups are kept to match how late a problem might be noticed, for example 7 days or more, and practise a restore.",
    prevents: "Losing data to a mistake that is noticed after the current window.",
    stillExposed: "Problems older than the new window, and anything outside this database.",
    tier: "light",
    biggerIf:
      "backups turn out to be switched off: turning them on can cause a short outage and needs a planned rollout.",
    principle: "Availability",
  },
  rds_deletion_protection: {
    title: "The plans don't show deletion protection on the database",
    analogy:
      "The plans show no interlock on the barn's demolition switch. An interlock is not a spare barn; it only makes removal deliberate.",
    scene: "removal-interlock",
    risk: "Deletion protection isn't shown turned on in the plans. If it is really off, one wrong command or deployment could remove the database. A final snapshot or other backup, if one is set up, might still allow a restore.",
    work: "Turn on deletion protection and make removal a deliberate, two-step change.",
    prevents: "Deleting the database by accident.",
    stillExposed: "Data damaged without deleting the database, which needs backups instead.",
    tier: "light",
    principle: "Availability",
  },
  sqs_dlq_retention: {
    title: "Failed jobs can expire before anyone looks at them",
    analogy:
      "Failed orders go into a tray for checking, but the tray throws them out sooner than the order book keeps orders, counted from when each order first came in.",
    scene: "failed-tray",
    risk: "The failed-jobs queue may not leave enough time to investigate after a job moves there. For standard queues, time already spent in the main queue counts toward expiry too.",
    work: "Allow time to investigate after the main queue's retention period; the current check allows one day. Increase failed-job retention if this fits within AWS's 14-day limit. If it cannot fit, preserve failed jobs another way or redesign the retry process, and assign someone to monitor it.",
    prevents: "Failed jobs disappearing before anyone can investigate or retry them.",
    stillExposed:
      "Failures nobody looks at, or investigations taking longer than the allowance. A holding tray is not an archive or an alert.",
    tier: "light",
    principle: "Availability",
  },
  invalid_sqs_mapping: {
    title: "A queue connection is set up in a way AWS rejects",
    analogy: null,
    scene: null,
    risk: "A function's time limit is longer than the queue's hold time. AWS refuses this setup, so the connection may not work as planned. This is not evidence of retries or extra charges.",
    work: "Set the queue's hold time at least as long as the function's time limit, then tune retries separately.",
    prevents: "A queue connection that is refused or behaves unpredictably.",
    stillExposed: "Other processing problems, which need their own checks.",
    tier: "light",
    principle: "Availability",
  },
  iam_wildcard: {
    title: "A permission policy uses wildcards that grant very broad access",
    analogy:
      "A farmhand's key list says 'every room' or 'every shed' instead of naming the rooms they need.",
    scene: "key-list",
    risk: "A policy in the plans allows every action, or whole groups of actions, on every resource. What an identity can really do also depends on who the policy is attached to and on other limits, such as permissions boundaries or organization rules, which were not reviewed. If anything using it is taken over, the attacker could get that broad access.",
    work: "Limit the permission to the specific actions and resources it really needs, and test that nothing breaks.",
    prevents: "A compromise of an identity using this policy reaching far beyond what it needs.",
    stillExposed: "Misuse of the access that remains, and other broad permissions.",
    tier: "light",
    biggerIf: "many systems share this permission and each needs its own narrower one.",
    principle: "Least privilege",
  },
  iam_trust: {
    title: "A role can be taken on by an AWS account with no extra condition",
    analogy:
      "A crew can collect the keys without quoting the job reference you agreed with them or showing a badge.",
    scene: null,
    risk: "The role's trust rule lets an AWS account, possibly another company's, take it on with no external ID, MFA or organization condition. Anyone in that account who is allowed to assume roles could use it. If it is a third party, this also leaves room for the 'confused deputy' problem, where they are tricked into acting for someone else.",
    work: "Add a condition that fits who uses the role: an external ID agreed with a third party, MFA for people, or an organization check.",
    prevents:
      "The role being used by someone in the trusted account it wasn't meant for, or through a tricked third party.",
    stillExposed: "Misuse by the trusted account itself. An external ID is not a password.",
    tier: "light",
    biggerIf: "the third party has to change how it connects.",
    principle: "Least privilege",
  },
  iam_compute_broad_managed: {
    title: "Running code is given a broad AWS-managed permission",
    analogy:
      "The delivery driver is handed keys to whole sections of the farm, not just the loading shed. A separate rule may still limit where they can go.",
    scene: "key-list",
    risk: "A server or function's role has a broad AWS-managed policy attached. If that code is taken over, the attacker could use what the policy allows, unless other limits narrow it. Some roles have a permissions boundary that does; this card does not evaluate it, and the technical finding says whether one is set.",
    work: "Find out which resources the code really uses, replace the broad policy with one that names only those, then test the code.",
    prevents: "A compromise of that code reaching unrelated resources.",
    stillExposed: "The resources the code is still allowed to use.",
    tier: "light",
    biggerIf:
      "nobody knows exactly which resources the code needs and that has to be worked out first.",
    principle: "Least privilege",
  },
  public_lambda_url: {
    title: "A side entrance to the application needs no login",
    analogy:
      "The farm has a side gate that skips the front desk, and its rule says anyone may come through. We did not see whether anyone uses it.",
    scene: "gate-rule",
    risk: "A function has its own web address that accepts calls from anyone, even if the main entrance asks for a login. The plans don't show whether the address is in use.",
    work: "Remove the extra address if nobody needs it, or require signed requests from named callers, keeping a tested route for them.",
    prevents: "Strangers running the function through that address.",
    stillExposed: "Flaws in the function itself, reached through its approved routes.",
    tier: "light",
    biggerIf: "outside callers depend on the address and need a new authenticated route.",
    principle: "Defense in depth",
  },
  ec2_imdsv2: {
    title: "A server isn't required to use the safer way of handing out its access keys",
    analogy: null,
    scene: null,
    risk: "The plans don't require the newer token-based method (IMDSv2) on this server. Unless the server image or an account setting the code doesn't show requires it, the older method stays available, and a common web flaw can trick the server into revealing its AWS keys.",
    work: "Require the newer token-based method (IMDSv2) and check that the software on the server still works.",
    prevents: "That trick for stealing the server's keys.",
    stillExposed:
      "Other ways of taking over the server, and what its keys allow if stolen another way.",
    tier: "light",
    biggerIf: "older software on the server only supports the old method.",
    principle: "Confidentiality",
  },
  lambda_concurrency: {
    title: "The plans don't set a limit on how many copies of a function run at once",
    analogy:
      "The farm takes every feed order the moment it arrives; only the county's overall limit caps how many are handled at once.",
    scene: "order-intake",
    risk: "The plans don't set a limit for this function, so only the account-wide limit applies. A traffic spike, bug or abuse could run many copies at once, running up usage and starving other functions in the account.",
    work: "Set a limit that fits the expected traffic, and watch for requests being turned away.",
    prevents: "One function using up the account's capacity or running away with usage.",
    stillExposed: "Real demand above the limit being turned away; the limit has to be sized well.",
    tier: "light",
    principle: "Availability",
  },
  apigw_throttling: {
    title: "The plans don't set request limits for the API",
    analogy:
      "The farm gate takes deliveries at whatever pace they arrive, unless a limit is set somewhere the plans don't show. The county-wide traffic limit still applies.",
    scene: "order-intake",
    risk: "The plans set no request limits for this API's stages. Limits may be set in a usage plan or outside this code; if not, only AWS's account-wide default applies, and a flood of requests could crowd out other APIs or run up usage.",
    work: "Confirm whether limits exist elsewhere. If not, set request rate and burst limits on the API.",
    prevents: "One API, or one caller, overwhelming the rest.",
    stillExposed: "Determined attacks spread across many sources, which need other protections.",
    tier: "light",
    principle: "Availability",
  },
  cloudtrail_present: {
    title: "The plans don't set up a long-term record of account activity",
    analogy:
      "The plans show no gate logbook for the farm. One may be kept elsewhere; confirm that before starting another.",
    scene: "logbook",
    risk: "The submitted code has no CloudTrail trail. AWS keeps 90 days of account changes by default, but nothing older, and file-level access isn't recorded. A trail may exist outside this code.",
    work: "If no trail exists yet, set one up that writes to a locked-down bucket, and decide who reviews it.",
    prevents: "Investigations coming up short because the record ran out.",
    stillExposed:
      "Misuse itself: a record helps find out what happened, it doesn't stop it, and only if someone reads it.",
    tier: "moderate",
    principle: "Monitoring",
  },
  cloudtrail_log_validation: {
    title: "The plans don't show tamper checks on the activity record",
    analogy:
      "The plans don't show the gate logbook's pages numbered and sealed, so a changed page might go unnoticed.",
    scene: "sealed-logbook",
    risk: "Log file validation isn't shown turned on for this trail. If it is really off, an intruder who reaches the log files could change or remove them without that being detectable.",
    work: "Turn on log file validation for the trail.",
    prevents: "Undetected tampering with the stored activity record.",
    stillExposed: "Activity that was never recorded, and logs nobody checks.",
    tier: "light",
    principle: "Integrity",
  },
  apigw_access_logging: {
    title: "The plans don't show a record of requests to the API",
    analogy: "The plans show no logbook at the delivery gate for who came and what they asked for.",
    scene: "logbook",
    risk: "Access logging isn't shown turned on for this API stage. If it is really off, there would be no record of what was called and by whom when an incident or complaint needs looking into.",
    work: "Turn on access logging with a set retention period, and decide who looks at it.",
    prevents: "Investigations with no record to work from.",
    stillExposed: "The requests themselves: logs record, they don't block.",
    tier: "moderate",
    principle: "Monitoring",
  },
  cloudfront_logging: {
    title: "The plans don't show a visitor record at the website's front door",
    analogy:
      "The plans show no logbook at the customer entrance, so after a problem nobody may be able to say who came through.",
    scene: "logbook",
    risk: "Standard logging isn't shown turned on for this CloudFront distribution. Logging may be set up another way the plans don't show; if there is none, attacks and outages are harder to investigate afterwards.",
    work: "Confirm whether logs are collected another way. If not, turn on CloudFront logging to a log bucket with a retention rule.",
    prevents: "Investigations with no record of website traffic.",
    stillExposed: "The traffic itself: logs record, they don't block.",
    tier: "moderate",
    principle: "Monitoring",
  },
  cloudfront_waf: {
    title: "The plans don't show a firewall screening website requests",
    analogy:
      "Customers need the front entrance. The plans show no checkpoint at that entrance screening what comes in.",
    scene: "entrance-check",
    risk: "No web application firewall is attached to this CloudFront distribution in the plans. One may be applied by another tool the plans don't show; if there is none, common web attacks and bot traffic reach the systems behind it unscreened.",
    work: "Attach an AWS WAF web ACL with managed rule groups, then tune it and keep it maintained.",
    prevents: "Requests that match the configured rules, at this entrance.",
    stillExposed:
      "Traffic that doesn't come through this entrance, flaws in the application itself, and weak sign-in. A firewall screens requests; it does not fix the system behind it.",
    tier: "moderate",
    principle: "Defense in depth",
  },
  lambda_secret_env: {
    title: "A function's settings have a name that suggests a password or key",
    analogy: null,
    scene: null,
    risk: "A setting on the function is named like a secret (ending in _KEY, _SECRET, _TOKEN or _PASSWORD). If it holds a real secret, anyone who can view the function's settings can read it. We only checked the name: it may hold a reference to a secret rather than the secret itself.",
    work: "Move real secrets to AWS Secrets Manager, have the function read them at start-up, and replace any secret that was exposed.",
    prevents: "Secrets being read by people who can view function settings.",
    stillExposed: "Misuse by the function itself, or by anyone allowed to read the secret store.",
    tier: "moderate",
    principle: "Confidentiality",
  },
  s3_encryption: {
    title: "The code doesn't choose how stored files are encrypted",
    analogy: null,
    scene: null,
    risk: "S3 encrypts new files by default, so this does not mean the files are unencrypted; files written before 2023 may need checking. The code doesn't choose or record a key, so it doesn't show whether access to sensitive files is limited through the key.",
    work: "Confirm the key arrangement the data needs and declare it in the code.",
    prevents: "Unclear or uncontrolled decryption of sensitive files.",
    stillExposed: "Anyone with read access: encryption at rest does not stop an authorized read.",
    tier: "light",
    biggerIf:
      "a customer-managed key is required, which adds a key to look after and permissions to update.",
    principle: "Confidentiality",
  },
  ebs_encryption: {
    title: "The plans don't ask for a storage disk to be encrypted",
    analogy: null,
    scene: null,
    risk: "The disk is not marked as encrypted in the plans. An account-wide default may still encrypt it; that setting is not visible in the code. If it is not encrypted, a copied disk or snapshot could be read.",
    work: "Confirm the account default. If needed, copy the disk to an encrypted one and switch over in a planned window.",
    prevents: "Copied disks or snapshots being readable.",
    stillExposed:
      "Anyone who can use the running server: encryption at rest does not stop an authorized read.",
    tier: "moderate",
    biggerIf: "many disks or busy servers need switching over.",
    principle: "Confidentiality",
  },
  rds_encryption: {
    title: "The plans don't turn on encryption for the database's storage",
    analogy:
      "The plans don't show the herd records' cabinet sealed. Sealing protects copies taken away, not someone reading at the desk.",
    scene: "sealed-records",
    risk: "Storage encryption isn't shown turned on for this database in the plans. If it is really off, a copied backup or snapshot could be read by whoever has it.",
    work: "Confirm whether storage is encrypted. If not, restore an encrypted copy of the database and switch the applications over in a planned window.",
    prevents: "Copied storage, backups or snapshots being readable.",
    stillExposed:
      "Anyone with database access: encryption at rest does not stop an authorized read.",
    tier: "moderate",
    biggerIf: "the database is large or can't be paused, which makes the switch-over bigger.",
    principle: "Confidentiality",
  },
  sns_encryption: {
    title: "The plans don't choose an encryption key for a notification topic",
    analogy: "The plans don't show a seal on the tray where messages wait for delivery.",
    scene: "sealed-records",
    risk: "Encryption with a key isn't shown turned on for this notification topic. If it is really off, messages waiting for delivery aren't protected by a key you control, and audits that require one can fail.",
    work: "Turn on encryption for the topic with a suitable key and check that senders and receivers still work.",
    prevents: "Stored messages being readable without permission to use the key.",
    stillExposed:
      "Anyone allowed to read the messages: encryption at rest does not stop an authorized read.",
    tier: "light",
    biggerIf:
      "a customer-managed key is required, which adds a key to look after and permissions to update.",
    principle: "Confidentiality",
  },
  rds_force_ssl: {
    title: "The database accepts connections that aren't encrypted",
    analogy:
      "Records can travel between the barn and the office in an open cart instead of a covered one.",
    scene: "covered-transport",
    risk: "The database settings explicitly allow unencrypted connections, so passwords and data could cross the network readable by someone able to watch that traffic.",
    work: "Turn on the setting that refuses unencrypted connections, after checking every application can connect securely.",
    prevents: "Data and passwords being read in transit on the network.",
    stillExposed: "Stolen logins and misuse by connected applications.",
    tier: "light",
    biggerIf: "some applications can't use encrypted connections yet and need updating first.",
    principle: "Confidentiality",
  },
  lb_tls_policy: {
    title: "The website's entrance still accepts old, weak encryption",
    analogy: "The covered cart still accepts an old latch that is known to be easy to open.",
    scene: "covered-transport",
    risk: "The load balancer allows older encryption versions with known weaknesses, which standards such as PCI DSS no longer allow.",
    work: "Switch the load balancer to a modern TLS 1.2+ policy, after checking which clients would be affected.",
    prevents: "Connections being pushed down to weak encryption.",
    stillExposed: "Flaws in the application behind the load balancer.",
    tier: "light",
    biggerIf: "important clients only support old encryption versions.",
    principle: "Confidentiality",
  },
  nat_single: {
    title: "One network exit serves several parts of the system",
    analogy: null,
    scene: null,
    risk: "The plans have one NAT gateway for several subnets. The rule counts gateways and subnets; it does not establish their zones or which systems depend on that exit. If they do depend on it, one failure could cut them off from the internet and outside services.",
    work: "Confirm which systems use the exit and from which zones, then decide between an exit per zone and private connections to the AWS services in use.",
    prevents:
      "One gateway failure cutting off every dependent system, if that dependency is confirmed.",
    stillExposed: "Outages of the outside services themselves, and anything this rule cannot see.",
    tier: "needs-scoping",
    principle: "Availability",
  },
};

// What the rule's evidence actually establishes, kept apart from the
// analogy. The rules fire on a setting that is left out, set the other way,
// or set from a value the files don't include, and the finding does not
// record which (backend/lambdas/rule_engine/handler.py uses `not truthy()`),
// so the wording for those concerns is conditional throughout.
export type EvidenceState = "declared" | "not-shown" | "absent" | "derived" | "name-match";

export const EVIDENCE_STATE_LABELS: Record<EvidenceState, string> = {
  declared: "Set this way in the submitted plans. The live account was not checked.",
  "not-shown":
    "The submitted files don't show the safer setting. It may be left out, set the other way, or depend on a value the files don't include; an account default or another tool may also set it. The live account was not checked.",
  absent:
    "No such resource is in the submitted code. It may be managed elsewhere, such as by another team or account.",
  derived:
    "Worked out from how several settings in the submitted plans fit together, using AWS defaults where a value is left out. The live account was not checked.",
  "name-match": "Matched by a setting's name only. Its value was not checked.",
};

const EVIDENCE_STATES: Record<string, EvidenceState> = {
  cloudtrail_present: "absent",
  lambda_secret_env: "name-match",
  placement_single_az: "derived",
  invalid_sqs_mapping: "derived",
  versioned_retention_gap: "derived",
  nat_single: "derived",
  public_lambda_url: "derived",
  sqs_dlq_retention: "derived",
  iam_compute_broad_managed: "derived",
  ...Object.fromEntries(
    [
      "s3_public_access",
      "s3_encryption",
      "s3_versioning",
      "sns_encryption",
      "ebs_encryption",
      "rds_encryption",
      "rds_multi_az",
      "rds_deletion_protection",
      "rds_backup_retention",
      "dynamodb_pitr",
      "cloudtrail_log_validation",
      "apigw_access_logging",
      "apigw_throttling",
      "cloudfront_logging",
      "cloudfront_waf",
      "ec2_imdsv2",
      "lambda_concurrency",
    ].map((concern) => [concern, "not-shown" as const]),
  ),
};

export function evidenceStateFor(concern: string): EvidenceState {
  return EVIDENCE_STATES[concern] ?? "declared";
}

// The curated text applies only to a deterministic rule finding whose
// concern is recorded, sent by the backend or carried by a legacy card.
// Model and reviewer findings never get it (briefCardFor).
export type ConcernSource = "recorded" | "title" | "sidecar";

export type BriefCard =
  | {
      kind: "curated";
      concern: string;
      concernSource: ConcernSource;
      entry: BriefEntry;
      subject: string | null;
    }
  | {
      kind: "summary";
      writtenBy: "model" | "reviewer";
      title: string;
      summary: string;
      action: string;
      moneyRemoved: boolean;
    }
  | {
      kind: "technical";
      title: string;
      risk: string;
      action: string;
      notObservable: boolean;
      moneyRemoved: boolean;
    };

// ---- Monetary text policy --------------------------------------------------
// Lives in money-policy.ts (shared rules with the backend). Re-exported so
// callers of the brief have one import.
export {
  AMOUNT_PLACEHOLDER,
  MONEY_NOTE,
  fieldWithoutMoney as withoutMoney,
  narrativeWithoutMoney,
} from "./money-policy";

// ---- Card derivation -------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function concernFor(finding: ReportFinding): { concern: string; source: ConcernSource } | null {
  const { record } = finding;
  if (record.type !== "deterministic-rule-result") return null;
  if (typeof record.concern === "string" && record.concern) {
    return { concern: record.concern, source: "recorded" };
  }
  const meta: BriefMeta | undefined = finding.brief;
  if (meta && meta.version === 2 && typeof meta.concern === "string" && meta.concern) {
    return {
      concern: meta.concern,
      source: meta.concern_source === "recorded" ? "recorded" : "title",
    };
  }
  // Older backends and demo sidecars carry the concern on their card.
  const legacy = finding.stakeholder?.concern;
  if (typeof legacy === "string" && legacy) return { concern: legacy, source: "sidecar" };
  return null;
}

function subjectFor(finding: ReportFinding): string | null {
  const subject = finding.brief?.subject ?? finding.stakeholder?.subject ?? null;
  if (typeof subject === "string" && subject) return subject;
  const match = /'([^']{1,80})'/.exec(finding.record.finding);
  return match ? match[1] : null;
}

// The plain block the model (or a reviewer, for demos) wrote. Only its
// summary fields are read: never its analogy, price items or effort.
function writtenSummary(
  finding: ReportFinding,
): { writtenBy: "model" | "reviewer"; title: string; summary: string; action: string } | null {
  const plain = (finding.record as Finding).plain;
  const candidates: unknown[] = [plain, finding.stakeholder];
  for (const candidate of candidates) {
    if (!isRecord(candidate)) continue;
    const by = candidate.written_by ?? candidate.source;
    if (by !== "model" && by !== "reviewer") continue;
    const { title, what_could_happen: summary, action } = candidate;
    if (typeof title === "string" && typeof summary === "string" && typeof action === "string") {
      return { writtenBy: by, title, summary, action };
    }
  }
  return null;
}

export function briefCardFor(finding: ReportFinding): BriefCard {
  const resolved = concernFor(finding);
  const entry = resolved ? BRIEF_ENTRIES[resolved.concern] : undefined;
  if (resolved && entry) {
    return {
      kind: "curated",
      concern: resolved.concern,
      concernSource: resolved.source,
      entry,
      subject: subjectFor(finding),
    };
  }
  const written =
    finding.record.type === "deterministic-rule-result" ? null : writtenSummary(finding);
  if (written) {
    const title = withoutMoney(written.title);
    const summary = withoutMoney(written.summary);
    const action = withoutMoney(written.action);
    return {
      kind: "summary",
      writtenBy: written.writtenBy,
      title: title.text,
      summary: summary.text,
      action: action.text,
      moneyRemoved: title.removed + summary.removed + action.removed > 0,
    };
  }
  const title = withoutMoney(finding.record.finding);
  const risk = withoutMoney(finding.record.risk_impact);
  const action = withoutMoney(finding.record.recommendation);
  return {
    kind: "technical",
    title: title.text,
    risk: risk.text,
    action: action.text,
    notObservable: finding.record.type === "not-observable",
    moneyRemoved: title.removed + risk.removed + action.removed > 0,
  };
}

// Tier for a card. Model and reviewer-written findings always need
// scoping; an unmatched or not-observable finding stays unclassified.
export function tierFor(card: BriefCard): Tier | null {
  if (card.kind === "curated") return card.entry.tier;
  if (card.kind === "summary") return "needs-scoping";
  return null;
}

export function cardTitle(card: BriefCard): string {
  return card.kind === "curated" ? card.entry.title : card.title;
}

export const SOURCE_LABELS = {
  curated: "Standard explanation for this kind of finding, reviewed by hand.",
  model:
    "Plain summary written by the AI from this finding. It is not a verified explanation; check the technical evidence.",
  reviewer: "Plain summary written by hand for this demo.",
  technical:
    "No plain-language explanation exists for this finding, so its technical text is shown.",
  notObservable: "ArchiBrief could not check this from the submitted material.",
};

// ---- The brief as a whole --------------------------------------------------

export interface BriefRow {
  finding: ReportFinding;
  card: BriefCard;
}

export interface BriefModel {
  // Needs a decision, most serious first, then findings with no assessment.
  rows: BriefRow[];
  // Explicit no-action assessments, shown collapsed.
  noAction: BriefRow[];
  severityCounts: Record<Severity, number>;
  unassessedCount: number;
}

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

export function buildBrief(report: ReviewReport): BriefModel {
  const toRow = (finding: ReportFinding): BriefRow => ({ finding, card: briefCardFor(finding) });
  // Array.prototype.sort is stable, so equal assessments keep report order.
  const ordered = [...report.findings].sort(compareAssessments);
  const rows = ordered.filter((f) => assessmentFor(f).action !== "none").map(toRow);
  const noAction = ordered.filter((f) => assessmentFor(f).action === "none").map(toRow);
  const severityCounts = Object.fromEntries(SEVERITIES.map((s) => [s, 0])) as Record<
    Severity,
    number
  >;
  let unassessedCount = 0;
  for (const { finding } of rows) {
    const severity = assessmentFor(finding).severity;
    if (severity) severityCounts[severity] += 1;
    else unassessedCount += 1;
  }
  return { rows, noAction, severityCounts, unassessedCount };
}

// The coverage statement shown near the top. A report with no recorded
// scope must not read as complete coverage.
export interface BriefCoverage {
  headline: string;
  details: string[];
}

export function briefCoverage(report: ReviewReport): BriefCoverage {
  const scope = report.review_scope;
  const recorded = !!scope && scope.version === "review-scope-public@1" && scope.known_y !== null;
  const headline = recorded
    ? `ArchiBrief read the submitted Terraform and workload brief, not the live AWS account. ${
        scope.count_complete ? "" : "Its count of the system's parts is partial. "
      }Coverage details are below.`
    : "ArchiBrief read the submitted Terraform and workload brief, not the live AWS account. This report was saved before ArchiBrief recorded review scope, so it covers only the findings listed and cannot show what was left out. Do not read it as complete coverage.";
  const details = [declarationScopeMessage(scope), qualityMessage(report.analysis_quality)];
  if (report.analysis_scope) details.push(scopeMessage(report.analysis_scope));
  for (const answer of report.baseline_answers) {
    if (answer.outcome === "assumption") {
      details.push(`${answer.label} was not supplied, so a cautious assumption was used.`);
    } else if (answer.outcome !== "answered") {
      details.push(
        `${answer.label} was not supplied, so conclusions that depend on it can't be drawn.`,
      );
    }
  }
  return { headline, details };
}

// Which protection jobs this report touches, for the optional explainer.
// "No finding" never means "in place".
export interface ProtectionJob {
  name: string;
  job: string;
  status: string;
}

const JOB_CONCERNS: Record<string, string[]> = {
  gates: [
    "sg_open_ingress",
    "sg_admin_ingress",
    "rds_public",
    "subnet_public_ip",
    "public_lambda_url",
    "s3_public_policy",
    "s3_public_access",
  ],
  screening: ["cloudfront_waf"],
  records: [
    "cloudtrail_present",
    "cloudtrail_log_validation",
    "apigw_access_logging",
    "cloudfront_logging",
  ],
};

export function protectionJobs(model: BriefModel): ProtectionJob[] {
  const concerns = new Set(
    [...model.rows, ...model.noAction]
      .map(({ card }) => (card.kind === "curated" ? card.concern : null))
      .filter((c): c is string => c !== null),
  );
  const status = (key: string, unchecked: string) =>
    JOB_CONCERNS[key].some((c) => concerns.has(c))
      ? "This report has a finding about it."
      : unchecked;
  return [
    {
      name: "Gate rules",
      job: "Decide who may even knock: firewall rules, public addresses and access permissions.",
      status: status(
        "gates",
        "No finding in this report. That does not prove the gates are set well.",
      ),
    },
    {
      name: "Traffic inspection",
      job: "Inspects traffic moving through the network, like a guard checking loads on the farm road.",
      status: "Not assessed by this review.",
    },
    {
      name: "Web-request screening",
      job: "A checkpoint at the customer entrance that screens web requests. It guards that entrance, not the whole system.",
      status: status(
        "screening",
        "No finding in this report. This review only checks it for CloudFront distributions.",
      ),
    },
    {
      name: "Activity records",
      job: "A logbook of who did what. It helps find out what happened; it doesn't stop anything.",
      status: status("records", "No finding in this report. That does not prove records are kept."),
    },
  ];
}
