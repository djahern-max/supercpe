"""Account, session, and site-mode constants.

Unlike the credit and question constants, none of these numbers are NASBA's:
the Standards say who must be identified (6.01, 9.02.2(1)) but not how long
a session lives or how many login attempts to allow. These are superCPE's
own choices and can change without touching any Standards locator.
"""

ROLES = ("participant", "reviewer", "admin")

SITE_MODES = ("coming_soon", "open")

# A session dies after this long without a request, and unconditionally
# after the absolute limit, whichever comes first.
SESSION_IDLE_MINUTES = 60
SESSION_ABSOLUTE_HOURS = 12

# After this many consecutive failed logins the account locks for
# LOCKOUT_MINUTES; a correct password during the lockout is still refused.
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

MIN_PASSWORD_LENGTH = 12

# The cookie carrying the raw session token; only its sha256 is stored.
SESSION_COOKIE = "supercpe_session"

# Email verification tokens (017): random bytes in the link (32 bytes =
# 256 bits), sha256-stored like session tokens, and a 48-hour life. One
# active token per account; a resend supersedes the prior. Sized so 017a's
# password reset can reuse the machinery unchanged.
VERIFICATION_TOKEN_BYTES = 32
VERIFICATION_TOKEN_HOURS = 48
