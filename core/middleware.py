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
