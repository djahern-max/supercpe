"""The Section 9 retention period.

9.02: "CPE program sponsors must retain adequate documentation (electronic
or paper) for a minimum of five years to support their compliance with
these Standards and the reports that may be required of participants."

The constant exists so the audit bundle and the admin can *state* the
retention date. Retention is a floor, and nothing is ever deleted
automatically after it.

038 reversed "superCPE keeps everything" for one thing only: once every
record referencing a package version is past this date, an admin may purge
that archived version's stored video and media files
(`services.package_lifecycle`). Its rows and every participant record are
still kept.
"""

RETENTION_YEARS = 5
