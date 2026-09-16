from datetime import datetime, timezone

from backend.corpus.models import Block, BlockKind
from backend.corpus.normalize_pdf import _segment_blocks, normalize_pdf

from .fixtures import (
    build_sample_pdf_bytes,
    build_sample_pdf_bytes_with_a_broken_entry_between_valid_siblings,
    build_sample_pdf_bytes_with_a_far_apart_gap,
    build_sample_pdf_bytes_with_bullet_list,
    build_sample_pdf_bytes_with_same_depth_siblings_sharing_a_page,
    build_sample_pdf_bytes_with_shared_page,
)

# Real text extracted (pypdf plain-mode) from the "Resources" section under
# REL01-BP03 in the actual waf-reliability-pillar.pdf, captured 2026-09-15
# before this feature existed — used verbatim (not fabricated) to validate
# list detection against a real-world wrapped bullet item and real noise
# (page-footer text mid-run).
_REAL_REL01_RESOURCES_TEXT = (
    "Resources\n"
    "Related best practices:\n"
    "• REL01-BP01 Aware of service quotas and constraints\n"
    "• REL01-BP02 Manage service quotas across accounts and regions\n"
    "• REL01-BP04 Monitor and manage quotas\n"
    "• REL01-BP05 Automate quota management\n"
    "• REL01-BP06 Ensure that a suﬃcient gap exists between the current quotas and the maximum \n"
    "usage to accommodate failover\n"
    "• REL03-BP01 Choose how to segment your workload\n"
    "• REL10-BP01 Deploy the workload to multiple locations\n"
    "• REL11-BP01 Monitor all components of the workload to detect failures\n"
    "• REL11-BP03 Automate healing on all layers\n"
    "• REL12-BP04 Test resiliency using chaos engineering"
)


def _normalize():
    return normalize_pdf(
        build_sample_pdf_bytes(),
        document_id="waf-security-pillar",
        source_url="https://docs.aws.amazon.com/pdfs/wellarchitected/latest/security-pillar/wellarchitected-security-pillar.pdf",
        retrieved_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        source_edition="2026-09-11",
    )


def test_sections_follow_the_pdf_outline_structure():
    snapshot = _normalize()
    heading_paths = [section.heading_path for section in snapshot.sections]
    assert heading_paths == [
        ["Security foundations"],
        ["Security foundations", "Design principles"],
        ["Security foundations", "SEC01-BP01 Separate workloads using accounts"],
    ]


def test_leaf_section_text_comes_from_its_own_page():
    snapshot = _normalize()
    design_principles = next(
        s for s in snapshot.sections if s.heading_path[-1] == "Design principles"
    )
    assert "least privilege" in design_principles.blocks[0].text.lower()


def test_metadata_is_populated():
    snapshot = _normalize()
    assert snapshot.document_id == "waf-security-pillar"
    assert snapshot.source_edition == "2026-09-11"
    assert snapshot.content_hash
    assert snapshot.parser_version


