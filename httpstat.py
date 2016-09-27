#!/usr/bin/env python
# coding: utf-8
# References:
# man curl
# https://curl.haxx.se/libcurl/c/curl_easy_getinfo.html
# https://curl.haxx.se/libcurl/c/easy_getinfo_options.html
# http://blog.kenweiner.com/2014/11/http-request-timings-with-curl.html

from __future__ import print_function

import os
import json
import sys
import logging
import tempfile
import subprocess


__version__ = '1.1.3'


PY3 = sys.version_info >= (3,)

if PY3:
    xrange = range


class Env(object):
    prefix = 'HTTPSTAT'

    def __init__(self, key):
        self.key = key.format(prefix=self.prefix)

    def get(self, default=None):
        return os.environ.get(self.key, default)

ENV_SHOW_BODY = Env('{prefix}_SHOW_BODY')
ENV_SHOW_SPEED = Env('{prefix}_SHOW_SPEED')
ENV_SAVE_BODY = Env('{prefix}_SAVE_BODY')
ENV_CURL_BIN = Env('{prefix}_CURL_BIN')
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
"speed_upload": %{speed_upload}
}"""

https_template = """
  DNS Lookup   TCP Connection   SSL Handshake   Server Processing   Content Transfer
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


ISATTY = sys.stdout.isatty()


def make_color(code):
    def color_func(s):
        if not ISATTY:
            return s
        tpl = '\x1b[{}m{}\x1b[0m'
        return tpl.format(code, s)
    return color_func


red = make_color(31)
green = make_color(32)
yellow = make_color(33)
blue = make_color(34)
magenta = make_color(35)
cyan = make_color(36)

bold = make_color(1)
underline = make_color(4)

grayscale = {(i - 232): make_color('38;5;' + str(i)) for i in xrange(232, 256)}


def quit(s, code=0):
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

Environments:
  HTTPSTAT_SHOW_BODY    Set to `true` to show resposne body in the output,
                        note that body length is limited to 1023 bytes, will be
                        truncated if exceeds. Default is `false`.
  HTTPSTAT_SHOW_SPEED   Set to `true` to show download and upload speed.
                        Default is `false`.
  HTTPSTAT_SAVE_BODY    By default httpstat stores body in a tmp file,
                        set to `false` to disable this feature. Default is `true`
  HTTPSTAT_CURL_BIN     Indicate the curl bin path to use. Default is `curl`
                        from current shell $PATH.
  HTTPSTAT_DEBUG        Set to `true` to see debugging logs. Default is `false`
"""[1:-1]
    print(help)


def main():
    args = sys.argv[1:]
    if not args:
        print_help()
        quit(None, 0)

    # get envs
    show_body = 'true' in ENV_SHOW_BODY.get('false').lower()
    show_speed = 'true'in ENV_SHOW_SPEED.get('false').lower()
    save_body = 'true' in ENV_SAVE_BODY.get('true').lower()
    curl_bin = ENV_CURL_BIN.get('curl')
    is_debug = 'true' in ENV_DEBUG.get('false').lower()

    # configure logging
    if is_debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)
    lg = logging.getLogger('httpstat')

    # log envs
    lg.debug(
        'ENVs:\n'
        '  {show_body_key}: {show_body}\n'
        '  {show_speed_key}: {show_speed}\n'
        '  {save_body_key}: {save_body}\n'
        '  {curl_bin_key}: {curl_bin}\n'
        '  {is_debug_key}: {is_debug}\n'.format(
            show_body_key=ENV_SHOW_BODY.key, show_body=show_body,
            show_speed_key=ENV_SHOW_SPEED.key, show_speed=show_speed,
            save_body_key=ENV_SAVE_BODY.key, save_body=save_body,
            curl_bin_key=ENV_CURL_BIN.key, curl_bin=curl_bin,
            is_debug_key=ENV_DEBUG.key, is_debug=is_debug,
        )
    )

    # get url
    url = args[0]
    if url in ['-h', '--help']:
        print_help()
        quit(None, 0)
    elif url == '--version':
        print('httpstat {}'.format(__version__))
        quit(None, 0)

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
            quit(yellow('Error: {} is not allowed in extra curl args'.format(i)), 1)

    # tempfile for output
    bodyf = tempfile.NamedTemporaryFile(delete=False)
    bodyf.close()

    headerf = tempfile.NamedTemporaryFile(delete=False)
    headerf.close()

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
    if PY3:
        out, err = out.decode(), err.decode()

    # print stderr
    if p.returncode == 0:
        print(grayscale[16](err))
    else:
        _cmd = list(cmd)
        _cmd[2] = '<output-format>'
        _cmd[4] = '<tempfile>'
        _cmd[6] = '<tempfile>'
        print('> {}'.format(' '.join(_cmd)))
        quit(yellow('curl error: {}'.format(err)), p.returncode)

    # parse output
    try:
        d = json.loads(out)
    except ValueError as e:
        print(yellow('Could not decode json: {}'.format(e)))
        print('curl result:', p.returncode, grayscale[16](out), grayscale[16](err))
        quit(None, 1)
    for k in d:
        if k.startswith('time_'):
            d[k] = int(d[k] * 1000)

    # calculate ranges
    d.update(
        range_dns=d['time_namelookup'],
        range_connection=d['time_connect'] - d['time_namelookup'],
        range_ssl=d['time_pretransfer'] - d['time_connect'],
        range_server=d['time_starttransfer'] - d['time_pretransfer'],
        range_transfer=d['time_total'] - d['time_starttransfer'],
    )

    # print header & body summary
    with open(headerf.name, 'r') as f:
        headers = f.read().strip()
    # remove header file
    lg.debug('rm header file %s', headerf.name)
    os.remove(headerf.name)

    for loop, line in enumerate(headers.split('\n')):
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
            s = '{} is truncated ({} out of {})'.format(green('Body'), body_limit, body_len)
            if save_body:
                s += ', stored in: {}'.format(bodyf.name)
            print(s)
        else:
            print(body)
    else:
        if save_body:
            print('{} stored in: {}'.format(green('Body'), bodyf.name))

    # remove body file
    if not save_body:
        lg.debug('rm body file %s', bodyf.name)
        os.remove(bodyf.name)

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
        return cyan('{:^7}'.format(str(s) + 'ms'))

    def fmtb(s):
        return cyan('{:<7}'.format(str(s) + 'ms'))

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
        print('speed_download: {:.1f} KiB/s, speed_upload: {:.1f} KiB/s'.format(
            d['speed_download'] / 1024, d['speed_upload'] / 1024))


if __name__ == '__main__':
    main()
