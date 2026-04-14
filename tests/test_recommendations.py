import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


def _make_project(status='online', last_ping=None, response_time=100):
    return {
        'id': 'test-svc',
        'name': 'Test Service',
        'status': status,
        'last_ping': last_ping or datetime.now().isoformat(),
        'response_time': response_time,
    }


def test_offline_service_over_30min_is_critical(app):
    from recommendations import run_rule_checks
    stale_ping = (datetime.now() - timedelta(minutes=45)).isoformat()
    projects = [_make_project(status='offline', last_ping=stale_ping)]
    telemetry = []
    recent_failures = 0
    recs = run_rule_checks(projects, telemetry, recent_failures)
    assert any(r['severity'] == 'critical' and 'offline' in r['message'].lower() for r in recs)


def test_offline_service_under_30min_is_warning(app):
    from recommendations import run_rule_checks
    recent_ping = (datetime.now() - timedelta(minutes=10)).isoformat()
    projects = [_make_project(status='offline', last_ping=recent_ping)]
    recs = run_rule_checks(projects, [], 0)
    assert any(r['severity'] == 'warning' and 'offline' in r['message'].lower() for r in recs)


def test_high_cpu_is_warning(app):
    from recommendations import run_rule_checks
    telemetry = [{'cpu_usage': 90.0, 'ram_usage': 50.0} for _ in range(5)]
    recs = run_rule_checks([], telemetry, 0)
    assert any(r['severity'] == 'warning' and 'cpu' in r['message'].lower() for r in recs)


def test_high_ram_is_critical(app):
    from recommendations import run_rule_checks
    telemetry = [{'cpu_usage': 20.0, 'ram_usage': 92.0} for _ in range(5)]
    recs = run_rule_checks([], telemetry, 0)
    assert any(r['severity'] == 'critical' and 'ram' in r['message'].lower() for r in recs)


def test_many_failed_logins_is_critical(app):
    from recommendations import run_rule_checks
    recs = run_rule_checks([], [], recent_failures=15)
    assert any(r['severity'] == 'critical' and 'login' in r['message'].lower() for r in recs)


def test_no_alerts_when_everything_healthy(app):
    from recommendations import run_rule_checks
    projects = [_make_project(status='online')]
    telemetry = [{'cpu_usage': 30.0, 'ram_usage': 40.0} for _ in range(5)]
    recs = run_rule_checks(projects, telemetry, recent_failures=0)
    assert recs == []


def test_ai_insights_returns_recommendations(app):
    from recommendations import run_ai_checks
    snapshot = {'services': [], 'github': [], 'telemetry_avg': {}}

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='- Deploy backlog growing for mjolnir-armory\n- CPU trending up')]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(content=mock_message.content)

    with patch('recommendations.anthropic.Anthropic', return_value=mock_client):
        recs = run_ai_checks(snapshot, api_key='fake-key')

    assert len(recs) >= 1
    assert all(r['source'] == 'ai' for r in recs)


def test_ai_insights_fails_gracefully(app):
    from recommendations import run_ai_checks
    snapshot = {'services': [], 'github': [], 'telemetry_avg': {}}

    with patch('recommendations.anthropic.Anthropic', side_effect=Exception('API down')):
        recs = run_ai_checks(snapshot, api_key='fake-key')

    assert recs == []
