import re
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .models import Block, BlockKind, DocumentSnapshot, Section

# Bump whenever segmentation output (block boundaries or kinds) can change.
_PARSER_VERSION = "1.4.0"
_SKIP_TITLES = {"table of contents", "notices", "contributors", "document history"}
# Bullet glyphs and numbered-step prefixes actually observed introducing list
# items in the real WAF pillar PDFs (e.g. "Related best practices:" /
# "Resources" sections use "•"; procedural "Implementation steps" sections use
# "1. ", "2. ", ...). A bare "-"/"*" at line start was tried and dropped: real
# corpus lines like "- AWS Well-Architected" are wrapped title fragments, not
# bullets (zero genuine dash/asterisk bullets across all 6 pillar PDFs, only
# false positives). Lettered sub-steps ("a. ", "b. ", ...) are included: 297
# real occurrences across all 6 pillar PDFs (e.g. "a. Use services like AWS
# Config to..." under numbered "Implementation steps"), zero false positives (a
# genuine sentence never starts "<single letter>. <word>" at a line boundary in
# this corpus) — these are real nested list markers, not prose.
_LIST_LINE_PATTERN = re.compile(r"^([•‣◦▪]|\d{1,2}\.|[a-z]\.)\s+\S")
# CLI prefixes ("aws ", "curl ", etc.), plus two shapes with zero false
# positives in the real corpus: a line opening with "{" (the one real
# occurrence is a CloudWatch metric-filter expression in waf-security-pillar,
# "{ $.eventName = ... }"), and a Markdown ATX header ("#"/"##", the 6 real
# occurrences are runbook/playbook templates in
# waf-operational-excellence-pillar, e.g. "# Runbook Title" / "## Steps").
_CODE_LINE_PATTERN = re.compile(r"^(\$ |aws |curl |docker |kubectl |sudo |\{|#{1,6}\s)")
# A line that is NOT itself a bullet (doesn't start with one) but contains
# a bullet glyph later in the line, preceded by other text, is the
# signature of a real corpus defect: a two-column, non-pipe-delimited
# table (a "term" cell glued to the start of its "Examples" cell's first
# bullet by pypdf's text extraction) rather than a genuine list or prose
# line. All 12 real occurrences across all 6 pillar PDFs are in
# waf-performance-efficiency-pillar's mangled compute-options/pricing and
# data-store/networking tables (e.g. "Instance type • Compute-optimized
# instances are ideal", "Pricing model • On-Demand Instances let you use
# the") — zero elsewhere in the corpus. See _segment_blocks for how this
# is used to stop the table's bullet-shaped cells from being misread as a
# genuine, atomic LIST run.
_TABLE_ROW_GLUE_PATTERN = re.compile(r"^(?!\s*[•‣◦▪])\S.*\s[•‣◦▪]\s+\S")
# A line with >=2 "|" characters is treated as a table row. In the real corpus,
# every pipe-delimited table (waf-security-pillar's "Example table format:"
# incident-contact table, waf-operational-excellence-pillar's runbook/playbook
# Markdown tables) has multiple consecutive rows meeting this bar, with zero
# single-line false positives found elsewhere in the corpus. This intentionally
# does NOT catch waf-performance-efficiency-pillar's "Configuration option /
# Examples" compute-options table — that one has no pipe delimiters at all
# (plain two-column text mangled by PDF extraction into a bullet-list shape),
# and no general non-delimited table detector was added for it: a heuristic
# general enough to catch a headerless two-column layout would be
# indistinguishable from ordinary "term: explanation" prose paragraphs
# elsewhere in these documents (known gap, left undetected rather than risking
# prose false positives).
_TABLE_MIN_PIPES = 2
_TERMINAL_PUNCTUATION = (".", "?", "!")
# A running page-footer/header stamp in this corpus ends with a bare page
# number (e.g. "Implementation guidance 16", "REL08-BP04 Deploy using
# immutable infrastructure 150" — see _is_heading_or_new_sentence's own
# docstring for more real examples of this shape). In the real corpus,
# every bullet ending in ":" that is directly followed by one of these
# page-furniture lines (not a genuine explanation) matches this pattern,
# and the known real continuation that must still be absorbed ("The CUR
# provides daily or hourly usage granularity...") does not. See the colon
# carve-out in _segment_blocks.
_PAGE_FOOTER_NUMBER_PATTERN = re.compile(r"\d+$")
# A run needs at least this many real list/table marker lines ("seeds",
# as opposed to lines that only inherited the kind via wrapped-line
# continuation) to survive as LIST/TABLE — see _segment_blocks docstring
# for why a lone seed is demoted back to PARAGRAPH instead. CODE uses a
# relaxed variant of this same rule — see _MIN_SEEDS_FOR_KIND.
_MIN_SEEDS_TO_KEEP_STRUCTURE = 2
# A section spanning more pages than this is a sign something upstream is
# still wrong (a bad destination the other filters didn't catch), not real
# document structure. Across all 6 WAF pillar PDFs the largest genuine
# span is 14 pages. This is a generous safety net, not a content limit:
# when it trips we raise loudly rather than silently truncating, because
# truncation turns a visible duplication bug into a hard-to-detect
# content-loss bug (8-24 real body pages silently dropped per document).
_MAX_PLAUSIBLE_SECTION_PAGE_SPAN = 50


