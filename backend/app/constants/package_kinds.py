"""Package kinds and the 7.02.5 section roles (023).

A lesson package is either a `video` — the program is the narrated video,
its words are whatever the manifest declares — or `text`: a study guide
whose sections are the program, with optional supplemental videos.

The roles exist to make 7.02.5's exclusion list structural rather than a
matter of author honesty. 7.02.5 names what is *not* critical to the
stated learning objectives and therefore not counted: "course
introduction, instructions to the participant, author/course developer
biographies, table of contents, glossary, pre-program assessment, and
appendixes containing supplementary reference materials." Each of those
has a role here that is not `body`, and only `body` words reach the
formula.
"""

KIND_VIDEO = "video"
KIND_TEXT = "text"
PACKAGE_KINDS = (KIND_VIDEO, KIND_TEXT)

# Absent `kind` in a manifest means video: every package exported before
# the 023 contract change stays valid and ingests unchanged.
DEFAULT_KIND = KIND_VIDEO

ROLE_FRONT_MATTER = "front_matter"
ROLE_BODY = "body"
ROLE_GLOSSARY = "glossary"
ROLE_APPENDIX = "appendix"
SECTION_ROLES = (ROLE_FRONT_MATTER, ROLE_BODY, ROLE_GLOSSARY, ROLE_APPENDIX)

# 7.02.5: the one role whose words enter the word count formula.
COUNTED_ROLE = ROLE_BODY

# Roles a participant may reach at any time without answering anything:
# they are reference, not required reading — the same reason they are
# excluded from the count. Body sections gate (5.01.2.1).
UNGATED_ROLES = (ROLE_FRONT_MATTER, ROLE_GLOSSARY, ROLE_APPENDIX)

ROLE_LABELS = {
    ROLE_FRONT_MATTER: "Front matter",
    ROLE_BODY: "Body",
    ROLE_GLOSSARY: "Glossary",
    ROLE_APPENDIX: "Appendix",
}

# How a lesson's word count was arrived at, recorded on the package and
# printed in the 9.02.2(2)(ii) calculation record. The distinction is the
# whole point of 023's ingestion change: for text packages superCPE counts
# the shipped words itself, for video packages it still takes the
# manifest's number on trust (7.02.8 leaves the sponsor responsible for
# reviewing a developer's figure either way).
WORD_COUNT_COMPUTED = "computed"
WORD_COUNT_MANIFEST = "manifest"
WORD_COUNT_SOURCES = (WORD_COUNT_COMPUTED, WORD_COUNT_MANIFEST)
