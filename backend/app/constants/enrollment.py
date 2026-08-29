"""Enrollment and certificate-delivery numbers fixed by Section 9 of the
2026 Standards."""

# 9.02.2(3): "Course documentation must include an expiration date (the time
# by which the participant must complete the qualified assessment). For
# individual courses, the expiration date is no longer than one year from
# the date of purchase or enrollment." superCPE uses the full year
# uniformly; the longer "series of courses to achieve an integrated
# learning plan" allowance is not modeled.
ENROLLMENT_DAYS = 365

# 9.01: the certificate "should be provided as soon as possible and should
# not exceed 60 days (so that participants can report their earned CPE
# credits in a timely manner)". Reported as the `certificates_overdue`
# finding, not enforced.
CERTIFICATE_DEADLINE_DAYS = 60
