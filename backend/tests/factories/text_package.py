"""Builds a valid *text* package zip on disk for tests (023).

The hand-made fixture the 023 spec calls for: front matter, three body
sections, a glossary of five terms, an appendix, one supplemental video,
five review questions and four assessment questions. Overrides let a test
break one thing at a time; the content hash is computed correctly unless
a test asks otherwise.

The body sections' words are hand-countable on purpose — BODY_ONE has a
known count that a test asserts against, so the counting rules stay
something an author can reproduce with a pen.
"""

import json
import zipfile
from pathlib import Path

from app.services.packages import compute_text_content_hash
from tests.factories.package import _deep_merge, _video_bytes

DEFAULT_LESSON_ID = "ASC842-GDE-01"
DEFAULT_COURSE_CODE = "ASC842-GDE"

FRONT_MATTER = """## How this course works

This is a self study CPE program. The study guide below is the program;
read it in order. Answer the review question after each section to open
the next one. The glossary and the appendix are reference material and
are available at any time.

When every review question has been answered, the qualified assessment
opens from the course page.
"""

# Hand-counted: 3 (heading) + 29 + 22 + 10 = 64 countable words. The fenced
# code block, the image, and the link's URL are stripped before counting;
# the link's text ("the codification") and the heading's words are kept.
# test_text_packages asserts the counter agrees, so the rules in
# docs/course-package.md stay something an author can reproduce with a pen.
BODY_ONE = """# Identifying a Lease

A contract is, or contains, a lease when it conveys the right to control
the use of an identified asset for a period of time in exchange for
consideration. Control means both the right to obtain substantially all
of the economic benefits from use and the right to direct that use.

See [the codification](https://asc.fasb.org/842-10-15-3) for the full
text of this criterion.

![diagram](media/not-a-real-image.png)

```python
# not counted
identified_asset = True
```
"""
BODY_ONE_WORDS = 64

BODY_TWO = """# Identified Asset

An asset is identified when it is explicitly or implicitly specified in
the contract. A supplier's substantive substitution right defeats
identification.
"""

BODY_THREE = """# Right to Direct Use

The customer directs the use of an identified asset when it decides how
and for what purpose the asset is used throughout the period of use.
"""

GLOSSARY = """# Glossary

Definitions of the key terms used in this guide. See the manifest's
glossary_terms for the machine-readable copy superCPE renders.
"""

APPENDIX = """# Appendix A — ASC 842-10-15 in full

Reference material, reproduced for convenience. Excluded from the word
count under 7.02.5 as an appendix of supplementary reference material.
"""

DEFAULT_SECTION_FILES = {
    "guide/00-front-matter.md": FRONT_MATTER,
    "guide/01-identifying-a-lease.md": BODY_ONE,
    "guide/02-identified-asset.md": BODY_TWO,
    "guide/03-right-to-direct-use.md": BODY_THREE,
    "guide/90-glossary.md": GLOSSARY,
    "guide/91-appendix-a.md": APPENDIX,
}


def default_sections() -> list:
    return [
        {
            "id": "sec-00",
            "file": "guide/00-front-matter.md",
            "role": "front_matter",
            "title": "How this course works",
        },
        {
            "id": "sec-01",
            "file": "guide/01-identifying-a-lease.md",
            "role": "body",
            "title": "Identifying a Lease",
        },
        {
            "id": "sec-02",
            "file": "guide/02-identified-asset.md",
            "role": "body",
            "title": "Identified Asset",
        },
        {
            "id": "sec-03",
            "file": "guide/03-right-to-direct-use.md",
            "role": "body",
            "title": "Right to Direct Use",
        },
        {
            "id": "sec-90",
            "file": "guide/90-glossary.md",
            "role": "glossary",
            "title": "Glossary",
        },
        {
            "id": "sec-91",
            "file": "guide/91-appendix-a.md",
            "role": "appendix",
            "title": "Appendix A — ASC 842-10-15 in full",
        },
    ]


def default_media() -> list:
    return [
        {
            "id": "vid-01",
            "file": "media/ex-01.mp4",
            "placement": {"after_section": "sec-02"},
            "av_is_additional_learning": True,
            "duration_seconds": None,
        }
    ]


def default_glossary_terms() -> list:
    return [
        {
            "term": "Right-of-use asset",
            "definition": (
                "An asset that represents a lessee's right to use an "
                "underlying asset for the lease term."
            ),
            "section_id": "sec-90",
        },
        {
            "term": "Identified asset",
            "definition": (
                "An asset explicitly or implicitly specified in a contract "
                "for which the supplier has no substantive substitution "
                "right."
            ),
            "section_id": "sec-90",
        },
        {
            "term": "Period of use",
            "definition": (
                "The total period of time an asset is used to fulfil a "
                "contract with a customer."
            ),
            "section_id": "sec-90",
        },
        {
            "term": "Substantive substitution right",
            "definition": (
                "A supplier's practical ability to substitute an alternative "
                "asset throughout the period of use, from which it would "
                "benefit economically."
            ),
            "section_id": "sec-90",
        },
        {
            "term": "Short-term lease",
            "definition": (
                "A lease with a lease term of twelve months or less that "
                "contains no purchase option the lessee is reasonably "
                "certain to exercise."
            ),
            "section_id": "sec-90",
        },
    ]


