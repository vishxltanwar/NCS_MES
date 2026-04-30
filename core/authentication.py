# core/authentication.py
# CSRF-exempt session authentication for DRF API views.
# The frontend JS uses fetch() with JSON body, which doesn't include CSRF tokens.
# This mirrors the original FastAPI behaviour (which had no CSRF).
from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth that skips CSRF enforcement for DRF API views."""

    def enforce_csrf(self, request):
        return  # Skip CSRF check
