# core/pagination.py
# Lightweight pagination helpers for DRF function-based views.
# Avoids pulling in DRF's PageNumberPagination class (which expects a ListAPIView).

from urllib.parse import urlencode


def parse_pagination(request, default_page_size=50, max_page_size=200):
    """
    Parse `?page=N&page_size=M` from the request query string.
    Clamps page_size to [1, max_page_size]. Returns (page, page_size).
    """
    try:
        page = max(1, int(request.query_params.get('page', '1')))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(request.query_params.get('page_size', str(default_page_size)))
    except (TypeError, ValueError):
        page_size = default_page_size
    page_size = max(1, min(page_size, max_page_size))
    return page, page_size


def paginate_queryset(queryset, request, default_page_size=50, max_page_size=200):
    """
    Slice a queryset according to the request's page/page_size params and
    return (items, pagination_meta).

    The response shape mirrors DRF's PageNumberPagination so frontend code
    can read `count`, `page`, `page_size`, `total_pages`, `has_next`,
    `has_previous`, `next_url`, `previous_url`, `results`.
    """
    page, page_size = parse_pagination(request, default_page_size, max_page_size)
    total = queryset.count() if hasattr(queryset, 'count') else len(queryset)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size
    items = list(queryset[start:end])
    has_next = page < total_pages
    has_previous = page > 1

    def _build_url(target_page):
        if not target_page:
            return None
        params = request.query_params.copy()
        params['page'] = str(target_page)
        params['page_size'] = str(page_size)
        return f"{request.path}?{urlencode(params)}"

    return items, {
        'count': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'has_next': has_next,
        'has_previous': has_previous,
        'next_url': _build_url(page + 1) if has_next else None,
        'previous_url': _build_url(page - 1) if has_previous else None,
    }
