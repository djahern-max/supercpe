"""Certificate facts fixed by Section 9 of the 2026 Standards."""

# 9.01 item 10: every certificate carries a "NASBA time statement stating
# that CPE credits have been granted on a 50-minute hour". NASBA fixes the
# substance of the wording; a sponsor has no reason to vary it, so it is a
# constant, not a profile field.
TIME_STATEMENT = "CPE credits have been granted based on a 50-minute hour."

# The sponsor-level fields a certificate cannot be issued without:
# 9.01 item 1 (CPE program sponsor name) and item 8 (NASBA sponsor
# identification number). Item 9 (state registration number) is conditional
# on the state boards, so state registrations are not in this list.
CERTIFICATE_SPONSOR_FIELDS = ["name", "national_registry_id"]

# The fields issuance actually gates on (010): item 1 and 9.01.1's awarding
# entity. Item 8 is deliberately NOT here — a sponsor that is not on the
# National Registry may still issue certificates; it simply cannot print a
# sponsor ID, and Phase B's NASBA application needs a sample certificate
# before membership exists. Item 8 gates on `may_claim_registry` instead,
# snapshotted at completion.
ISSUANCE_SPONSOR_FIELDS = ["name", "legal_name"]

# 9.01 item 6: type of formal learning program. Deliberately "Self study",
# not "QAS Self Study": QAS is a National Registry program designation
# superCPE may not use until `registry_status` is registered (Phase C).
PROGRAM_TYPE = "Self study"

# 8.01 item 11: the official NASBA sponsor statement, "if an approved NASBA
# sponsor". The Registry's standard wording, with the sponsor's name filled
# in at render time. This text may ONLY be rendered while
# `SponsorProfile.may_claim_registry` is true — anywhere else it is a false
# claim of Registry membership; `services.policies.sponsor_statement` is
# the one place that gates it.
NASBA_SPONSOR_STATEMENT = (
    "{sponsor_name} is registered with the National Association of State "
    "Boards of Accountancy (NASBA) as a sponsor of continuing professional "
    "education on the National Registry of CPE Sponsors. State boards of "
    "accountancy have final authority on the acceptance of individual "
    "courses for CPE credit. Complaints regarding registered sponsors may "
    "be submitted to the National Registry of CPE Sponsors through its "
    "website: www.nasbaregistry.org."
)
