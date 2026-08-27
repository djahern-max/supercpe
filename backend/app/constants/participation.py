"""The 4.02 licensed-participation rule, field by field.

4.02: "The participation of at least one licensed CPA (in good standing and
holding an active license or the equivalent of an 'active' CPA license in a
U.S. jurisdiction) is required in the development of every program in
accounting and auditing. The participation of at least one licensed CPA,
tax attorney, or IRS enrolled agent ... is required in the development of
each program in the field of study of taxes." Either the developer or the
reviewer satisfies it ("Whether to have this individual involved during the
development or the review process is at the CPE program sponsor's
discretion").

Field names match `app/constants/fields_of_study.py`. The governmental
variants are included because a governmental accounting or auditing program
is a program in accounting or auditing; 4.02 speaks of the subject, not the
NASBA catalog line.
"""

# Fields where 4.02 requires an active licensed CPA.
CPA_PARTICIPATION_FIELDS = frozenset(
    {
        "Accounting",
        "Accounting (Governmental)",
        "Auditing",
        "Auditing (Governmental)",
    }
)

# Fields where 4.02 accepts a CPA, tax attorney, or IRS enrolled agent.
TAX_PARTICIPATION_FIELDS = frozenset({"Taxes"})

# The credential_type values that satisfy each rule (license_status must be
# active in every case).
CPA_QUALIFYING_CREDENTIALS = frozenset({"cpa"})
TAX_QUALIFYING_CREDENTIALS = frozenset({"cpa", "tax_attorney", "enrolled_agent"})
