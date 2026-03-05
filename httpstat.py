#!/usr/bin/env python
from __future__ import annotations
# References:
# man curl
# https://curl.haxx.se/libcurl/c/curl_easy_getinfo.html
# https://curl.haxx.se/libcurl/c/easy_getinfo_options.html
# http://blog.kenweiner.com/2014/11/http-request-timings-with-curl.html

import os
import json
import sys
import logging
import tempfile
import subprocess
from typing import NoReturn, overload


__version__ = '2.0.0'


class Env:
    prefix = 'HTTPSTAT'
    _instances: list['Env'] = []

    def __init__(self, key: str):
        self.key = key.format(prefix=self.prefix)
        Env._instances.append(self)

    @overload
    def get(self, default: str) -> str: ...
    @overload
    def get(self, default: None = None) -> str | None: ...
    def get(self, default: str | None = None) -> str | None:
        return os.environ.get(self.key, default)


ENV_SHOW_BODY = Env('{prefix}_SHOW_BODY')
ENV_SHOW_IP = Env('{prefix}_SHOW_IP')
ENV_SHOW_SPEED = Env('{prefix}_SHOW_SPEED')
ENV_SAVE_BODY = Env('{prefix}_SAVE_BODY')
ENV_CURL_BIN = Env('{prefix}_CURL_BIN')
ENV_METRICS_ONLY = Env('{prefix}_METRICS_ONLY')
ENV_DEBUG = Env('{prefix}_DEBUG')


curl_format = """{
"time_namelookup": %{time_namelookup},
"time_connect": %{time_connect},
"time_appconnect": %{time_appconnect},
"time_pretransfer": %{time_pretransfer},
"time_redirect": %{time_redirect},
"time_starttransfer": %{time_starttransfer},
"time_total": %{time_total},
"speed_download": %{speed_download},
"speed_upload": %{speed_upload},
"remote_ip": "%{remote_ip}",
"remote_port": "%{remote_port}",
"local_ip": "%{local_ip}",
"local_port": "%{local_port}"
}"""

https_template = """
  DNS Lookup   TCP Connection   TLS Handshake   Server Processing   Content Transfer
[   {a0000}  |     {a0001}    |    {a0002}    |      {a0003}      |      {a0004}     ]
             |                |               |                   |                  |
    namelookup:{b0000}        |               |                   |                  |
                        connect:{b0001}       |                   |                  |
                                    pretransfer:{b0002}           |                  |
                                                      starttransfer:{b0003}          |
                                                                                 total:{b0004}
"""[1:]

http_template = """
  DNS Lookup   TCP Connection   Server Processing   Content Transfer
[   {a0000}  |     {a0001}    |      {a0003}      |      {a0004}     ]
             |                |                   |                  |
    namelookup:{b0000}        |                   |                  |
                        connect:{b0001}           |                  |
                                      starttransfer:{b0003}          |
                                                                 total:{b0004}
"""[1:]


# Color code is copied from https://github.com/reorx/python-terminal-color/blob/master/color_simple.py
ISATTY = sys.stdout.isatty() and 'NO_COLOR' not in os.environ


def make_color(code):
    def color_func(s):
        if not ISATTY:
            return s
        return f'\x1b[{code}m{s}\x1b[0m'
    return color_func


red = make_color(31)
green = make_color(32)
yellow = make_color(33)
blue = make_color(34)
magenta = make_color(35)
cyan = make_color(36)

bold = make_color(1)
underline = make_color(4)

grayscale = {(i - 232): make_color(f'38;5;{i}') for i in range(232, 256)}


_TRUTHY = frozenset(('1', 'true', 'yes', 'on'))
_FALSY = frozenset(('0', 'false', 'no', 'off'))


def parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in _TRUTHY:
        return True
    if v in _FALSY:
        return False
    raise ValueError(f'invalid boolean value: {value!r}')


def pop_arg(args: list[str], flag: str, has_value: bool = True) -> str | bool | None:
    """Remove flag (and its value if has_value) from args list in-place.
    Returns the value string, True (for valueless flags), or None if not found.
    """
    if flag not in args:
        return None
    idx = args.index(flag)
    if has_value:
        if idx + 1 >= len(args):
            return None  # flag at end with no value
        args.pop(idx)  # remove flag
        return args.pop(idx)  # remove and return value
    else:
        args.pop(idx)
        return True


SLO_KEY_MAP = {
    'total': 'time_total',
    'connect': 'time_connect',
    'ttfb': 'time_starttransfer',
    'dns': 'time_namelookup',
    'tls': 'time_pretransfer',
}


