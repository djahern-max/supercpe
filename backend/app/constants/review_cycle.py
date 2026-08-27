"""Review currency periods fixed by 4.01 of the 2026 Standards.

4.01: courses in subjects that undergo frequent changes "must be reviewed
and revised, as necessary, by a subject matter expert as soon as possible
but at least once a year"; other courses "at least every two years". Which
cycle a course is on is the admin's judgment, stored on the course; the due
date is always derived from the current review's date plus these periods,
never stored.
"""

ANNUAL_REVIEW_DAYS = 365
BIENNIAL_REVIEW_DAYS = 730

REVIEW_CYCLE_DAYS = {
    "annual": ANNUAL_REVIEW_DAYS,
    "biennial": BIENNIAL_REVIEW_DAYS,
}
