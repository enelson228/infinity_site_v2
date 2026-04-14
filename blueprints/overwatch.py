import urllib.request
import urllib.error
from flask import Blueprint, render_template, request
import config

overwatch_bp = Blueprint('overwatch', __name__)

@overwatch_bp.route('/overwatch')
def overwatch():
    return render_template('overwatch.html', cesium_token=config.CESIUM_ION_TOKEN)

@overwatch_bp.route('/api/tle')
def tle_proxy():
    """Proxy Celestrak TLE data to avoid browser CORS restrictions."""
    group = request.args.get('group', 'stations')
    # Sanitize group name to path-safe characters only
    safe_group = ''.join(c for c in group if c.isalnum() or c in '-_')
    # Celestrak new GP data API (replaces deprecated pub/TLE/* paths)
    base = 'https://celestrak.org/NORAD/elements/gp.php'
    url = f'{base}?GROUP={safe_group}&FORMAT=TLE'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode('utf-8', errors='replace')
        return data, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except urllib.error.URLError as e:
        return f'# TLE fetch error: {e.reason}\n', 502, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f'# TLE fetch error: {e}\n', 500, {'Content-Type': 'text/plain'}
