"""The Section 9 retention period.

9.02: "CPE program sponsors must retain adequate documentation (electronic
or paper) for a minimum of five years to support their compliance with
these Standards and the reports that may be required of participants."

The constant exists so the audit bundle and the admin can *state* the
retention date; nothing enforces deletion after it. Retention is a floor —
superCPE keeps everything.
"""

RETENTION_YEARS = 5