def normalize_pdf(
    pdf_bytes: bytes,
    *,
    document_id: str,
    source_url: str,
    retrieved_at: datetime,
    source_edition: str | None = None,
    license: str = "CC-BY-SA-4.0",
) -> DocumentSnapshot:
    """Turn a PDF whitepaper into a versioned, heading-structured snapshot
    using the PDF's own outline/bookmark tree — AWS Well-Architected pillar
    PDFs carry a real, deeply-nested outline matching their true section
    structure, more reliable than guessing headings from extracted text."""
    reader = PdfReader(BytesIO(pdf_bytes))
    entries = _flatten_outline(reader, reader.outline)
    # Drop front/back-matter entries before they participate in boundary
    # math below — left in, an entry like "Table of Contents" still acts
    # as a page-span/parent-tracking neighbor for real entries around it
    # even though it never becomes a section of its own (seen in the
    # Sustainability pillar PDF).
    entries = [e for e in entries if e[1].strip().lower() not in _SKIP_TITLES]
    entries = _drop_entries_with_broken_destinations(entries)

    sections: list[Section] = []
    for index, (_, title, start_page, heading_path) in enumerate(entries):
        # Consecutive outline entries commonly share a start page (a
        # heading and its own first sub-heading both land on the same
        # printed page) — without this, each of them independently
        # extracted the whole shared page, producing byte-identical
        # chunks under different heading paths (93.5% of the corpus was
        # duplicate content before this check). Only skip the
        # *parent* in a shared-page run — its own content is genuinely
        # indistinguishable from its child's. Same-depth siblings sharing
        # a page (e.g. real "COST04-BP03"/"COST04-BP04", both page 75)
        # are NOT a parent/child pair and must not be collapsed this way:
        # doing so silently drops one heading's identity and mislabels
        # its content under the other's (this occurs in 5 of 6 pillar
        # PDFs), so both keep their own section instead, even
        # though that means they'll share near-identical text, because a
        # correct citation under duplicate content is far less harmful
        # than a wrong citation under merged content.
        if (
            index + 1 < len(entries)
            and entries[index + 1][2] == start_page
            and _is_descendant(heading_path, entries[index + 1][3])
        ):
            continue
        end_page = entries[index + 1][2] if index + 1 < len(entries) else len(reader.pages)
        # KNOWN GAP (zero occurrences across all 6 WAF pillar PDFs): if two
        # same-depth siblings resolve with the *later* one pointing to an
        # earlier page (a backward-resolving destination, distinct from the
        # parent/child case _drop_entries_with_broken_destinations already
        # catches), this silently clamps the span to 1 page instead of flagging
        # that the later sibling's destination is suspect. Left unfixed until
        # it is observed in real data, rather than fixed speculatively.
        end_page = max(end_page, start_page + 1)
        span = end_page - start_page
        if span > _MAX_PLAUSIBLE_SECTION_PAGE_SPAN:
            raise ValueError(
                f"Section {heading_path!r} claims pages {start_page}-{end_page} "
                f"({span} pages) — beyond the plausible span for this document "
                "type, which usually means an outline destination is still "
                "resolving incorrectly. Investigate rather than silently "
                "truncating the section."
            )
        text = _extract_text(reader, start_page, end_page)
        if not text:
            continue
        sections.append(Section(heading_path=heading_path, blocks=_segment_blocks(text)))

    return DocumentSnapshot(
        document_id=document_id,
        source_url=source_url,
        retrieved_at=retrieved_at,
        source_edition=source_edition,
        license=license,
        parser_version=_PARSER_VERSION,
        sections=sections,
        content_hash=DocumentSnapshot.compute_content_hash(sections),
    )


