#!/bin/bash

function assert_exit() {
    rc=$?
    expect=$1
    if [ "$rc" -eq "$expect" ]; then
        echo OK
    else
        echo "Failed, expect $expect, got $rc"
        exit 1
    fi
}

function title() {
    echo
    echo "Test $1 ..."
}

function check_url() {
    url=$1
    echo "Checking $url ..."
    if curl -s --head "$url" >/dev/null; then
        echo "URL $url is accessible"
    else
        echo "URL $url is not accessible"
        exit 1
    fi
}

http_url="https://www.gstatic.com/generate_204"
https_url="https://http2.akamai.com"

check_url "$http_url"
check_url "$https_url"
    
for pybin in python; do
    echo
    echo "# Test in $pybin"

    function main() {
        $pybin httpstat.py "$@" 2>&1
    }

    function main_silent() {
        $pybin httpstat.py "$@" >/dev/null 2>&1
    }

    title "basic"
    main_silent $http_url
    assert_exit 0

    title "https site ($https_url)"
    main_silent $https_url
    assert_exit 0

    title "comma decimal language (ru_RU)"
    LC_ALL=ru_RU main_silent $http_url
    assert_exit 0

    title "HTTPSTAT_DEBUG"
    HTTPSTAT_DEBUG=true main $http_url | grep -q 'HTTPSTAT_DEBUG=true'
    assert_exit 0

    title "HTTPSTAT_SHOW_SPEED"
    HTTPSTAT_SHOW_SPEED=true main $http_url | grep -q 'speed_download'
    assert_exit 0

    title "HTTPSTAT_CURL_BIN"
    HTTPSTAT_CURL_BIN=/usr/bin/curl HTTPSTAT_DEBUG=true main $http_url | grep -q '/usr/bin/curl'
    assert_exit 0

    title "HTTPSTAT_SHOW_IP"
    HTTPSTAT_SHOW_IP="true" main $http_url | grep -q 'Connected'
    assert_exit 0

    title "HTTPSTAT_SHOW_BODY=true, -G --data-urlencode \"a=中文\""
    HTTPSTAT_SHOW_BODY="true" main_silent httpbin.org/get -G --data-urlencode "a=中文"
    assert_exit 0

    title "HTTPSTAT_SHOW_BODY=true, -G --data-urlencode \"a=中文\""
    HTTPSTAT_SHOW_BODY="true" main_silent httpbin.org/post -X POST --data-urlencode "a=中文"
    assert_exit 0

    title "HTTPSTAT_SAVE_BODY=true"
    HTTPSTAT_SAVE_BODY=true main $http_url | grep -q 'stored in'
    assert_exit 0

    title "HTTPSTAT_SAVE_BODY=false"
    HTTPSTAT_SAVE_BODY=false HTTPSTAT_DEBUG=true main $http_url | grep -q 'rm body file'
    assert_exit 0

    title "HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=true"
    out=$(HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=true \
        main $https_url)
    echo "$out" | grep -q '^HTTP/'
    assert_exit 0

    if echo "$out" | grep -q 'is truncated'; then
        echo "$out" | grep -q 'stored in'
        assert_exit 0
    fi

    title "HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=false, no 'stored in'"
    out=$(HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=false \
        main $https_url)
    echo "$out" | grep -q '^HTTP/'
    assert_exit 0

    echo "$out" | grep -q 'stored in'
    assert_exit 1

    title "--format json produces valid JSON with schema_version"
    out=$(main $http_url --format json)
    echo "$out" | python -c "import sys,json; d=json.load(sys.stdin); assert d['schema_version']==1"
    assert_exit 0

    title "--format jsonl produces single-line JSON"
    out=$(main $http_url --format jsonl)
    lines=$(echo "$out" | wc -l | tr -d ' ')
    [ "$lines" -eq 1 ]
    assert_exit 0

    title "--slo total=1 triggers exit code 4"
    main_silent $http_url --slo total=1
    assert_exit 4

    title "--save writes file"
    tmpout="/tmp/httpstat_e2e_test_$$.json"
    main_silent $http_url --format json --save "$tmpout"
    assert_exit 0
    python -c "import json; d=json.load(open('$tmpout')); assert d['schema_version']==1"
    assert_exit 0
    rm -f "$tmpout"

    title "NO_COLOR disables ANSI escapes"
    out=$(NO_COLOR=1 main $http_url)
    if echo "$out" | python -c "import sys; sys.exit(0 if '\x1b[' in sys.stdin.read() else 1)" 2>/dev/null; then
        echo "Failed, found ANSI escapes"
        exit 1
    else
        echo OK
    fi

    title "HTTPSTAT_METRICS_ONLY backward compat with --format"
    out=$(HTTPSTAT_METRICS_ONLY=true main $http_url)
    echo "$out" | python -c "import sys,json; json.load(sys.stdin)"
    assert_exit 0
done
