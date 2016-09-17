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
import tempfile
import subprocess


__version__ = '1.1.3'


PY3 = sys.version_info >= (3,)

if PY3:
    xrange = range

ENV_SHOW_BODY = 'HTTPSTAT_SHOW_BODY'
ENV_SHOW_SPEED = 'HTTPSTAT_SHOW_SPEED'

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
  HTTPSTAT_SHOW_BODY    By default httpstat will write response body
                        in a tempfile, but you can let it print out by setting
                        this variable to `true`.
  HTTPSTAT_SHOW_SPEED   set to `true` to show download and upload speed.
"""[1:-1]
    print(help)


def main():
    args = sys.argv[1:]
    if not args:
        print_help()
        quit(None, 0)

    url = args[0]
    if url in ['-h', '--help']:
        print_help()
        quit(None, 0)
    elif url == '--version':
        print('httpstat {}'.format(__version__))
        quit(None, 0)

    curl_args = args[1:]

    # check curl args
    exclude_options = ['-w', '-D', '-o', '-s']
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
    cmd_core = ['curl', '-w', curl_format, '-D', headerf.name, '-o', bodyf.name, '-s', '-S']
    cmd = cmd_core + curl_args + [url]
    #print(cmd)
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
    show_body = os.environ.get(ENV_SHOW_BODY, 'false')
    show_body = 'true' in show_body.lower()
    if show_body:
        body_limit = 1024
        with open(bodyf.name, 'r') as f:
            body = f.read().strip()
        if len(body) > body_limit:
            print(body[:body_limit] + '... (more in {})'.format(bodyf.name))
        else:
            print(body)
    else:
        print('{} stored in: {}'.format(green('Body'), bodyf.name))

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
    show_speed = os.environ.get(ENV_SHOW_SPEED, 'false')
    show_speed = 'true' in show_speed.lower()
    if show_speed:
        print('speed_download: {:.1f} KiB, speed_upload: {:.1f} KiB'.format(
            d['speed_download'] / 1024, d['speed_upload'] / 1024))


if __name__ == '__main__':
    main()
