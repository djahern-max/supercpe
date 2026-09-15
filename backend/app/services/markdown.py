"""Section markdown as a participant sees it, not as the author wrote it.

video-tool writes authoring annotations into the guide as HTML comments —
`<!-- index: 9#1, 9#2; 4#3 attributed -->` marks which source paragraphs a
section was written from. They are notes between the author and the
exporter. A participant must never read them, and 7.02.6 must never count
them: Method 2 divides "the word count for the text of the required
reading of the program" by 180, and an annotation nobody is asked to read
is not required reading.

So this module holds the one function that removes them, and every place
that shows, indexes, or measures section text goes through it: the reader
payload (`services.reader`), the keyword search and its snippets
(`services.search`, via `strip_markdown`), and the word count
(`services.word_count`).

What it does *not* touch is the stored markdown. A section row keeps the
bytes that were shipped, the 023a content hash still covers them, and the
audit bundle still writes the author's file as written — an auditor
reading the retained materials sees the same file video-tool exported.
Stripping happens at read, index, and measure time only.

Two things that look like comments are not:

- A `<!--` inside a fenced block or an inline code span is *content*: a
  guide that teaches HTML has to be able to print one. Those spans are
  matched first here and handed back untouched, so the same `<!-- … -->`
  is an annotation in prose and a word in code.
- A `<!--` that is never closed is not a comment either. It stays as text
  and renders escaped, which is what an author needs to see to notice the
  typo.

Nothing here renders HTML or makes any other raw HTML safe to render.
`<b>` and `<script>` are still escaped by the renderer exactly as before;
this removes one kind of node, it does not open a door.
"""

import re

# A fenced block: three or more backticks or tildes, any info string, to
# the matching closing fence or the end of the document. Shared with
# `services.word_count`, which removes the whole block from a count —
# defined once so "what counts as a fence" cannot drift between the two.
FENCED_CODE = re.compile(
    r"^(?P<fence>```+|~~~+).*?(?:\n(?P=fence)[^\n]*$|\Z)", re.M | re.S
)

# Left to right, first match wins: a fenced block, then an inline code
# span (a run of backticks closed by an equal run), then a comment. The
# order is the precedence — a comment opening inside code never starts a
# comment, and a code span opening inside a comment never protects it.
_SCAN = re.compile(
    r"(?P<fenced>^(?P<fence>```+|~~~+).*?(?:\n(?P=fence)[^\n]*$|\Z))"
    r"|(?P<code>(?P<ticks>`+).+?(?P=ticks))"
    r"|(?P<comment><!--.*?-->)",
    re.M | re.S,
)


def _separator(source: str, start: int, end: int) -> str:
    """What to leave behind where a comment was.

    Nothing, when whitespace or an edge already separates the neighbours —
    removing it must not add a space that was not there. One space when it
    did not, so `Alpha<!-- note -->Beta` cannot become the single word
    `AlphaBeta` and inflate neither the count nor a search hit.
    """
    before = start == 0 or source[start - 1].isspace()
    after = end == len(source) or source[end].isspace()
    return "" if before or after else " "


def strip_html_comments(markdown: str) -> str:
    """`markdown` with its HTML comments removed.

    Multi-line comments and several comments in one section included;
    comments inside fenced or inline code kept, because there they are
    content; an unclosed `<!--` kept, because it is not a comment.
    """
    pieces: list[str] = []
    end = 0
    for match in _SCAN.finditer(markdown):
        pieces.append(markdown[end : match.start()])
        if match.group("comment") is None:
            # A fenced block or an inline code span: content, verbatim.
            pieces.append(match.group(0))
        else:
            pieces.append(_separator(markdown, match.start(), match.end()))
        end = match.end()
    pieces.append(markdown[end:])
    return "".join(pieces)