def parse_slo(spec: str) -> dict[str, int]:
    """Parse 'total=500,connect=100' → {'total': 500, 'connect': 100}.
    Exits with error on invalid input.
    """
    result = {}
    for part in spec.split(','):
        part = part.strip()
        if not part:
            print(f'Error: empty SLO spec')
            sys.exit(1)
        if '=' not in part:
            print(f'Error: invalid SLO spec "{part}", expected key=value')
            sys.exit(1)
        key, _, val = part.partition('=')
        key = key.strip()
        val = val.strip()
        if key not in SLO_KEY_MAP:
            valid = ', '.join(SLO_KEY_MAP.keys())
            print(f'Error: unknown SLO key "{key}", valid keys: {valid}')
            sys.exit(1)
        try:
            ms = int(val)
        except ValueError:
            print(f'Error: SLO value for "{key}" must be a positive integer, got "{val}"')
            sys.exit(1)
        if ms <= 0:
            print(f'Error: SLO value for "{key}" must be positive, got {ms}')
            sys.exit(1)
        result[key] = ms
    return result


def check_slo(slo: dict[str, int], timings: dict) -> tuple[bool, list[dict]]:
    """Check timings against SLO thresholds.
    Returns (pass, violations). Each violation: {'key': ..., 'threshold_ms': ..., 'actual_ms': ...}
    """
    violations = []
    for key, threshold in slo.items():
        timing_key = SLO_KEY_MAP[key]
        actual = timings[timing_key]
        if actual > threshold:
            violations.append({
                'key': key,
                'threshold_ms': threshold,
                'actual_ms': actual,
            })
    return (len(violations) == 0, violations)


def build_json_result(url: str, d: dict, headers_text: str,
                      slo_result: tuple[bool, list[dict]] | None,
                      exit_code: int) -> dict:
    """Build the v1 JSON schema output dict."""
    # Parse status line from headers
    first_line = headers_text.split('\n')[0].strip().rstrip('\r')
    status_line = first_line
    # Extract status code: "HTTP/2 200" or "HTTP/1.1 301 Moved Permanently"
    parts = first_line.split(None, 2)
    try:
        status_code = int(parts[1]) if len(parts) >= 2 else 0
    except (ValueError, IndexError):
        status_code = 0

    ok = exit_code == 0

    result = {
        'schema_version': 1,
        'url': url,
        'ok': ok,
        'exit_code': exit_code,
        'response': {
            'status_line': status_line,
            'status_code': status_code,
            'remote_ip': d.get('remote_ip', ''),
            'remote_port': d.get('remote_port', ''),
            'headers': headers_text,
        },
        'timings_ms': {
            'dns': d['range_dns'],
            'connect': d['range_connection'],
            'tls': d['range_ssl'],
            'server': d['range_server'],
            'transfer': d['range_transfer'],
            'total': d['time_total'],
            'namelookup': d['time_namelookup'],
            'initial_connect': d['time_connect'],
            'pretransfer': d['time_pretransfer'],
            'starttransfer': d['time_starttransfer'],
        },
        'speed': {
            'download_kbs': round(d.get('speed_download', 0) / 1024, 1),
            'upload_kbs': round(d.get('speed_upload', 0) / 1024, 1),
        },
        'slo': None,
    }

    if slo_result is not None:
        result['slo'] = {
            'pass': slo_result[0],
            'violations': slo_result[1],
        }

    return result


def _exit(s, code=0) -> NoReturn:
    if s is not None:
        print(s)
    sys.exit(code)


def print_help():
    help = """
Usage: httpstat URL [CURL_OPTIONS]
       httpstat -h | --help
       httpstat --version

Arguments:
  URL     url to request, could be with or without `http(s)://` prefix

Options:
  CURL_OPTIONS  any curl supported options, except for -w -D -o -S -s,
                which are already used internally.
  -h --help     show this screen.
  --version     show version.
  -f --format   output format: pretty, json, jsonl. Default is `pretty`.
  --slo         SLO thresholds as key=value pairs, e.g. `total=500,connect=100`.
                Valid keys: total, connect, ttfb, dns, tls.
                Exits with code 4 on violation.
  --save        save structured output to a file path.

Environments:
  HTTPSTAT_SHOW_BODY    Set to `true` to show response body in the output,
                        note that body length is limited to 1023 bytes, will be
                        truncated if exceeds. Default is `false`.
  HTTPSTAT_SHOW_IP      By default httpstat shows remote and local IP/port address.
                        Set to `false` to disable this feature. Default is `true`.
  HTTPSTAT_SHOW_SPEED   Set to `true` to show download and upload speed.
                        Default is `false`.
  HTTPSTAT_SAVE_BODY    By default httpstat stores body in a tmp file,
                        set to `false` to disable this feature. Default is `true`
  HTTPSTAT_CURL_BIN     Indicate the curl bin path to use. Default is `curl`
                        from current shell $PATH.
  HTTPSTAT_DEBUG        Set to `true` to see debugging logs. Default is `false`
  NO_COLOR              Disable colored output (see https://no-color.org).
"""[1:-1]
    print(help)


