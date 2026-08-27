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
