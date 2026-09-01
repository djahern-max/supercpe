"""Counting the words of a study guide section (7.02.5, 7.02.6).

7.02.6 divides "the word count for the text of the required reading of the
program" by 180. 7.02.5 says that count "begins with a word count of the
number of words contained in the text of the required reading" and
"should exclude any material not critical to the achievement of the stated
learning objectives."

Two separate jobs, and this module does only the first: *how many words
are in this text*. *Which sections are required reading* is answered
structurally by the section role — only `body` sections are counted, and
the caller sums those (see `services.packages`). Keeping them apart is
deliberate: the exclusion must not depend on a heuristic reading of the
prose.

What is stripped before counting is markdown machinery and material that
is not prose a participant reads: fences, HTML, image URLs, link targets,
and the punctuation of lists, tables, headings, and emphasis. What is kept
is every word that would be read aloud, including headings and the text of
a link. The rules are written out in `docs/course-package.md` so an author
can hand-count a section and get superCPE's number, and are applied to the
markdown exactly as shipped in the package — never to a re-rendered or
re-formatted copy.

Nothing here rounds, estimates, or samples: a word is a whitespace-
delimited token containing at least one letter or digit.
"""

import re

# Fenced code blocks, both fence characters, with any info string. Code is
# not prose the participant reads at 180 words a minute.
_FENCED_CODE = re.compile(r"^(?P<fence>```+|~~~+).*?(?:\n(?P=fence)[^\n]*$|\Z)", re.M | re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# Images carry a URL and an alt string that is a caption, not body prose.
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_IMAGE_REF = re.compile(r"!\[[^\]]*\]\[[^\]]*\]")
# Links keep their text and lose their target.
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]]*)\]\[[^\]]*\]")
# `[ref]: https://example.com "title"` on its own line.
_LINK_DEFINITION = re.compile(r"^[ \t]*\[[^\]]+\]:[^\n]*$", re.M)
_AUTOLINK = re.compile(r"<https?://[^>]*>", re.I)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
# Setext underlines and horizontal rules: rows of -, =, *, _ alone.
_RULE_LINE = re.compile(r"^[ \t]*(?:[-=*_][ \t]*){3,}$", re.M)
# Table delimiter rows: | --- | :--: |
_TABLE_DELIMITER = re.compile(r"^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(?:\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$", re.M)
_LEADING_MARKS = re.compile(r"^[ \t]*(?:[>#]+[ \t]*|[-+*][ \t]+|\d+[.)][ \t]+)+", re.M)
# Emphasis, strikethrough, inline-code backticks, and table pipes. The
# words between them are kept; only the marks go.
_INLINE_MARKS = re.compile(r"[*_~`|]")
# A token is a word if it contains a letter or a digit — so "—", "|", and
# a bare "..." do not inflate a count, and "ASC" and "842-10-15" do.
_HAS_ALNUM = re.compile(r"[^\W_]", re.UNICODE)


def strip_markdown(markdown: str) -> str:
    """The prose of a markdown section, with the machinery removed.

    Also what the keyword search (4.05.3 item 2) matches and snippets
    from, so a participant never sees a hit inside a URL."""
    text = _HTML_COMMENT.sub(" ", markdown)
    text = _FENCED_CODE.sub(" ", text)
    text = _LINK_DEFINITION.sub(" ", text)
    text = _IMAGE.sub(" ", text)
    text = _IMAGE_REF.sub(" ", text)
    text = _INLINE_LINK.sub(r"\1", text)
    text = _REF_LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    text = _RULE_LINE.sub(" ", text)
    text = _TABLE_DELIMITER.sub(" ", text)
    text = _LEADING_MARKS.sub("", text)
    text = _INLINE_MARKS.sub(" ", text)
    return text


def count_words(markdown: str) -> int:
    """Words in one section's shipped markdown."""
    return sum(1 for token in strip_markdown(markdown).split() if _HAS_ALNUM.search(token))
