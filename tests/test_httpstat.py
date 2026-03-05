from __future__ import annotations

import json
import os
import pytest

import httpstat


# --- parse_bool ---

class TestParseBool:
    @pytest.mark.parametrize('value', ['1', 'true', 'yes', 'on', 'TRUE', ' True ', 'YES'])
    def test_truthy(self, value):
        assert httpstat.parse_bool(value) is True

    @pytest.mark.parametrize('value', ['0', 'false', 'no', 'off', 'FALSE', ' False ', 'NO'])
    def test_falsy(self, value):
        assert httpstat.parse_bool(value) is False

    @pytest.mark.parametrize('value', ['', 'maybe', '2', 'truthy'])
    def test_invalid(self, value):
        with pytest.raises(ValueError):
            httpstat.parse_bool(value)


# --- pop_arg ---

class TestPopArg:
    def test_pop_flag_with_value(self):
        args = ['--format', 'json', 'https://example.com']
        val = httpstat.pop_arg(args, '--format')
        assert val == 'json'
        assert args == ['https://example.com']

    def test_pop_flag_with_value_short(self):
        args = ['-f', 'json', 'https://example.com']
        val = httpstat.pop_arg(args, '-f')
        assert val == 'json'
        assert args == ['https://example.com']

    def test_pop_flag_no_value(self):
        args = ['--verbose', 'https://example.com']
        val = httpstat.pop_arg(args, '--verbose', has_value=False)
        assert val is True
        assert args == ['https://example.com']

    def test_pop_flag_missing(self):
        args = ['https://example.com']
        val = httpstat.pop_arg(args, '--format')
        assert val is None
        assert args == ['https://example.com']

    def test_pop_flag_missing_no_value(self):
        args = ['https://example.com']
        val = httpstat.pop_arg(args, '--verbose', has_value=False)
        assert val is None
        assert args == ['https://example.com']

    def test_pop_flag_at_end_missing_value(self):
        args = ['https://example.com', '--format']
        val = httpstat.pop_arg(args, '--format')
        assert val is None
        assert args == ['https://example.com', '--format']

    def test_pop_multiple_flags(self):
        args = ['--format', 'json', '--slo', 'total=500', 'https://example.com']
        fmt = httpstat.pop_arg(args, '--format')
        slo = httpstat.pop_arg(args, '--slo')
        assert fmt == 'json'
        assert slo == 'total=500'
        assert args == ['https://example.com']


# --- parse_slo ---

