from .rbac import ROLE_OPERATOR, user_role


class StationModeMiddleware:
    """Expose whether this request belongs to a locked production terminal."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        terminal_session = bool(request.session.get('station_terminal', False))
        request.is_station_mode = bool(
            request.user.is_authenticated
            and (user_role(request.user) == ROLE_OPERATOR or terminal_session)
        )
        return self.get_response(request)


class AuditUserMiddleware:
    """Bind the authenticated request user to audit signals for the duration of the request.

    Any model save/delete that happens during the request will be attributed
    to the request user. Anonymous requests produce audit entries with
    `username=''` and `user=NULL`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .signals import bind_audit_user
        with bind_audit_user(getattr(request, 'user', None)):
            return self.get_response(request)
