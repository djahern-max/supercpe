"""Keyword search and the glossary lookup — 4.05.3 items 2 and 3 (023).

4.05.3 lists what instructional materials must include at a minimum. Two
of those items were superCPE's longest-standing application-blocking gap:

  2) The ability to find information quickly (for example, an index or key
     word search function)
  3) The definition of key terms (for example, a glossary or a search
     function that takes a participant to the definition of a key word)

Both are natural over a study guide and awkward over a video, which is
part of why the text-first pivot closes them. This module is both: `find`
searches the guide text of a course's text lessons and returns section
hits with snippets; `glossary` returns the key terms, optionally narrowed
to a lookup, so a participant reading a section can reach a definition
without leaving the reader.

**Search never touches questions.** It reads `package_sections` and
nothing else. A search index over question stems would be an
answer-adjacent payload the browser could query at will, which is exactly
what the player has refused since 006 — so the rule here is structural
rather than a filter: there is no question text in scope to leak.

Matching is plain and case-insensitive over the stripped prose of each
section, so a hit is never inside a URL or a code fence. Simple term
matching with section-level results is what the Standard's own example
asks for; nothing here needs a search engine.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.lesson_package import LessonPackage
from app.services import word_count as word_count_service

# How much prose to return around a hit, and how many hits per section.
# Enough to recognize the passage, not enough to be a way of reading a
# gated section through the search box.
SNIPPET_RADIUS = 90
MAX_SNIPPETS_PER_SECTION = 3
MIN_QUERY_LENGTH = 2


@dataclass
class SearchHit:
    package_id: int
    lesson_id: str
    section_key: str
    section_title: str
    role: str
    snippets: list[str]
    match_count: int


@dataclass
class GlossaryEntry:
    term: str
    definition: str
    package_id: int
    lesson_id: str
    section_key: str | None


def _text_packages(packages: list[LessonPackage]) -> list[LessonPackage]:
    return [p for p in packages if p.is_text]


def find(
    db: Session, packages: list[LessonPackage], query: str
) -> list[SearchHit]:
    """Sections of these lessons whose prose contains `query`, in reading
    order. An empty or too-short query finds nothing rather than
    everything."""
    term = query.strip()
    if len(term) < MIN_QUERY_LENGTH:
        return []
    pattern = re.compile(re.escape(term), re.IGNORECASE)

    hits: list[SearchHit] = []
    for package in _text_packages(packages):
        for section in package.sections:
            prose = " ".join(
                word_count_service.strip_markdown(section.markdown).split()
            )
            matches = list(pattern.finditer(prose))
            if not matches:
                continue
            hits.append(
                SearchHit(
                    package_id=package.id,
                    lesson_id=package.lesson_id,
                    section_key=section.section_key,
                    section_title=section.title,
                    role=section.role,
                    snippets=[
                        _snippet(prose, match)
                        for match in matches[:MAX_SNIPPETS_PER_SECTION]
                    ],
                    match_count=len(matches),
                )
            )
    return hits


def _snippet(prose: str, match: re.Match) -> str:
    """A window of prose around one hit, trimmed to whole words and
    ellipsed where it was cut. The caller highlights the query itself —
    no marker protocol to get wrong, and nothing to unescape."""
    start = max(0, match.start() - SNIPPET_RADIUS)
    end = min(len(prose), match.end() + SNIPPET_RADIUS)
    if start > 0:
        space = prose.find(" ", start)
        start = space + 1 if 0 <= space < match.start() else start
    if end < len(prose):
        space = prose.rfind(" ", match.end(), end)
        end = space if space > match.end() else end
    return (
        ("… " if start > 0 else "")
        + prose[start:end].strip()
        + (" …" if end < len(prose) else "")
    )


def glossary(
    packages: list[LessonPackage], term: str | None = None
) -> list[GlossaryEntry]:
    """The key terms of these lessons, alphabetically. `term` narrows to
    the lookup 4.05.3 item 3 describes — "a search function that takes a
    participant to the definition of a key word" — matching a term that
    equals or starts with what was typed, case-insensitively."""
    needle = (term or "").strip().lower()
    entries = [
        GlossaryEntry(
            term=row.term,
            definition=row.definition,
            package_id=package.id,
            lesson_id=package.lesson_id,
            section_key=row.section_key,
        )
        for package in _text_packages(packages)
        for row in package.glossary_terms
    ]
    if needle:
        exact = [e for e in entries if e.term.lower() == needle]
        entries = exact or [
            e for e in entries if e.term.lower().startswith(needle)
        ]
    return sorted(entries, key=lambda e: (e.term.lower(), e.lesson_id))
