"""Program knowledge levels under the 2026 Statement on Standards.

3.01.1: "Knowledge levels consist of Basic, Intermediate, Advanced, Update,
and Overview."

3.02.1: "All programs identified as Intermediate, Advanced or Update must
clearly identify prerequisite education, experience, and advance preparation
in precise language." For Basic and Overview, prerequisites and advance
preparation "should be noted if applicable, otherwise, state 'none'".
"""

KNOWLEDGE_LEVELS: tuple[str, ...] = (
    "Basic",
    "Intermediate",
    "Advanced",
    "Update",
    "Overview",
)

LEVELS_REQUIRING_PREREQUISITES: tuple[str, ...] = (
    "Intermediate",
    "Advanced",
    "Update",
)

# 3.02.1 wants "none" stated, not omitted; a blank value on a Basic or
# Overview lesson is stored as this literal.
PREREQUISITES_NONE: str = "None"
