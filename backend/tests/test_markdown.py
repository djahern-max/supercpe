"""Feature 035: HTML comments are authoring annotations, not reading.

`strip_html_comments` is the one place a comment is removed, and every
caller that shows, indexes, or measures section text goes through it. The
rules it has to keep, in order of how easy they are to get wrong:

- a comment in prose goes, however many there are and however many lines
  one spans;
- a comment inside a fenced block or an inline code span *stays*, because
  a guide that teaches HTML has to be able to print one;
- an unclosed `<!--` stays, because it is not a comment;
- removing one never fuses the words that were on either side of it.
"""

from app.services.markdown import strip_html_comments
from app.services.word_count import count_words


# --- prose: the comment goes ------------------------------------------------


def test_a_single_line_comment_is_removed():
    source = "Alpha beta.\n\n<!-- index: 9#1, 9#2; 4#3 attributed -->\n\nGamma.\n"
    stripped = strip_html_comments(source)
    assert "<!--" not in stripped
    assert "attributed" not in stripped
    assert "Alpha beta." in stripped and "Gamma." in stripped


def test_a_multi_line_comment_is_removed():
    source = "Alpha\n\n<!-- index: 9#1,\n     9#2; 4#3 attributed -->\n\nbeta\n"
    stripped = strip_html_comments(source)
    assert "<!--" not in stripped and "-->" not in stripped
    assert "attributed" not in stripped
    assert "Alpha" in stripped and "beta" in stripped


def test_several_comments_in_one_section_all_go():
    source = "<!-- one -->\nAlpha <!-- two --> beta\n\n<!-- three -->\ngamma\n"
    stripped = strip_html_comments(source)
    assert "<!--" not in stripped
    for note in ("one", "two", "three"):
        assert note not in stripped
    for word in ("Alpha", "beta", "gamma"):
        assert word in stripped


def test_a_comment_between_two_words_leaves_one_space():
    """The neighbours were two words before; they must still be two after,
    or the count and any search over them would be wrong."""
    assert strip_html_comments("Alpha<!-- note -->Beta") == "Alpha Beta"
    assert count_words("Alpha<!-- note -->Beta") == 2


def test_a_comment_already_separated_by_whitespace_adds_nothing():
    assert strip_html_comments("Alpha <!-- note --> Beta") == "Alpha  Beta"
    assert strip_html_comments("<!-- note -->\nAlpha") == "\nAlpha"
    assert strip_html_comments("Alpha\n<!-- note -->") == "Alpha\n"


# --- code: the comment is content -------------------------------------------


def test_a_comment_inside_a_fenced_block_is_preserved():
    source = "Alpha\n\n```html\n<!-- this is the lesson -->\n```\n\nbeta\n"
    assert strip_html_comments(source) == source


def test_a_tilde_fence_protects_a_comment_too():
    source = "Alpha\n\n~~~html\n<!-- this is the lesson -->\n~~~\n\nbeta\n"
    assert strip_html_comments(source) == source


def test_a_comment_inside_inline_code_is_preserved_and_counted():
    source = "An HTML comment looks like `<!-- a note -->` in the source.\n"
    assert strip_html_comments(source) == source
    # "a" and "note" are words of the guide here, not an annotation:
    # 8 prose words + the 2 inside the code span. The `<!--` and `-->`
    # marks hold no letter or digit, so they are not words either way.
    assert count_words(source) == 10


def test_a_code_span_inside_a_comment_does_not_protect_the_comment():
    """The comment opened first, so the backticks are part of the note."""
    stripped = strip_html_comments("Alpha <!-- see `here` first --> beta")
    assert "<!--" not in stripped
    assert "here" not in stripped


# --- not a comment ----------------------------------------------------------


def test_an_unclosed_comment_opener_is_left_alone():
    source = "Alpha <!-- never closed beta\n"
    assert strip_html_comments(source) == source
    # It stays text, so the words after the typo still count.
    assert count_words(source) == 4


def test_a_bare_arrow_is_left_alone():
    source = "The pointer --> is not a comment.\n"
    assert strip_html_comments(source) == source


def test_other_raw_html_is_not_removed():
    """Only comments go. A tag is still text, for the renderer to escape —
    nothing here makes raw HTML renderable."""
    source = "Alpha <b>bold</b> and <script>alert(1)</script> beta\n"
    assert strip_html_comments(source) == source


def test_markdown_without_comments_is_returned_unchanged():
    source = "# Heading\n\nAlpha beta gamma.\n\n- one\n- two\n"
    assert strip_html_comments(source) == source


# --- the 7.02.6 rule --------------------------------------------------------


def test_a_comment_never_changes_the_word_count():
    """7.02.6 divides "the word count for the text of the required
    reading" by 180. An annotation is not required reading, so the section
    must measure exactly as it would without it."""
    plain = (
        "# Identifying a Lease\n\n"
        "A contract is, or contains, a lease when it conveys the right to\n"
        "control the use of an identified asset.\n"
    )
    annotated = (
        "# Identifying a Lease\n\n"
        "<!-- index: 9#1, 9#2; 4#3 attributed -->\n"
        "A contract is, or contains, a lease when it conveys the right to\n"
        "control the use of an identified asset.\n"
    )
    assert count_words(annotated) == count_words(plain)


def test_comment_words_are_not_findable_in_the_stripped_prose():
    """What `search` matches over. A word that appears only in an
    annotation is not in the guide."""
    from app.services.word_count import strip_markdown

    prose = strip_markdown("Alpha <!-- 4#3 attributed --> beta\n")
    assert "attributed" not in prose
    assert "Alpha" in prose and "beta" in prose