def main():
    args = sys.argv[1:]
    if not args:
        print_help()
        _exit(None, 0)

    # pop httpstat-specific flags before anything else
    output_format = pop_arg(args, '--format') or pop_arg(args, '-f') or 'pretty'
    slo_spec = pop_arg(args, '--slo')
    save_path = pop_arg(args, '--save')

    # get envs
    show_body = parse_bool(ENV_SHOW_BODY.get('false'))
    show_ip = parse_bool(ENV_SHOW_IP.get('true'))
    show_speed = parse_bool(ENV_SHOW_SPEED.get('false'))
    save_body = parse_bool(ENV_SAVE_BODY.get('true'))
    curl_bin = ENV_CURL_BIN.get('curl')
    metrics_only = parse_bool(ENV_METRICS_ONLY.get('false'))
    is_debug = parse_bool(ENV_DEBUG.get('false'))

    # backward compat: HTTPSTAT_METRICS_ONLY → --format json
    if metrics_only and output_format == 'pretty':
        output_format = 'json'

    # validate output format
    if output_format not in ('pretty', 'json', 'jsonl'):
        _exit(f'Error: invalid format "{output_format}", must be pretty, json, or jsonl', 1)

    # parse SLO spec
    slo = parse_slo(slo_spec) if slo_spec else None

    # configure logging
    if is_debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)
    lg = logging.getLogger('httpstat')

    # log envs
    lg.debug('Envs:\n%s', '\n'.join(f'  {i.key}={i.get("")}' for i in Env._instances))
    lg.debug('Flags: %s', dict(
        show_body=show_body,
        show_ip=show_ip,
        show_speed=show_speed,
        save_body=save_body,
        curl_bin=curl_bin,
        is_debug=is_debug,
    ))

    # get url
    url = args[0]
    if url in ['-h', '--help']:
        print_help()
        _exit(None, 0)
    elif url == '--version':
        print(f'httpstat {__version__}')
        _exit(None, 0)

    curl_args = args[1:]

    # check curl args
    exclude_options = [
        '-w', '--write-out',
        '-D', '--dump-header',
        '-o', '--output',
        '-s', '--silent',
    ]
    for i in exclude_options:
        if i in curl_args:
            _exit(yellow(f'Error: {i} is not allowed in extra curl args'), 1)

    # tempfile for output
    bodyf = tempfile.NamedTemporaryFile(delete=False)
    bodyf.close()

    headerf = tempfile.NamedTemporaryFile(delete=False)
    headerf.close()

    try:
        # run cmd
        cmd_env = os.environ.copy()
        cmd_env.update(
            LC_ALL='C',
        )
        cmd_core = [curl_bin, '-w', curl_format, '-D', headerf.name, '-o', bodyf.name, '-s', '-S']
        cmd = cmd_core + curl_args + [url]
        lg.debug('cmd: %s', cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=cmd_env)
        out, err = p.communicate()
        out, err = out.decode(errors='replace'), err.decode(errors='replace')
        lg.debug('out: %s', out)

        # print stderr
        if p.returncode == 0:
            if err:
                print(grayscale[16](err))
        else:
            _cmd = list(cmd)
            _cmd[2] = '<output-format>'
            _cmd[4] = '<tempfile>'
            _cmd[6] = '<tempfile>'
            print(f'> {" ".join(_cmd)}')
            _exit(yellow(f'curl error: {err}'), p.returncode)

        # parse output
        try:
            d = json.loads(out)
        except ValueError as e:
            print(yellow(f'Could not decode json: {e}'))
            print('curl result:', p.returncode, grayscale[16](out), grayscale[16](err))
            _exit(None, 1)

        # convert time_ metrics from seconds to milliseconds
        for k in d:
            if k.startswith('time_'):
                v = d[k]
                # Convert time_ values to milliseconds in int
                if isinstance(v, float):
                    # Before 7.61.0, time values are represented as seconds in float
                    d[k] = int(v * 1000)
                elif isinstance(v, int):
                    # Starting from 7.61.0, libcurl uses microsecond in int
                    # to return time values, references:
                    # https://daniel.haxx.se/blog/2018/07/11/curl-7-61-0/
                    # https://curl.se/bug/?i=2495
                    d[k] = int(v / 1000)
                else:
                    raise TypeError(f'{k} value type is invalid: {type(v)}')

        # calculate ranges
        d.update(
            range_dns=d['time_namelookup'],
            range_connection=d['time_connect'] - d['time_namelookup'],
            range_ssl=d['time_pretransfer'] - d['time_connect'],
            range_server=d['time_starttransfer'] - d['time_pretransfer'],
            range_transfer=d['time_total'] - d['time_starttransfer'],
        )

        # read headers
        with open(headerf.name, 'r') as f:
            headers_text = f.read().strip()

        # check SLO
        slo_result = check_slo(slo, d) if slo else None
        exit_code = 0
        if slo_result and not slo_result[0]:
            exit_code = 4

        # --- output ---
        if output_format in ('json', 'jsonl'):
            result = build_json_result(url, d, headers_text, slo_result, exit_code)
            indent = 2 if output_format == 'json' else None
            output_text = json.dumps(result, indent=indent)
            print(output_text)
            if save_path:
                with open(save_path, 'w') as f:
                    f.write(output_text + '\n')
            sys.exit(exit_code)

        # --- pretty mode (default, unchanged behavior) ---

        # ip
        if show_ip:
            print(f"Connected to {cyan(d['remote_ip'])}:{cyan(d['remote_port'])} from {d['local_ip']}:{d['local_port']}")
            print()

        for loop, line in enumerate(headers_text.split('\n')):
            if loop == 0:
                p1, p2 = tuple(line.split('/'))
                print(green(p1) + grayscale[14]('/') + cyan(p2))
            else:
                pos = line.find(':')
                print(grayscale[14](line[:pos + 1]) + cyan(line[pos + 1:]))

        print()

        # body
        if show_body:
            body_limit = 1024
            with open(bodyf.name, 'r') as f:
                body = f.read().strip()
            body_len = len(body)

            if body_len > body_limit:
                print(body[:body_limit] + cyan('...'))
                print()
                s = f"{green('Body')} is truncated ({body_limit} out of {body_len})"
                if save_body:
                    s += f', stored in: {bodyf.name}'
                print(s)
            else:
                print(body)
        else:
            if save_body:
                print(f"{green('Body')} stored in: {bodyf.name}")

        # print stat
        if url.startswith('https://'):
            template = https_template
        else:
            template = http_template

        # colorize template first line
        tpl_parts = template.split('\n')
        tpl_parts[0] = grayscale[16](tpl_parts[0])
        template = '\n'.join(tpl_parts)

        def fmta(s):
            return cyan(f'{str(s) + "ms":^7}')

        def fmtb(s):
            return cyan(f'{str(s) + "ms":<7}')

        stat = template.format(
            # a
            a0000=fmta(d['range_dns']),
            a0001=fmta(d['range_connection']),
            a0002=fmta(d['range_ssl']),
            a0003=fmta(d['range_server']),
            a0004=fmta(d['range_transfer']),
            # b
            b0000=fmtb(d['time_namelookup']),
            b0001=fmtb(d['time_connect']),
            b0002=fmtb(d['time_pretransfer']),
            b0003=fmtb(d['time_starttransfer']),
            b0004=fmtb(d['time_total']),
        )
        print()
        print(stat)

        # speed, originally bytes per second
        if show_speed:
            print(f"speed_download: {d['speed_download'] / 1024:.1f} KiB/s, speed_upload: {d['speed_upload'] / 1024:.1f} KiB/s")

        # SLO violations in pretty mode
        if slo_result and not slo_result[0]:
            print()
            for v in slo_result[1]:
                print(red(f"SLO VIOLATION: {v['key']} = {v['actual_ms']}ms (threshold: {v['threshold_ms']}ms)"))

        # save pretty output as json if --save specified
        if save_path:
            result = build_json_result(url, d, headers_text, slo_result, exit_code)
            with open(save_path, 'w') as f:
                f.write(json.dumps(result, indent=2) + '\n')

        if exit_code:
            sys.exit(exit_code)
    finally:
        # always clean header file; only clean body file if not saving
        for path in (headerf.name,):
            try:
                os.remove(path)
            except OSError:
                pass
        if not save_body:
            lg.debug('rm body file %s', bodyf.name)
            try:
                os.remove(bodyf.name)
            except OSError:
                pass


if __name__ == '__main__':
    main()
