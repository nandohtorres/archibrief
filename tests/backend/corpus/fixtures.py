def build_sample_pdf_bytes() -> bytes:
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 750, "Security foundations")
    pdf.drawString(72, 730, "This chapter covers the foundational security practices.")
    pdf.showPage()
    pdf.drawString(72, 750, "Design principles")
    pdf.drawString(72, 730, "Apply least privilege everywhere across every workload.")
    pdf.showPage()
    pdf.drawString(72, 750, "SEC01-BP01 Separate workloads using accounts")
    pdf.drawString(72, 730, "Establish a clear boundary between workloads using accounts.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    foundations = writer.add_outline_item("Security foundations", 0)
    writer.add_outline_item("Design principles", 1, parent=foundations)
    writer.add_outline_item("SEC01-BP01 Separate workloads using accounts", 2, parent=foundations)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_pdf_bytes_with_shared_page() -> bytes:
    """Two outline entries pointing at the same page (a heading and its
    own first sub-heading both landing on the same printed page) — the
    real-world pattern that caused massive chunk duplication in the WAF
    pillar PDFs (2026-09-14, see Work-Project-Issues-Log)."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 750, "Parent heading")
    pdf.drawString(72, 730, "Child heading")
    pdf.drawString(72, 710, "Shared page content belonging to the child heading.")
    pdf.showPage()
    pdf.drawString(72, 750, "Next heading")
    pdf.drawString(72, 730, "Content on the following page.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    parent = writer.add_outline_item("Parent heading", 0)
    writer.add_outline_item("Child heading", 0, parent=parent)
    writer.add_outline_item("Next heading", 1)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_pdf_bytes_with_a_far_apart_gap(gap_pages: int = 7) -> bytes:
    """A heading whose next outline entry is `gap_pages` later — either a
    legitimate long section with no sub-headings (small gap) or a stand-in
    for an implausible span that should be rejected outright (large gap),
    depending on which test uses it."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    total_pages = gap_pages + 3
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for i in range(total_pages):
        pdf.drawString(72, 750, f"Page {i} heading text")
        pdf.drawString(72, 730, f"Body content unique to page {i}.")
        pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    writer.add_outline_item("Heading with a huge gap", 1)
    writer.add_outline_item("Next heading", 1 + gap_pages)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_pdf_bytes_with_same_depth_siblings_sharing_a_page() -> bytes:
    """Two same-depth siblings (not a parent/child pair) both resolving to
    the same page — the real pattern behind a 2026-09-14 finding: real
    WAF pillar PDFs have cases like "COST04-BP03 Decommission resources"
    and "COST04-BP04 Decommission resources automatically" both landing
    on page 75. Collapsing same-page entries indiscriminately (as an
    earlier fix did) drops one sibling's heading entirely and mislabels
    its content under the other's — confirmed in 5 of 6 real pillar
    PDFs. Both siblings must keep their own section here, even though
    that means near-identical text, because a correct citation under
    duplicate content is far less harmful than a wrong citation under
    merged content."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 750, "Decommission resources")
    pdf.drawString(72, 730, "BP03 text: manually decommission unused resources.")
    pdf.drawString(72, 710, "BP04 text: automatically decommission unused resources.")
    pdf.showPage()
    pdf.drawString(72, 750, "Next best practice")
    pdf.drawString(72, 730, "Content on the following page.")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    category = writer.add_outline_item("Decommission resources", 0)
    writer.add_outline_item("COST04-BP03 Decommission resources", 0, parent=category)
    writer.add_outline_item("COST04-BP04 Decommission resources automatically", 0, parent=category)
    writer.add_outline_item("Next best practice", 1)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_pdf_bytes_with_a_broken_entry_between_valid_siblings() -> bytes:
    """Reproduces a real 2026-09-14 finding on the WAF Operational
    Excellence pillar PDF: a broken outline entry (resolving before its
    own parent's page, so it gets dropped) sits between two valid sibling
    subtrees at the same depth. A naive "track the last page seen at each
    depth" check can let a *grandchild* of the broken entry validate
    itself against a stale page left over from the unrelated, earlier
    valid sibling instead of being dropped along with its broken parent —
    which is exactly what happened to "Implementation steps" entries
    nested under a broken "Implementation guidance" entry in the real
    document, producing duplicate content across unrelated best
    practices."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for i in range(6):
        pdf.drawString(72, 750, f"Page {i} heading text")
        pdf.drawString(72, 730, f"Body content unique to page {i}.")
        pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    root_a = writer.add_outline_item("Root A", 0)
    writer.add_outline_item("Child A", 1, parent=root_a)
    root_b = writer.add_outline_item("Root B", 5)
    broken_child_b = writer.add_outline_item("Broken child B", 2, parent=root_b)
    writer.add_outline_item("Grandchild of broken child B", 3, parent=broken_child_b)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_pdf_bytes_with_bullet_list() -> bytes:
    """A section whose page text is a numbered list — end-to-end coverage
    that normalize_pdf's block segmentation reaches real pypdf-extracted
    text, not just the helper function in isolation. Uses digits rather
    than the real corpus's "•" glyph because reportlab's standard
    Helvetica font (no embedded ToUnicode CMap) doesn't round-trip that
    glyph through pypdf's extraction — the "•" case itself is already
    covered directly against real extracted corpus text in
    test_real_bullet_list_text_is_segmented_into_a_list_block, which
    needs no PDF rendering."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 750, "Related best practices")
    pdf.drawString(72, 730, "1. Aware of service quotas and constraints")
    pdf.drawString(72, 710, "2. Manage service quotas across accounts and regions")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    writer.add_outline_item("Related best practices", 0)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_sample_iam_doc_html(long_paragraph_sentences: int = 200) -> str:
    long_paragraph = " ".join(
        f"Sentence number {i} explains one small detail about IAM permission boundaries."
        for i in range(long_paragraph_sentences)
    )
    return f"""
    <html><body>
    <h1>Security best practices in IAM</h1>
    <p>This guide describes recommended practices for using AWS Identity
    and Access Management.</p>
    <h2>Multi-factor authentication</h2>
    <p>Require MFA for all human users with console access.</p>
    <h2>Least privilege</h2>
    <p>Grant only the permissions required to perform a task.</p>
    <table>
      <tr><th>Policy</th><th>Scope</th></tr>
      <tr><td>AdministratorAccess</td><td>Account</td></tr>
    </table>
    <h3>Access Analyzer</h3>
    <pre>aws accessanalyzer create-analyzer --analyzer-name example</pre>
    <ul>
      <li>Enable Access Analyzer in every Region</li>
      <li>Review findings regularly</li>
    </ul>
    <h2>Long section</h2>
    <p>{long_paragraph}</p>
    </body></html>
    """
