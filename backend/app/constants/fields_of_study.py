"""NASBA fields of study that qualify for CPE.

Transcribed from `docs/2024-Fields-of-Study.pdf` ("Fields of Study That
Qualify for Continuing Professional Education", January 2024). The value is
True where NASBA classifies the field as technical, False where it is
non-technical — read by 020's jurisdiction hint, which quotes a board's
non-technical cap only for non-technical fields
(`app/services/jurisdictions.py`).
"""

FIELDS_OF_STUDY: dict[str, bool] = {
    # Technical
    "Accounting": True,
    "Accounting (Governmental)": True,
    "Auditing": True,
    "Auditing (Governmental)": True,
    "Business Law": True,
    "Economics": True,
    "Finance": True,
    "Information Technology": True,
    "Management Services": True,
    "Regulatory Ethics": True,
    "Specialized Knowledge": True,
    "Statistics": True,
    "Taxes": True,
    # Non-technical
    "Behavioral Ethics": False,
    "Business Management & Organization": False,
    "Communications and Marketing": False,
    "Computer Software & Applications": False,
    "Personal Development": False,
    "Personnel/Human Resources": False,
    "Production": False,
}