class TestParseSlo:
    def test_single_key(self):
        result = httpstat.parse_slo('total=500')
        assert result == {'total': 500}

    def test_multiple_keys(self):
        result = httpstat.parse_slo('total=500,connect=100,ttfb=200')
        assert result == {'total': 500, 'connect': 100, 'ttfb': 200}

    def test_all_valid_keys(self):
        result = httpstat.parse_slo('total=1,connect=2,ttfb=3,dns=4,tls=5')
        assert result == {'total': 1, 'connect': 2, 'ttfb': 3, 'dns': 4, 'tls': 5}

    def test_invalid_key(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('badkey=100')

    def test_invalid_value_not_int(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('total=abc')

    def test_invalid_value_negative(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('total=-1')

    def test_invalid_value_zero(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('total=0')

    def test_malformed_no_equals(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('total')

    def test_empty_string(self):
        with pytest.raises(SystemExit):
            httpstat.parse_slo('')

    def test_spaces_trimmed(self):
        result = httpstat.parse_slo(' total = 500 , connect = 100 ')
        assert result == {'total': 500, 'connect': 100}


# --- check_slo ---

class TestCheckSlo:
    def _make_timings(self, **overrides):
        base = {
            'time_namelookup': 5,
            'time_connect': 15,
            'time_pretransfer': 30,
            'time_starttransfer': 80,
            'time_total': 100,
        }
        base.update(overrides)
        return base

    def test_all_pass(self):
        slo = {'total': 200, 'connect': 50}
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is True
        assert violations == []

    def test_one_violation(self):
        slo = {'total': 50}  # actual is 100
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is False
        assert len(violations) == 1
        assert violations[0]['key'] == 'total'
        assert violations[0]['threshold_ms'] == 50
        assert violations[0]['actual_ms'] == 100

    def test_multiple_violations(self):
        slo = {'total': 50, 'dns': 1}
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is False
        assert len(violations) == 2

    def test_exactly_at_threshold_passes(self):
        slo = {'total': 100}  # actual is 100, should pass
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is True
        assert violations == []

    def test_ttfb_maps_to_starttransfer(self):
        slo = {'ttfb': 50}  # actual starttransfer is 80
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is False
        assert violations[0]['actual_ms'] == 80

    def test_tls_maps_to_pretransfer(self):
        slo = {'tls': 25}  # actual pretransfer is 30
        passed, violations = httpstat.check_slo(slo, self._make_timings())
        assert passed is False
        assert violations[0]['actual_ms'] == 30


# --- build_json_result ---

class TestBuildJsonResult:
    def _make_d(self):
        return {
            'time_namelookup': 5,
            'time_connect': 15,
            'time_appconnect': 25,
            'time_pretransfer': 30,
            'time_redirect': 0,
            'time_starttransfer': 80,
            'time_total': 100,
            'speed_download': 10240.0,
            'speed_upload': 0.0,
            'remote_ip': '93.184.216.34',
            'remote_port': '443',
            'local_ip': '192.168.1.1',
            'local_port': '54321',
            'range_dns': 5,
            'range_connection': 10,
            'range_ssl': 15,
            'range_server': 50,
            'range_transfer': 20,
        }

    def test_schema_version(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\ncontent-type: text/html\r\n',
            None, 0,
        )
        assert result['schema_version'] == 1

    def test_basic_fields(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\ncontent-type: text/html\r\n',
            None, 0,
        )
        assert result['url'] == 'https://example.com'
        assert result['ok'] is True
        assert result['exit_code'] == 0

    def test_response_fields(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\ncontent-type: text/html\r\n',
            None, 0,
        )
        assert result['response']['status_line'] == 'HTTP/2 200'
        assert result['response']['status_code'] == 200
        assert result['response']['remote_ip'] == '93.184.216.34'
        assert result['response']['remote_port'] == '443'

    def test_timings_ms(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            None, 0,
        )
        t = result['timings_ms']
        assert t['dns'] == 5
        assert t['connect'] == 10
        assert t['tls'] == 15
        assert t['server'] == 50
        assert t['transfer'] == 20
        assert t['total'] == 100
        assert t['namelookup'] == 5
        assert t['initial_connect'] == 15
        assert t['pretransfer'] == 30
        assert t['starttransfer'] == 80

    def test_speed(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            None, 0,
        )
        assert result['speed']['download_kbs'] == pytest.approx(10.0)
        assert result['speed']['upload_kbs'] == 0.0

    def test_slo_none(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            None, 0,
        )
        assert result['slo'] is None

    def test_slo_pass(self):
        slo_result = (True, [])
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            slo_result, 0,
        )
        assert result['slo']['pass'] is True
        assert result['slo']['violations'] == []

    def test_slo_fail(self):
        slo_result = (False, [{'key': 'total', 'threshold_ms': 50, 'actual_ms': 100}])
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            slo_result, 4,
        )
        assert result['slo']['pass'] is False
        assert len(result['slo']['violations']) == 1
        assert result['exit_code'] == 4
        assert result['ok'] is False

    def test_http1_status_line(self):
        result = httpstat.build_json_result(
            'http://example.com', self._make_d(),
            'HTTP/1.1 301 Moved Permanently\r\nLocation: https://example.com\r\n',
            None, 0,
        )
        assert result['response']['status_line'] == 'HTTP/1.1 301 Moved Permanently'
        assert result['response']['status_code'] == 301

    def test_json_serializable(self):
        result = httpstat.build_json_result(
            'https://example.com', self._make_d(),
            'HTTP/2 200\r\n',
            (True, []), 0,
        )
        # Should not raise
        json.dumps(result)


# --- NO_COLOR ---

class TestNoColor:
    def test_isatty_false_when_no_color_set(self, monkeypatch):
        monkeypatch.setenv('NO_COLOR', '')
        # Re-evaluate ISATTY
        isatty = os.sys.stdout.isatty() and 'NO_COLOR' not in os.environ
        assert isatty is False

    def test_make_color_returns_plain_when_not_isatty(self, monkeypatch):
        monkeypatch.setattr(httpstat, 'ISATTY', False)
        func = httpstat.make_color(31)
        assert func('hello') == 'hello'

    def test_make_color_returns_colored_when_isatty(self, monkeypatch):
        monkeypatch.setattr(httpstat, 'ISATTY', True)
        func = httpstat.make_color(31)
        assert func('hello') == '\x1b[31mhello\x1b[0m'