def test_outline_entries_sharing_a_page_do_not_produce_duplicate_sections():
    """Regression test for the 2026-09-14 duplication incident: a parent
    heading and its child sharing the same start page must not each
    extract the whole page as their own content."""
    snapshot = normalize_pdf(
        build_sample_pdf_bytes_with_shared_page(),
        document_id="shared-page-doc",
        source_url="https://example.com/doc.pdf",
        retrieved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    heading_paths = [section.heading_path for section in snapshot.sections]

    assert heading_paths == [
        ["Parent heading", "Child heading"],
        ["Next heading"],
    ]
    texts = [section.blocks[0].text for section in snapshot.sections]
    assert len(texts) == len(set(texts)), "sections must not have duplicate content_hash-equivalent text"


def test_a_legitimate_multi_page_gap_is_extracted_in_full():
    """A section spanning several pages with no sub-headings (no bad
    destination involved) is real content and must not be truncated.
    Regression test for a 2026-09-14 finding: an earlier fix capped every
    section at 5 pages to bound a *different*, since-fixed bug (mis-
    resolved destinations claiming hundreds of pages) — but the cap
    itself silently discarded real content on every document that had a
    genuinely long section, confirmed via a Codex review that measured
    8-24 real body pages dropped per real WAF pillar PDF. The fix for the
    mis-resolved-destination case is _drop_entries_with_broken_destinations,
    not a blanket span cap — a legitimate gap like this one must come
    through whole."""
    snapshot = normalize_pdf(
        build_sample_pdf_bytes_with_a_far_apart_gap(),
        document_id="gap-doc",
        source_url="https://example.com/doc.pdf",
        retrieved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    gap_section = next(s for s in snapshot.sections if s.heading_path == ["Heading with a huge gap"])
    text = gap_section.blocks[0].text
    for page in range(1, 8):
        assert f"unique to page {page}" in text


def test_an_implausibly_large_span_raises_instead_of_silently_truncating():
    """If a section's computed span is far beyond anything real (a sign
    some other bad-destination case slipped past the other filters),
    fail loudly rather than quietly dropping content — silent truncation
    is exactly the mistake made and then caught (via Codex review) on
    2026-09-14, see Work-Project-Issues-Log."""
    import pytest

    from backend.corpus.normalize_pdf import _MAX_PLAUSIBLE_SECTION_PAGE_SPAN

    pdf_bytes = build_sample_pdf_bytes_with_a_far_apart_gap(
        gap_pages=_MAX_PLAUSIBLE_SECTION_PAGE_SPAN + 5
    )
    with pytest.raises(ValueError, match="beyond the plausible span"):
        normalize_pdf(
            pdf_bytes,
            document_id="huge-gap-doc",
            source_url="https://example.com/doc.pdf",
            retrieved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        )


def test_same_depth_siblings_sharing_a_page_both_keep_their_own_section():
    """Regression test for a real 2026-09-14 finding: collapsing every
    same-page entry (the earlier, too-broad fix) drops a same-depth
    sibling's own heading identity and mislabels its content under the
    other sibling's. Only a parent/child pair sharing a page should
    collapse; siblings must both survive, even as near-duplicate text."""
    snapshot = normalize_pdf(
        build_sample_pdf_bytes_with_same_depth_siblings_sharing_a_page(),
        document_id="siblings-doc",
        source_url="https://example.com/doc.pdf",
        retrieved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    heading_paths = [section.heading_path for section in snapshot.sections]
    assert ["Decommission resources", "COST04-BP03 Decommission resources"] in heading_paths
    assert (
        ["Decommission resources", "COST04-BP04 Decommission resources automatically"]
        in heading_paths
    )


def test_a_broken_entry_does_not_leak_a_stale_page_to_its_own_descendants():
    """Regression test for a real 2026-09-14 finding: dropping a broken
    outline entry (one whose page precedes its own parent's) must not
    leave a stale, unrelated sibling's page behind for that entry's own
    descendants to validate against — the descendant must be dropped too,
    since its true page can't be recovered once its parent is untrusted."""
    snapshot = normalize_pdf(
        build_sample_pdf_bytes_with_a_broken_entry_between_valid_siblings(),
        document_id="broken-entry-doc",
        source_url="https://example.com/doc.pdf",
        retrieved_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    heading_paths = [section.heading_path for section in snapshot.sections]
    assert ["Root B", "Broken child B", "Grandchild of broken child B"] not in heading_paths
    assert ["Root B", "Broken child B"] not in heading_paths


def test_real_bullet_list_text_is_segmented_into_a_list_block():
    """Regression/coverage for the content_type gap: a real "Resources"
    section from the actual Reliability pillar PDF must produce a
    dedicated LIST block covering the bullet run, separate from the
    leading "Resources" / "Related best practices:" prose lines, and the
    wrapped bullet ("...maximum \nusage to accommodate failover") must
    stay inside that one LIST block rather than leaking into a separate
    paragraph."""
    blocks = _segment_blocks(_REAL_REL01_RESOURCES_TEXT)

    assert blocks[0].kind == BlockKind.PARAGRAPH
    assert blocks[0].text == "Resources\nRelated best practices:"

    list_block = blocks[1]
    assert list_block.kind == BlockKind.LIST
    assert "REL01-BP01 Aware of service quotas and constraints" in list_block.text
    assert (
        "REL01-BP06 Ensure that a suﬃcient gap exists between the current quotas and the maximum \n"
        "usage to accommodate failover" in list_block.text
    )
    assert "REL12-BP04 Test resiliency using chaos engineering" in list_block.text


def test_numbered_procedure_lines_are_segmented_as_a_list_block():
    """Real WAF pillar PDFs use numbered steps ("1. ", "2. ", ...) for
    procedural guidance (e.g. cost-optimization billing-alert steps) —
    these must be protected as list blocks too, per ADR-0036's "ordered
    procedures" requirement, not just bullet-marker lists."""
    text = (
        "Configure the following steps to set up alerts.\n"
        "1. Filter out credits, discounts\n"
        "2. Select Show only\n"
        "3. Divide the amount in half"
    )
    blocks = _segment_blocks(text)

    assert blocks[0].kind == BlockKind.PARAGRAPH
    assert blocks[1].kind == BlockKind.LIST
    assert blocks[1].text == "1. Filter out credits, discounts\n2. Select Show only\n3. Divide the amount in half"


def test_a_lone_bullet_interrupted_by_page_noise_is_demoted_to_prose():
    """Regression test for the 2026-09-15 over-fragmentation finding: real
    WAF pillar "Design principles" sections render each principle as its
    own single "• Bolded title: paragraph." bullet, with a page
    header/footer line between consecutive principles. A single isolated
    bullet is a stylistic one-off, not a real list — without demoting it,
    real ingestion of the 6 pillar PDFs went from ~1,073 to ~4,000 chunks
    (each principle becoming its own tiny atomic LIST chunk)."""
    text = (
        "• Organize teams around business outcomes: leadership vision drives this.\n"
        "Operational Excellence Pillar AWS Well-Architected Framework\n"
        "• Implement observability for actionable insights: gain understanding of workload behavior.\n"
    )
    blocks = _segment_blocks(text)
    assert all(block.kind == BlockKind.PARAGRAPH for block in blocks)


def test_text_without_any_list_or_code_markers_is_untouched():
    """No structural markers found: a section must still come back as one
    PARAGRAPH block with text identical to the input, byte-for-byte —
    this is what keeps content_hash and chunk text stable for the ~99% of
    real sections that have no bullets, guarding against a chunk-count or
    hash regression across the existing 1,073-chunk corpus."""
    text = "This is an ordinary paragraph with no bullets or CLI commands at all."
    blocks = _segment_blocks(text)
    assert blocks == [Block(kind=BlockKind.PARAGRAPH, text=text)]


def test_cli_lines_are_segmented_as_a_code_block():
    """No real WAF pillar PDF section currently contains a CLI/code block
    (verified 2026-09-15), so this uses a synthetic example rather than a
    fabricated stand-in for something that exists in the real corpus —
    exercising the detection path so it's not dead code, and so it's
    ready the day a source PDF does carry one."""
    text = "Run the following commands:\naws s3 ls.\naws ec2 describe-instances.\nDone."
    blocks = _segment_blocks(text)

    code_block = next(b for b in blocks if b.kind == BlockKind.CODE)
    assert code_block.text == "aws s3 ls.\naws ec2 describe-instances."


# Real text extracted (pypdf plain-mode) from waf-security-pillar's
# SEC10-BP01 "Identify key personnel and external resources" section,
# captured 2026-09-15 — a genuine numbered procedure with lettered
# sub-steps, separated by blank lines, that was entirely demoted to prose
# before the 2026-09-15 fix (finding #1 of the Codex review).
_REAL_SEC10_STEPS_TEXT = (
    "1. Set up an incident management solution.\n"
    "\n"
    "a. Consider deploying Incident Manager in your Security Tooling account.\n"
    "\n"
    "2. Define contacts in your incident management solution.\n"
)

# Real text (pypdf plain-mode) from waf-sustainability-pillar, captured
# 2026-09-15 — two genuine resource bullets immediately followed by the
# "Sustainability in the cloud" heading and a full unrelated prose
# paragraph, all absorbed into one LIST block before the 2026-09-15 fix
# (finding #2 of the Codex review).
_REAL_SUSTAINABILITY_ABSORPTION_TEXT = (
    "• The Carbon Reduction Opportunity of Moving to Amazon Web Services\n"
    "• AWS enables sustainability solutions\n"
    "Sustainability in the cloud\n"
    "Sustainability in the cloud is a continuous effort focused primarily on energy reduction and \n"
    "efficiency across all components of a workload by achieving the maximum benefit from the \n"
    "resources provisioned and minimizing the total resources required."
)

# Real text (pypdf plain-mode) from waf-security-pillar's "Example table
# format:" incident-contact table, captured 2026-09-15 — a genuine
# pipe-delimited table typed prose before the 2026-09-15 fix (finding #3
# of the Codex review; independently spot-verified against the live chunk
# waf-security-pillar-0538 before this task began).
_REAL_SECURITY_PILLAR_TABLE_TEXT = (
    "Example table format:\n"
    "  | Role | Name | Contact Information | Responsibilities |\n"
    "1 | —–– | —–- | —–- | —–- |\n"
    "2 | Incident Manager | Jane Doe| jane.doe@example.com | Overall authority during \n"
    " response |\n"
    "Consider using the AWS Systems Manager Incident Manager feature to capture key contacts."
)

# Real text (pypdf plain-mode) from waf-security-pillar's SEC04-BP01
# CloudWatch metric-filter guidance, captured 2026-09-15 — a genuine
# single-seed, multi-line code/expression block typed prose before the
# 2026-09-15 fix (finding #4 of the Codex review).
_REAL_CLOUDWATCH_FILTER_TEXT = (
    "The instructions can be modified to configure the Amazon CloudWatch metric filter\n"
    "to filter on AssumeRole events related to the incident response IAM role:\n"
    '{ $.eventName = "AssumeRole" && $.requestParameters.roleArn = \n'
    ' "<INCIDENT_RESPONSE_ROLE_ARN>" && $.userIdentity.invokedBy NOT EXISTS }\n'
    "As the incident response roles are likely to have a high level of access, it is important."
)


def test_numbered_steps_separated_by_blank_lines_stay_a_list_block():
    """Regression test for finding #1 (2026-09-15 Codex review): a blank
    line between list items must not unconditionally break the run."""
    blocks = _segment_blocks(_REAL_SEC10_STEPS_TEXT)
    list_blocks = [b for b in blocks if b.kind == BlockKind.LIST]
    assert list_blocks, "expected at least one LIST block, got: " + repr(
        [b.kind for b in blocks]
    )
    merged_text = "\n".join(b.text for b in list_blocks)
    assert "1. Set up an incident management solution." in merged_text
    assert "2. Define contacts in your incident management solution." in merged_text


def test_a_lone_bullet_interrupted_by_page_noise_is_still_demoted_with_blank_lines():
    """The blank-line fix for finding #1 must not resurrect the
    over-fragmentation bug the ≥2-seed rule already fixed: an isolated
    bullet separated from the next by blank lines and unrelated content
    (no second marker following) must still demote to prose."""
    text = (
        "• Organize teams around business outcomes: leadership vision drives this.\n"
        "\n"
        "Operational Excellence Pillar AWS Well-Architected Framework\n"
        "\n"
        "This is an unrelated paragraph that never introduces another bullet at all.\n"
    )
    blocks = _segment_blocks(text)
    assert all(block.kind == BlockKind.PARAGRAPH for block in blocks)


def test_heading_after_list_bullets_is_not_absorbed_into_the_list_block():
    """Regression test for finding #2 (2026-09-15 Codex review): a
    heading-shaped line (and the unrelated prose paragraph after it) must
    not inherit LIST/CODE kind just because the preceding bullet line
    lacked terminal punctuation."""
    blocks = _segment_blocks(_REAL_SUSTAINABILITY_ABSORPTION_TEXT)
    list_block = next(b for b in blocks if b.kind == BlockKind.LIST)
    assert "Sustainability in the cloud" not in list_block.text
    assert "continuous effort" not in list_block.text

    prose_block = next(b for b in blocks if b.kind == BlockKind.PARAGRAPH)
    assert prose_block.text.startswith("Sustainability in the cloud")
    assert "continuous effort" in prose_block.text


def test_real_pipe_delimited_table_is_segmented_as_a_table_block():
    """Regression test for finding #3 (2026-09-15 Codex review): a real
    pipe-delimited table (independently spot-verified against
    waf-security-pillar-0538) must be typed TABLE, not prose."""
    blocks = _segment_blocks(_REAL_SECURITY_PILLAR_TABLE_TEXT)
    table_block = next(b for b in blocks if b.kind == BlockKind.TABLE)
    assert "Role | Name | Contact Information" in table_block.text
    assert "Incident Manager | Jane Doe" in table_block.text
    assert "Example table format:" not in table_block.text
    assert "Consider using" not in table_block.text


def test_markdown_pipe_table_is_segmented_as_a_table_block():
    """Real Markdown-style runbook table from waf-operational-excellence-pillar."""
    text = (
        "| Playbook ID | Description | Tools Used |\n"
        "|-------|-------|-------|\n"
        "| RUN001 | What is this playbook for? | Tools |\n"
    )
    blocks = _segment_blocks(text)
    assert blocks[0].kind == BlockKind.TABLE
    assert blocks[0].text == text.strip()


def test_a_single_stray_pipe_line_is_not_treated_as_a_table():
    """A lone line with >=2 pipes and no second row must still demote to
    prose, same ≥2-seed protection as LIST/CODE."""
    text = "Some prose | with a | couple of pipes in it that is not a table.\nMore ordinary prose follows."
    blocks = _segment_blocks(text)
    assert all(block.kind == BlockKind.PARAGRAPH for block in blocks)


def test_single_seed_multiline_code_expression_block_is_kept_as_code():
    """Regression test for finding #4 (2026-09-15 Codex review): a
    genuine single-marker, multi-line code/expression block (the real
    CloudWatch metric-filter expression) must not be demoted just because
    it only has one seed line — unlike LIST, CODE tolerates a lone seed
    when it has a real continuation."""
    blocks = _segment_blocks(_REAL_CLOUDWATCH_FILTER_TEXT)
    code_block = next(b for b in blocks if b.kind == BlockKind.CODE)
    assert code_block.text.startswith('{ $.eventName = "AssumeRole"')
    assert "INCIDENT_RESPONSE_ROLE_ARN" in code_block.text


def test_a_single_line_single_seed_code_match_is_still_demoted():
    """A lone CODE-marker line with no continuation at all (no real code
    block, just an isolated "aws "-prefixed sentence fragment) must still
    demote to prose — the finding #4 relaxation only applies when there's
    a genuine continuation line."""
    text = "Some paragraph.\naws is a common abbreviation seen here.\nMore ordinary prose follows next."
    blocks = _segment_blocks(text)
    assert all(block.kind == BlockKind.PARAGRAPH for block in blocks)


def test_markdown_header_lines_are_segmented_as_code():
    """Real Markdown ATX headers from waf-operational-excellence-pillar's
    runbook/playbook templates (finding #4)."""
    text = "# Runbook Title\n## Runbook Info\nSome ordinary prose paragraph follows this."
    blocks = _segment_blocks(text)
    code_block = next(b for b in blocks if b.kind == BlockKind.CODE)
    assert code_block.text == "# Runbook Title\n## Runbook Info"


def test_end_to_end_bullet_section_produces_a_list_block_via_normalize_pdf():
    snapshot = normalize_pdf(
        build_sample_pdf_bytes_with_bullet_list(),
        document_id="bullet-doc",
        source_url="https://example.com/doc.pdf",
        retrieved_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    section = next(s for s in snapshot.sections if s.heading_path == ["Related best practices"])
    kinds = [block.kind for block in section.blocks]
    assert BlockKind.LIST in kinds


# Real text (pypdf plain-mode) from waf-sustainability-pillar's SUS06-BP01
# "Communicate and cascade your sustainability goals" section, captured
# 2026-09-15 — a genuine list-item explanation that wraps onto a new,
# capitalized sentence right after a colon, split into a LIST chunk plus a
# separate PROSE chunk before this fix (finding #1 of the 2026-09-15
# follow-up Codex review; independently spot-verified against the live
# chunks waf-sustainability-pillar-0353/-0354 before this task began).
_REAL_SUSTAINABILITY_CUR_COLON_TEXT = (
    "• Communicate resource usage through proxy metrics to your teams: Track and report on your\n"
    "resource usage through proxy metrics. In the on-demand pricing models of the cloud, resource \n"
    "usage is related to cost, which is a generally-understandable metric. At a minimum, use cost as a \n"
    "proxy metric to communicate the resource usage and improvements by each team.\n"
    "• Enable hourly granularity in your Cost Explorer and create a Cost and Usage Report (CUR):\n"
    "The CUR provides daily or hourly usage granularity, rates, costs, and usage attributes for all \n"
    "AWS services. Use the Cloud Intelligence Dashboards and its Sustainability Proxy Metrics \n"
    "Dashboard as a starting point for the processing and visualization of cost and usage based \n"
    "data. For more detail, see the following:"
)

# Real text (pypdf plain-mode) from waf-reliability-pillar's REL04-BP04
# "Make mutating operations idempotent" Implementation-steps section,
# captured 2026-09-15 — a genuine bulleted example list (storage options
# for idempotency tokens) directly followed, with no intervening
# explanatory paragraph, by the next numbered procedure step. Before this
# fix, "4. Implement idempotent operations" was absorbed as an extra seed
# of the unrelated bullet-marker LIST run instead of starting its own step
# (finding #2 of the 2026-09-15 follow-up Codex review; independently
# spot-verified against the live chunks
# waf-reliability-pillar-0337/-0338 before this task began).
_REAL_IDEMPOTENCY_ORDINAL_AFTER_BULLETS_TEXT = (
    "Common AWS storage options typically used for storing idempotency tokens and related state \n"
    "include:\n"
    "• Amazon DynamoDB: DynamoDB is a NoSQL database service that provides low-latency \n"
    "performance and high availability, which makes it well-suited for the storage of idempotency-\n"
    "related data.\n"
    "• Amazon ElastiCache: ElastiCache can store idempotency tokens with high throughput, low \n"
    "latency, and at low cost.\n"
    "4. Implement idempotent operations\n"
    "Design your API and workload components to be idempotent. Incorporate idempotency checks \n"
    "into your workload components."
)

# Real text (pypdf plain-mode) from waf-performance-efficiency-pillar's
# PERF02-BP02 "Understand the available compute configuration and
# features" section, captured 2026-09-15 — a genuine two-column,
# non-pipe-delimited table mangled by PDF extraction into "term  •
# bullet-shaped cell" rows, split prose/list/prose with inconsistent
# content_type labels before this fix (finding #3 of the 2026-09-15
# follow-up Codex review; independently spot-verified against the live
# chunks waf-performance-efficiency-pillar-0125/-0126/-0127 before this
# task began).
_REAL_MANGLED_COMPUTE_TABLE_TEXT = (
    "Here are some key configuration options \n"
    "to consider:\n"
    "Configuration option Examples\n"
    "Instance type • Compute-optimized instances are ideal \n"
    "for the workloads that require high higher \n"
    "vCPU to memory ratio. \n"
    "• Memory-optimized instances deliver large \n"
    "amounts of memory to support memory \n"
    "intensive workloads.\n"
    "• Storage-optimized instances are designed \n"
    "for workloads that require high, sequentia \n"
    "l read and write access (IOPS) to local \n"
    "storage.\n"
    "Pricing model • On-Demand Instances let you use the \n"
    "compute capacity by the hour or second \n"
    "with no long-term commitment.\n"
    "Resources\n"
    "Related documents:\n"
    "• Cloud Compute with AWS \n"
    "• Amazon EC2 Instance Types \n"
    "• Processor State Control for Your Amazon EC2 Instance"
)


def test_colon_ended_list_item_absorbs_its_capitalized_continuation():
    """Regression test for finding #1 (2026-09-15 follow-up Codex review):
    a list item's explanation that wraps onto a new sentence right after
    a colon must stay inside the same LIST block, not split off as prose
    just because the continuation sentence starts with a capital letter."""
    blocks = _segment_blocks(_REAL_SUSTAINABILITY_CUR_COLON_TEXT)
    list_blocks = [b for b in blocks if b.kind == BlockKind.LIST]
    assert list_blocks, "expected at least one LIST block, got: " + repr([b.kind for b in blocks])
    merged_text = "\n".join(b.text for b in list_blocks)
    assert "Cost and Usage Report (CUR):" in merged_text
    assert "The CUR provides daily or hourly usage granularity" in merged_text


def test_a_page_footer_stamp_after_a_colon_is_still_not_absorbed():
    """Regression test caught while verifying finding #1's fix against the
    full real corpus (not just the one confirmed example): a bullet ending
    in ":" directly followed by a running page-footer/header stamp (which
    also happens to start with a capital letter) must not be absorbed
    just because of the colon carve-out — real text (pypdf plain-mode)
    from waf-performance-efficiency-pillar's PERF02-BP01 "Benchmark to
    validate performance" Implementation-steps section, captured
    2026-09-15."""
    text = (
        "• Benchmark and monitor: Perform your benchmark tests and monitor the metrics during the test.\n"
        "• Analyze and document:\n"
        "Implementation guidance 16\n"
    )
    blocks = _segment_blocks(text)
    list_block = next(b for b in blocks if b.kind == BlockKind.LIST)
    assert "Implementation guidance 16" not in list_block.text


def test_a_genuine_new_heading_after_a_colon_is_still_not_absorbed():
    """The colon carve-out from finding #1 must not swallow a genuine new
    heading just because the previous list item happened to end with a
    colon — only tested here as a synthetic guardrail since no real
    corpus example of that exact combination was found."""
    text = (
        "• Related documents:\n"
        "• Some other bullet with more detail that goes on for a while and ends properly.\n"
        "Resources\n"
        "This is an unrelated heading-shaped paragraph that must not be absorbed at all.\n"
    )
    blocks = _segment_blocks(text)
    list_block = next(b for b in blocks if b.kind == BlockKind.LIST)
    assert "Resources" not in list_block.text
    assert "unrelated heading-shaped paragraph" not in list_block.text


def test_numbered_step_after_bullet_example_list_starts_its_own_block():
    """Regression test for finding #2 (2026-09-15 follow-up Codex review):
    a numbered procedure step directly following a bulleted example list
    (no explanatory paragraph in between) must not be absorbed as another
    seed of that unrelated bullet-marker list."""
    blocks = _segment_blocks(_REAL_IDEMPOTENCY_ORDINAL_AFTER_BULLETS_TEXT)
    list_block = next(b for b in blocks if b.kind == BlockKind.LIST)
    assert "Amazon DynamoDB" in list_block.text
    assert "Amazon ElastiCache" in list_block.text
    assert "4. Implement idempotent operations" not in list_block.text

    trailing_text = "\n".join(b.text for b in blocks if b.kind == BlockKind.PARAGRAPH)
    assert "4. Implement idempotent operations" in trailing_text
    assert "Design your API and workload components" in trailing_text


def test_numbered_and_lettered_substeps_still_share_one_list_run():
    """The ordinal/bullet marker-flavor split from finding #2 must not
    reopen finding #1 of the original 2026-09-15 review: numbered steps
    and their lettered sub-steps are the same marker "flavor" (ordinal)
    and must still merge into one run when otherwise contiguous."""
    blocks = _segment_blocks(_REAL_SEC10_STEPS_TEXT)
    list_blocks = [b for b in blocks if b.kind == BlockKind.LIST]
    assert list_blocks, "expected at least one LIST block, got: " + repr([b.kind for b in blocks])
    merged_text = "\n".join(b.text for b in list_blocks)
    assert "1. Set up an incident management solution." in merged_text
    assert "a. Consider deploying Incident Manager" in merged_text
    assert "2. Define contacts in your incident management solution." in merged_text


def test_mangled_two_column_table_stays_one_paragraph_not_a_false_list():
    """Regression test for finding #3 (2026-09-15 follow-up Codex review):
    a real two-column, non-pipe-delimited table (mangled by PDF extraction
    into "term + mid-line bullet" rows) must not have its bullet-shaped
    cells misread as a genuine LIST — true atomic TABLE detection was not
    attempted for this shape (see _segment_blocks' docstring); the
    accepted, documented outcome is that it reads as ordinary paragraphs
    instead of being split into inconsistent list/prose/list chunks."""
    blocks = _segment_blocks(_REAL_MANGLED_COMPUTE_TABLE_TEXT)
    mangled_row_blocks = [
        b for b in blocks if "Compute-optimized" in b.text or "Memory-optimized" in b.text or "On-Demand" in b.text
    ]
    assert all(b.kind == BlockKind.PARAGRAPH for b in mangled_row_blocks), (
        "mangled table rows must not be typed LIST/TABLE: " + repr([(b.kind, b.text[:40]) for b in mangled_row_blocks])
    )

    real_list_block = next(b for b in blocks if b.kind == BlockKind.LIST)
    assert "Cloud Compute with AWS" in real_list_block.text
    assert "Compute-optimized" not in real_list_block.text
