# coding: utf-8

import functools
import json
import sys
import subprocess


curl_format = """{
"time_namelookup": "%{time_namelookup}",
"time_connect": "%{time_connect}",
"time_appconnect": "%{time_appconnect}",
"time_pretransfer": "%{time_pretransfer}",
"time_redirect": "%{time_redirect}",
"time_starttransfer": "%{time_starttransfer}",
"time_total": "%{time_total}"
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


def wide(s, width=10, align='left'):
    if align == 'left':
        sign = '<'
    else:
        sign = '>'
    tpl = '{:%s%s}' % (sign, width)
    return tpl.format(s)


if __name__ == '__main__':
    url = sys.argv[1]
    cmd = ['curl', '-w', curl_format, '-o', '/dev/null', '-s', url]
    output = subprocess.check_output(cmd)

    d = json.loads(output)
    for k in d:
        d[k] = int(float(d[k]) * 1000)
    d.update(
        range_dns=d['time_namelookup'],
        range_connection=d['time_connect'] - d['time_namelookup'],
        range_ssl=d['time_pretransfer'] - d['time_connect'],
        range_server=d['time_starttransfer'] - d['time_pretransfer'],
        range_transfer=d['time_total'] - d['time_starttransfer'],
    )

    unit = 'ms'

    def _unit(s):
        return str(s) + unit

    wide6l = functools.partial(wide, width=6, align='left')
    wide6r = functools.partial(wide, width=6, align='right')
    rs = https_template.format(
        a000=wide6r(_unit(d['range_dns'])),
        a001=wide6r(_unit(d['range_connection'])),
        a002=wide6r(_unit(d['range_ssl'])),
        a003=wide6r(_unit(d['range_server'])),
        a004=wide6r(_unit(d['range_transfer'])),
        b000=wide6l(_unit(d['time_namelookup'])),
        b001=wide6l(_unit(d['time_connect'])),
        b002=wide6l(_unit(d['time_pretransfer'])),
        b003=wide6l(_unit(d['time_starttransfer'])),
        b004=wide6l(_unit(d['time_total'])),
    )
    print rs
