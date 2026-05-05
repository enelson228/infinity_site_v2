import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, Response, jsonify, request

import config
from auth import login_required

storytell_proxy_bp = Blueprint('storytell_proxy', __name__)

_EXCLUDED_RESPONSE_HEADERS = {
    'connection',
    'content-encoding',
    'content-length',
    'transfer-encoding',
}


def _storytell_base_url() -> str:
    return getattr(config, 'STORYTELL_UPSTREAM_URL', 'http://127.0.0.1:8000').rstrip('/')


def _upstream_url(path: str) -> str:
    query = request.query_string.decode('utf-8')
    quoted_path = '/'.join(urllib.parse.quote(part) for part in path.split('/'))
    url = f"{_storytell_base_url()}/{quoted_path}"
    return f"{url}?{query}" if query else url


@storytell_proxy_bp.route('/storytell-api', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@storytell_proxy_bp.route('/storytell-api/<path:path>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
@login_required
def storytell_proxy(path: str):
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {'host', 'content-length', 'connection'}
    }
    data = request.get_data() if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} else None
    upstream_request = urllib.request.Request(
        _upstream_url(path),
        data=data,
        headers=headers,
        method=request.method,
    )

    try:
        with urllib.request.urlopen(upstream_request, timeout=60) as upstream_response:
            response_headers = [
                (key, value)
                for key, value in upstream_response.headers.items()
                if key.lower() not in _EXCLUDED_RESPONSE_HEADERS
            ]
            return Response(
                upstream_response.read(),
                status=upstream_response.status,
                headers=response_headers,
            )
    except urllib.error.HTTPError as exc:
        response_headers = [
            (key, value)
            for key, value in exc.headers.items()
            if key.lower() not in _EXCLUDED_RESPONSE_HEADERS
        ]
        return Response(exc.read(), status=exc.code, headers=response_headers)
    except urllib.error.URLError as exc:
        return jsonify({'error': 'StoryTell API unavailable', 'detail': str(exc.reason)}), 502