def default_manifest() -> dict:
    return {
        "package_version": 1,
        "kind": "text",
        "lesson_id": DEFAULT_LESSON_ID,
        "course_code": DEFAULT_COURSE_CODE,
        "position": 1,
        "title": "Identifying a Lease Under ASC 842",
        "content_hash": "",  # filled in by build_text_package
        "learning_objectives": [
            {
                "id": "lo-1",
                "text": "Determine whether a contract contains a lease",
            },
            {
                "id": "lo-2",
                "text": "Identify the asset a lease conveys the right to use",
            },
        ],
        "field_of_study": "Accounting",
        "knowledge_level": "Intermediate",
        "prerequisites": "Basic familiarity with lease accounting",
        "advance_preparation": "None",
        "sections": default_sections(),
        "media": default_media(),
        "glossary_terms": default_glossary_terms(),
        "sources": [{"citation": "ASC 842-10-15-3", "role": "primary"}],
        "author": {
            "name": "Test Author",
            "credentials": "CPA",
            "license_jurisdiction": "NH",
            "license_number": "12345",
        },
    }


def _review(n: int, after_section: str, objective: str = "lo-1") -> dict:
    return {
        "id": f"q-r{n:02d}",
        "kind": "review",
        "after_section": after_section,
        "stem": f"Review question {n} about identifying a lease?",
        "choices": [
            {"id": "a", "text": f"Wrong answer {n}"},
            {"id": "b", "text": f"Right answer {n}"},
            {"id": "c", "text": f"Also wrong {n}"},
        ],
        "correct": "b",
        "feedback": (
            f"Feedback {n}: control means benefits plus direction; "
            "re-read the section above."
        ),
        "objective_ids": [objective],
    }


def _assessment(n: int, objective: str = "lo-2") -> dict:
    return {
        "id": f"q-a{n:02d}",
        "kind": "assessment",
        "stem": f"Assessment question {n} about the identified asset?",
        "choices": [
            {"id": "a", "text": f"Wrong {n}"},
            {"id": "b", "text": f"Right {n}"},
            {"id": "c", "text": f"Also wrong {n}"},
        ],
        "correct": "b",
        "feedback": f"Assessment feedback {n}.",
        "objective_ids": [objective],
    }


def default_questions() -> list:
    """Five review questions placed across the three body sections, and
    four assessment questions covering both objectives."""
    return [
        _review(1, "sec-01", "lo-1"),
        _review(2, "sec-01", "lo-2"),
        _review(3, "sec-02", "lo-2"),
        _review(4, "sec-02", "lo-1"),
        _review(5, "sec-03", "lo-1"),
        _assessment(1, "lo-1"),
        _assessment(2, "lo-2"),
        _assessment(3, "lo-1"),
        _assessment(4, "lo-2"),
    ]


def build_text_package(
    tmp_path: Path,
    *,
    manifest_overrides: dict | None = None,
    questions: list | None = None,
    section_files: dict[str, str] | None = None,
    extra_files: dict[str, bytes] | None = None,
    dir_name: str | None = None,
) -> Path:
    """Write a text package zip under tmp_path and return its path.

    `section_files` replaces the whole markdown set (pass a copy of
    DEFAULT_SECTION_FILES with one entry edited to change one section).
    `manifest_overrides` is deep-merged (the video factory's OMIT sentinel
    works here too, since the merge is shared).
    """
    manifest = default_manifest()
    if manifest_overrides:
        hash_overridden = "content_hash" in manifest_overrides
        manifest = _deep_merge(manifest, manifest_overrides)
    else:
        hash_overridden = False

    questions = questions if questions is not None else default_questions()
    questions_bytes = json.dumps(questions, indent=2).encode()
    files = dict(section_files or DEFAULT_SECTION_FILES)

    top = dir_name or manifest.get("lesson_id", DEFAULT_LESSON_ID)
    package_dir = tmp_path / "built-text" / top
    package_dir.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        path = package_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    video = _video_bytes()
    for item in manifest.get("media") or []:
        path = package_dir / item["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(video)

    if not hash_overridden:
        section_bytes = [
            (package_dir / s["file"]).read_bytes()
            for s in manifest.get("sections", [])
            if (package_dir / s["file"]).exists()
        ]
        media_bytes = [
            (package_dir / m["file"]).read_bytes()
            for m in (manifest.get("media") or [])
            if (package_dir / m["file"]).exists()
        ]
        manifest["content_hash"] = compute_text_content_hash(
            section_bytes, questions_bytes, media_bytes
        )

    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (package_dir / "questions.json").write_bytes(questions_bytes)
    for name, content in (extra_files or {}).items():
        path = package_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    zip_path = tmp_path / f"{top}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                zf.write(path, f"{top}/{path.relative_to(package_dir)}")
    return zip_path
