from datetime import datetime

from bs4 import BeautifulSoup

from .models import Block, BlockKind, DocumentSnapshot, Section

_PARSER_VERSION = "1.0.0"
_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_CONTAINER_TAGS = {"table", "pre", "ul", "ol"}


def normalize_html(
    html: str,
    *,
    document_id: str,
    source_url: str,
    retrieved_at: datetime,
    source_edition: str | None = None,
    license: str = "CC-BY-SA-4.0",
) -> DocumentSnapshot:
    """Turn raw source HTML into a versioned, heading-structured snapshot
    (ADR-0036) — splits on heading boundaries and keeps tables/code/lists
    as atomic blocks so the chunker never has to split them mid-block."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.body or soup

    heading_stack: list[tuple[int, str]] = []
    sections: list[Section] = []
    current_blocks: list[Block] = []

    def flush() -> None:
        if current_blocks:
            sections.append(
                Section(
                    heading_path=[text for _, text in heading_stack],
                    blocks=list(current_blocks),
                )
            )
            current_blocks.clear()

    for tag in root.find_all(list(_HEADING_LEVELS) + ["p", "table", "pre", "ul", "ol"]):
        if tag.name in _HEADING_LEVELS:
            flush()
            level = _HEADING_LEVELS[tag.name]
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, text))
            continue

        if any(parent.name in _CONTAINER_TAGS for parent in tag.parents):
            continue

        if tag.name == "p":
            text = tag.get_text(" ", strip=True)
            if text:
                current_blocks.append(Block(kind=BlockKind.PARAGRAPH, text=text))
        elif tag.name == "table":
            rows = []
            for row in tag.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
                if any(cells):
                    rows.append(" | ".join(cells))
            text = "\n".join(rows)
            if text:
                current_blocks.append(Block(kind=BlockKind.TABLE, text=text))
        elif tag.name == "pre":
            text = tag.get_text("\n", strip=True)
            if text:
                current_blocks.append(Block(kind=BlockKind.CODE, text=text))
        elif tag.name in ("ul", "ol"):
            items = [
                item
                for li in tag.find_all("li", recursive=False)
                if (item := li.get_text(" ", strip=True))
            ]
            text = "\n".join(f"- {item}" for item in items)
            if text:
                current_blocks.append(Block(kind=BlockKind.LIST, text=text))

    flush()

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
