# coding: utf-8
# https://curl.haxx.se/libcurl/c/easy_getinfo_options.html
# http://blog.kenweiner.com/2014/11/http-request-timings-with-curl.html

from __future__ import print_function

import os
import json
import sys
import tempfile
import subprocess


PY3 = sys.version_info >= (3,)

if PY3:
    xrange = range

ENV_SHOW_BODY = 'HTTPSTAT_SHOW_BODY'

curl_format = """{
"time_namelookup": %{time_namelookup},
"time_connect": %{time_connect},
"time_appconnect": %{time_appconnect},
"time_pretransfer": %{time_pretransfer},
"time_redirect": %{time_redirect},
"time_starttransfer": %{time_starttransfer},
"time_total": %{time_total}
}"""

https_template = """
  DNS Lookup   TCP Connection   SSL handshake   Server Processing   Content Transfer
[   {a000}   |    {a001}      |     {a002}    |      {a003}       |     {a004}       ]
             |                |               |                   |                  |
    namelookup:{b000}         |               |                   |                  |
                        connect:{b001}        |                   |                  |
                                    pretransfer:{b002}            |                  |
                                                      starttransfer:{b003}           |
                                                                                 total:{b004}
"""[1:]

http_template = """
  DNS Lookup   TCP Connection   Server Processing   Content Transfer
[   {a000}   |    {a001}      |      {a003}       |     {a004}       ]
             |                |                   |                  |
    namelookup:{b000}         |                   |                  |
                        connect:{b001}            |                  |
                                      starttransfer:{b003}           |
                                                                 total:{b004}
"""[1:]


def make_color(code):
    def color_func(s):
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
    print(s)
    sys.exit(code)


def main():
    args = sys.argv[1:]
    url = args[0]
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
    cmd = ['curl', '-w', curl_format, '-D', headerf.name, '-o', bodyf.name, '-s', '-S'] + curl_args + [url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = p.communicate()
    if PY3:
        out, err = out.decode(), err.decode()
    if p.returncode != 0:
        quit(yellow('curl error: {}'.format(err)), p.returncode)

    # parse output
    d = json.loads(out)
    for k in d:
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
    tpl_parts[0] = grayscale[14](tpl_parts[0])
    template = '\n'.join(tpl_parts)

    def fmta(s):
        return cyan('{:>4}ms'.format(s))

    def fmtb(s):
        return cyan('{:<6}'.format(str(s) + 'ms'))

    stat = template.format(
        # a
        a000=fmta(d['range_dns']),
        a001=fmta(d['range_connection']),
        a002=fmta(d['range_ssl']),
        a003=fmta(d['range_server']),
        a004=fmta(d['range_transfer']),
        # b
        b000=fmtb(d['time_namelookup']),
        b001=fmtb(d['time_connect']),
        b002=fmtb(d['time_pretransfer']),
        b003=fmtb(d['time_starttransfer']),
        b004=fmtb(d['time_total']),
    )
    print()
    print(stat)


if __name__ == '__main__':
    main()