def _is_descendant(ancestor_heading_path: list[str], candidate_heading_path: list[str]) -> bool:
    return (
        len(candidate_heading_path) > len(ancestor_heading_path)
        and candidate_heading_path[: len(ancestor_heading_path)] == ancestor_heading_path
    )


def _drop_entries_with_broken_destinations(
    entries: list[tuple[int, str, int, list[str]]],
) -> list[tuple[int, str, int, list[str]]]:
    """Drop any entry whose resolved page is earlier than its own parent
    heading's page — a child section cannot legitimately start before its own
    parent. In the WAF Operational Excellence pillar PDF, every
    "Resources"/"Implementation guidance" sub-heading under OPS01-BP03 through
    BP06 resolved to page 14 regardless of their parent BP heading's real (and
    correctly increasing: 16, 18, 21, 23) page, causing unrelated best
    practices to produce identical duplicate content. This is a
    pypdf/PDF-structure quirk in the source destinations, not something we
    control — we can't recover the true page, so we drop the entry rather than
    guess."""
    result: list[tuple[int, str, int, list[str]]] = []
    parent_page_by_depth: dict[int, float] = {}
    for depth, title, start_page, heading_path in entries:
        for deeper_depth in [d for d in parent_page_by_depth if d > depth]:
            del parent_page_by_depth[deeper_depth]
        parent_page = parent_page_by_depth.get(depth - 1)
        if parent_page is not None and start_page < parent_page:
            # This entry's own page can't be trusted, so no descendant of
            # it can be validated against it either — mark this depth as
            # unverifiable (rather than leaving it unset, which would let
            # a deeper entry fall through to a stale, unrelated sibling's
            # page from earlier in the tree) so every descendant is
            # dropped too.
            parent_page_by_depth[depth] = float("inf")
            continue
        parent_page_by_depth[depth] = start_page
        result.append((depth, title, start_page, heading_path))
    return result


def _flatten_outline(reader: PdfReader, items) -> list[tuple[int, str, int, list[str]]]:
    # KNOWN GAP (zero occurrences across all 6 WAF pillar PDFs): if an entry is
    # skipped below (empty title, or its destination fails to resolve) but the
    # outline tree still nests real children under it, `stack` never gets that
    # entry's title pushed — so a valid child at that depth will have its
    # `heading_path` built against whatever ancestor happened to be on the
    # stack from an earlier, unrelated branch instead of its true (skipped)
    # parent. Left unfixed until it is observed in real data.
    stack: list[str] = []
    flat: list[tuple[int, str, int, list[str]]] = []
    for depth, item in _walk_outline(items):
        title = (item.title or "").strip()
        if not title:
            continue
        try:
            page_number = reader.get_destination_page_number(item)
        except (PyPdfError, ValueError, KeyError):
            continue
        del stack[depth:]
        stack.append(title)
        flat.append((depth, title, page_number, list(stack)))
    return flat


def _walk_outline(items, depth: int = 0):
    for item in items:
        if isinstance(item, list):
            yield from _walk_outline(item, depth + 1)
        else:
            yield depth, item


