"""Certificate of completion rendering (9.01).

`render` takes the frozen `certificate_snapshot` dict and nothing else —
deliberately no db session — so a certificate can only ever print what was
true when the credit was earned. Re-rendering the same snapshot produces
the same text content (asserted by test); byte identity is not required
(the PDF carries a creation timestamp in its metadata).

fpdf2 is pure Python with no system dependencies. Its built-in Helvetica
covers Latin-1 only, so text is sanitized with replacement characters
rather than crashing on an exotic character in a name or title.
"""

from fpdf import FPDF

_PAGE_WIDTH = 216  # letter, mm
_MARGIN = 20
_BODY_WIDTH = _PAGE_WIDTH - 2 * _MARGIN


def _latin1(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


class _Certificate(FPDF):
    def __init__(self):
        super().__init__(format="letter")
        self.set_auto_page_break(auto=False)
        self.set_margins(_MARGIN, _MARGIN)
        self.add_page()

    def line_out(self, text: str, size: int = 11, style: str = "", gap: int = 6):
        self.set_font("helvetica", style, size)
        self.multi_cell(_BODY_WIDTH, gap, _latin1(text), align="C")

    def spacer(self, height: int = 4):
        self.ln(height)


def render(snapshot: dict) -> bytes:
    """One page from the snapshot dict: the eleven 9.01 items in reading
    order. Item 5 (location) prints as not applicable for self study; item
    8 prints only when the snapshot carries it."""
    pdf = _Certificate()

    # Items 1 and 9.01.1: the sponsor, and the entity awarding the credit.
    pdf.line_out(snapshot["sponsor_name"], size=20, style="B", gap=9)
    if (
        snapshot["sponsor_legal_name"]
        and snapshot["sponsor_legal_name"] != snapshot["sponsor_name"]
    ):
        pdf.line_out(snapshot["sponsor_legal_name"], size=11)
    pdf.spacer(6)

    pdf.line_out("Certificate of Completion", size=16, style="B", gap=8)
    pdf.spacer(4)

    pdf.line_out("This certifies that", size=10)
    # Item 2: the participant.
    pdf.line_out(
        snapshot["participant_name"] or snapshot["participant_email"],
        size=15,
        style="B",
        gap=8,
    )
    pdf.line_out("has satisfactorily completed the qualified assessment for", size=10)
    # Item 3: the course.
    pdf.line_out(snapshot["course_title"], size=14, style="B", gap=8)
    pdf.line_out(f"Course code: {snapshot['course_code']}", size=10)
    pdf.spacer(6)

    # Items 4, 5, 6, 7.
    pdf.line_out(f"Completion date: {snapshot['completed_at'][:10]}", size=11)
    pdf.line_out("Location: Not applicable (self study)", size=11)
    pdf.line_out(f"Type of learning program: {snapshot['program_type']}", size=11)
    pdf.line_out(
        f"CPE credit: {snapshot['credit']} in {snapshot['field_of_study']}",
        size=11,
        style="B",
    )
    pdf.spacer(4)

    # Item 10: the NASBA time statement, verbatim.
    pdf.line_out(snapshot["time_statement"], size=10, style="I")

    # Item 8: only when the sponsor could claim it at completion.
    if snapshot["national_registry_id"]:
        pdf.line_out(
            "National Registry of CPE Sponsors ID: "
            f"{snapshot['national_registry_id']}",
            size=10,
        )

    # Item 9: state registration numbers, as held.
    for registration in snapshot["state_registrations"]:
        pdf.line_out(
            f"{registration['state']} sponsor registration number: "
            f"{registration['number']}",
            size=10,
        )

    # Item 11: any other statements required by boards of accountancy.
    for statement in snapshot["other_statements"]:
        pdf.line_out(statement, size=10)
    pdf.spacer(6)

    people = []
    if snapshot["developed_by"]:
        people.append(f"Developed by {_person(snapshot['developed_by'])}")
    if snapshot["reviewed_by"]:
        people.append(f"Reviewed by {_person(snapshot['reviewed_by'])}")
    if people:
        pdf.line_out(". ".join(people) + ".", size=9)
    pdf.spacer(8)

    pdf.line_out(f"Certificate number: {snapshot['certificate_number']}", size=10)
    # 018's public verification page will resolve this URL.
    pdf.line_out(
        f"Verify at supercpe.com/verify/{snapshot['verification_token']}",
        size=8,
    )

    return bytes(pdf.output())


def _person(person: dict) -> str:
    if person.get("credentials"):
        return f"{person['name']}, {person['credentials']}"
    return person["name"]
