# coding: utf-8

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

http_template = """
  DNS Lookup   TCP Connection   Server Processing   Content Transfer
[   {a000}   |    {a001}      |      {a003}       |     {a004}       ]
             |                |                   |                  |
    namelookup:{b000}         |                   |                  |
                        connect:{b001}            |                  |
                                      starttransfer:{b003}           |
                                                                 total:{b004}
"""[1:]


if __name__ == '__main__':
    url = sys.argv[1]
    if url.startswith('https://'):
        template = https_template
    else:
        template = http_template

    # run cmd
    cmd = ['curl', '-w', curl_format, '-o', '/dev/null', '-s', url]
    output = subprocess.check_output(cmd)

    # parse output
    d = json.loads(output)
    for k in d:
        d[k] = int(float(d[k]) * 1000)

    # calculate ranges
    d.update(
        range_dns=d['time_namelookup'],
        range_connection=d['time_connect'] - d['time_namelookup'],
        range_ssl=d['time_pretransfer'] - d['time_connect'],
        range_server=d['time_starttransfer'] - d['time_pretransfer'],
        range_transfer=d['time_total'] - d['time_starttransfer'],
    )

    def fmta(s):
        return '{:>4}ms'.format(s)

    def fmtb(s):
        return '{:<6}'.format(str(s) + 'ms')

    # render result
    rs = template.format(
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
    print rs