def _extract_text(reader: PdfReader, start_page: int, end_page: int) -> str:
    parts = []
    for page_index in range(start_page, min(end_page, len(reader.pages))):
        text = (reader.pages[page_index].extract_text() or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _is_heading_or_new_sentence(line: str) -> bool:
    """True if `line` looks like the start of fresh content (a heading, or
    a new sentence/paragraph) rather than the wrapped continuation of a
    list/code line above it. Real wrapped continuations in this corpus are
    produced by pypdf breaking a sentence mid-word-run, so they start with
    a lowercase word (e.g. "usage to accommodate failover", continuing
    "...current quotas and the maximum"); a line starting with an
    uppercase letter is either a genuine new sentence or a heading (a
    best-practice ID, "Resources", "Design principles", a running
    header/footer). Without this check, 2,078 lines in the real corpus were
    absorbed into LIST/CODE runs; a random sample found zero genuine
    wrapped continuations and many real headings/new sentences/page
    furniture (e.g. "Resources 67", "COST01-BP08 Create a cost-aware
    culture", "Develop a process that defines the criteria..."). In
    waf-sustainability-pillar, for example, two resource bullets absorbed
    the "Sustainability in the cloud" heading and the full paragraph after
    it.

    This uppercase-start check is itself too aggressive on its own: a
    genuine list-item continuation sentence that happens to start with a
    capitalized word (e.g. a proper noun, or just an ordinary sentence
    opener) is indistinguishable from a real heading by capitalization
    alone. See _segment_blocks' caller of this function for the one
    additional signal (a preceding colon) that resolves this without
    reopening the absorption problem above. Real waf-sustainability-pillar
    example: "...create a Cost and Usage Report (CUR):" + "The CUR provides
    daily or hourly usage granularity..." is one continuous explanation
    even though the continuation sentence starts with "The"."""
    return line[:1].isupper()


def _segment_blocks(text: str) -> list[Block]:
    """Split a section's flat extracted text into PARAGRAPH/LIST/TABLE/CODE
    blocks so the chunker (which already keeps non-PARAGRAPH blocks
    intact, per ADR-0036) can protect bullet/numbered lists, tables, and
    CLI/code snippets from being split mid-item.

    A wrapped continuation line (no bullet/table/code marker of its own)
    keeps the previous line's kind as long as (a) that previous line
    didn't end a sentence, and (b) this line doesn't itself look like a
    heading or the start of a fresh sentence (see
    _is_heading_or_new_sentence) — together these are what keep a bullet
    like "REL01-BP06 Ensure that a sufficient gap exists between the
    current quotas and the maximum" + "usage to accommodate failover" (a
    real two-line wrap in the Reliability pillar PDF) inside one LIST
    block, while stopping a following heading or unrelated paragraph (see
    _is_heading_or_new_sentence) from being absorbed into it.

    A blank line does NOT unconditionally break a LIST/TABLE/CODE run —
    it inherits the run's current kind so real procedures split across
    blank lines by PDF extraction (e.g. numbered "Implementation steps"
    separated by blank lines, with lettered "a."/"b." sub-steps of their
    own) survive as one run instead of being fragmented into isolated,
    single-seed groups. This does NOT by itself let two unrelated
    paragraphs merge: the line immediately after a blank line still only
    inherits if it passes the normal continuation checks (blank lines are
    never non-empty, so a plain prose line after a blank never satisfies
    the "previous_line truthy" check below) — a fresh LIST/CODE marker
    line, however, starts a new seed regardless, so it re-joins the
    (still-open) run instead of starting a disconnected group. Real
    example (waf-security-pillar SEC06-BP05 "Automate compute
    protection"): a genuine 6-step numbered procedure with lettered
    sub-steps, separated by blank lines, which would otherwise be entirely
    demoted to prose.

    A run is only kept as LIST/TABLE if it contains at least
    _MIN_SEEDS_TO_KEEP_STRUCTURE real marker lines ("seeds" — lines that
    matched a pattern directly, not lines that only inherited the kind via
    continuation); a lone seed is demoted back to PARAGRAPH. Without this,
    ingestion of the 6 WAF pillar PDFs grows from ~1,073 to ~4,000 chunks: each
    pillar's "Design principles" section renders every principle as "• Bolded
    title: full explanatory paragraph.", one principle per bullet, and
    consecutive principles are usually separated by a page-header/footer line
    that isn't itself a continuation, so every single principle would become
    its own tiny atomic LIST chunk instead of either the whole multi-principle
    run stitching into one block, or (lacking any real multi-bullet run)
    staying ordinary prose grouped by the normal token budget. A lone bullet
    like that reads as a stylistic one-off, not a real list structure worth
    protecting from the chunker's normal grouping.

    CODE uses a relaxed variant of that rule: a single-seed CODE run
    survives if it has more than one line (i.e. the seed has a real
    continuation), since genuine code/expression blocks in this corpus
    (e.g. the real CloudWatch metric-filter expression in
    waf-security-pillar, "{ $.eventName = ... }" wrapped across two
    lines) naturally have exactly one opening marker line, unlike a list
    where each item needs its own marker. A single-line, single-seed CODE
    run (no continuation at all) is still demoted, same as LIST.

    A continuation line that would otherwise be stopped by
    _is_heading_or_new_sentence's uppercase-start check is still absorbed if
    the line before it ends with a colon — a colon is an explicit, unambiguous
    "an explanation follows" signal (distinct from ordinary terminal
    punctuation), so a capitalized continuation sentence right after it is
    never mistaken for a real heading (real waf-sustainability-pillar example:
    "...create a Cost and Usage Report (CUR):" + "The CUR provides daily or
    hourly usage granularity..."). This carve-out is itself guarded against the
    corpus's running page-footer/header stamps (_PAGE_FOOTER_NUMBER_PATTERN) —
    without that guard, a real bullet ending in ":" immediately followed by a
    page-furniture line (e.g. "• Analyze and document:" + "Implementation
    guidance 16") would be wrongly absorbed into the list.

    A bullet-marker (•/‣/◦/▪) seed line never continues an already-open
    run whose most recent seed was an ordinal marker (numbered "1. " or
    lettered "a. "), and vice versa — mixing the two marker "flavors" into
    one LIST run is itself a bug, not a real list, even though both map to
    the same BlockKind. Real waf-reliability-pillar REL04-BP04 example: a
    bulleted "Amazon DynamoDB: ..." / "Amazon ElastiCache: ..." example list
    directly followed, with no intervening explanatory paragraph, by the
    next numbered procedure step "4. Implement idempotent operations",
    which must start its own step + explanation like steps 1/2/3/5/6
    rather than being absorbed into the unrelated example list.

    A line that is not itself a bullet but glues a "term" to a mid-line
    bullet (_TABLE_ROW_GLUE_PATTERN) marks the start of a real corpus
    defect — a mangled, non-pipe-delimited two-column table — and turns on
    a "mangled table" mode that suppresses LIST-seed classification for
    bullet lines until a colon-ending line is seen (a colon reliably
    signals a genuine new list is about to start, e.g. "Related
    documents:"). Without this, the table's bullet-shaped cells
    intermittently cross the >=2-seed threshold (depending on how many
    bullets happen to fall between "term" lines) and get inconsistently
    typed LIST/PARAGRAPH/LIST instead of reading as one ordinary
    paragraph. True atomic TABLE detection for this shape is not attempted
    (the mangled rows are themselves interleaved with page header/footer
    noise across a page break, which would need its own handling) — this
    fix only prevents the false LIST split, so the content lands as
    ordinary PARAGRAPH, a documented, accepted gap rather than a false
    table detector risking prose false positives elsewhere."""
    lines = text.split("\n")
    kinds: list[BlockKind] = []
    is_seed: list[bool] = []
    # None for non-seed/non-LIST lines; "bullet" or "ordinal" for a LIST
    # seed, tracking which marker family it matched (see the marker-flavor
    # paragraph of _segment_blocks' docstring).
    marker_styles: list[str | None] = []
    # See _TABLE_ROW_GLUE_PATTERN and _segment_blocks' docstring: once a glued
    # "term + mid-line bullet" row is seen, real bullet lines are the mangled
    # table's other cells, not a genuine list, until a colon-ending line
    # signals a real new list is starting.
    in_mangled_table_row = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            previous_kind = kinds[index - 1] if index > 0 else None
            kinds.append(
                previous_kind
                if previous_kind in (BlockKind.LIST, BlockKind.TABLE, BlockKind.CODE)
                else BlockKind.PARAGRAPH
            )
            is_seed.append(False)
            marker_styles.append(None)
            continue
        if _TABLE_ROW_GLUE_PATTERN.match(stripped):
            in_mangled_table_row = True
        if _LIST_LINE_PATTERN.match(stripped) and not in_mangled_table_row:
            kinds.append(BlockKind.LIST)
            is_seed.append(True)
            marker_styles.append("bullet" if stripped[0] in "•‣◦▪" else "ordinal")
            continue
        if stripped.count("|") >= _TABLE_MIN_PIPES:
            kinds.append(BlockKind.TABLE)
            is_seed.append(True)
            marker_styles.append(None)
            continue
        if _CODE_LINE_PATTERN.match(stripped):
            kinds.append(BlockKind.CODE)
            is_seed.append(True)
            marker_styles.append(None)
            continue
        previous_kind = kinds[index - 1] if index > 0 else None
        previous_line = lines[index - 1].strip() if index > 0 else ""
        if (
            previous_kind in (BlockKind.LIST, BlockKind.TABLE, BlockKind.CODE)
            and previous_line
            and not previous_line.endswith(_TERMINAL_PUNCTUATION)
            and (
                (previous_line.endswith(":") and not _PAGE_FOOTER_NUMBER_PATTERN.search(stripped))
                or not _is_heading_or_new_sentence(stripped)
            )
        ):
            kinds.append(previous_kind)
        else:
            kinds.append(BlockKind.PARAGRAPH)
        is_seed.append(False)
        marker_styles.append(None)
        if stripped.endswith(":"):
            in_mangled_table_row = False

    if not any(kind in (BlockKind.LIST, BlockKind.TABLE, BlockKind.CODE) for kind in kinds):
        # No structure detected — return the untouched original text as a
        # single block, byte-for-byte identical to pre-detection behavior,
        # so the vast majority of sections (no bullets/tables/CLI content)
        # see zero change to their chunk text or content_hash.
        return [Block(kind=BlockKind.PARAGRAPH, text=text)]

    blocks: list[Block] = []
    group_lines: list[str] = []
    group_kind: BlockKind | None = None
    group_seeds = 0
    group_marker_style: str | None = None

    def flush() -> None:
        nonlocal group_lines, group_kind, group_seeds, group_marker_style
        joined = "\n".join(group_lines).strip()
        if joined:
            kind = group_kind
            too_few_seeds = group_seeds < _MIN_SEEDS_TO_KEEP_STRUCTURE
            # LIST/TABLE always need >=2 seeds; CODE tolerates a lone seed
            # if it has a real continuation (len(group_lines) > 1); see
            # _segment_blocks' docstring.
            if (kind in (BlockKind.LIST, BlockKind.TABLE) and too_few_seeds) or (
                kind == BlockKind.CODE and too_few_seeds and len(group_lines) <= 1
            ):
                kind = BlockKind.PARAGRAPH
            blocks.append(Block(kind=kind, text=joined))
        group_lines = []
        group_kind = None
        group_seeds = 0
        group_marker_style = None

    for line, kind, seed, marker_style in zip(lines, kinds, is_seed, marker_styles):
        # A fresh ordinal/bullet seed never continues an open LIST run
        # seeded by the other marker flavor; see _segment_blocks'
        # docstring.
        marker_flavor_changed = (
            seed
            and kind == BlockKind.LIST
            and group_marker_style is not None
            and marker_style != group_marker_style
        )
        if group_kind is not None and (kind != group_kind or marker_flavor_changed):
            flush()
        group_kind = kind
        group_lines.append(line)
        if seed:
            group_seeds += 1
            if kind == BlockKind.LIST:
                group_marker_style = marker_style
    flush()

    return blocks
