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

http_url="google.com"
https_url="https://http2.akamai.com"

for pybin in python python3; do
#for pybin in python; do
    echo
    echo "# Test in $pybin"

    function main() {
        $pybin httpstat.py $@ 2>&1
    }

    function main_silent() {
        $pybin httpstat.py $@ >/dev/null 2>&1
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
    HTTPSTAT_DEBUG=true main $http_url | grep -q 'HTTPSTAT_DEBUG: True'
    assert_exit 0

    title "HTTPSTAT_SHOW_SPEED"
    HTTPSTAT_SHOW_SPEED=true main $http_url | grep -q 'speed_download'
    assert_exit 0

    title "HTTPSTAT_CURL_BIN"
    HTTPSTAT_CURL_BIN=/usr/bin/curl HTTPSTAT_DEBUG=true main $http_url | grep -q '/usr/bin/curl'
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

    title "HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=true, has 'is truncated, has 'stored in'"
    out=$(HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=true \
        main $https_url)
    echo "$out" | grep -q 'is truncated'
    assert_exit 0

    echo "$out" | grep -q 'stored in'
    assert_exit 0

    title "HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=false, has 'is truncated', no 'stored in'"
    out=$(HTTPSTAT_SHOW_BODY=true HTTPSTAT_SAVE_BODY=false \
        main $https_url)
    echo "$out" | grep -q 'is truncated'
    assert_exit 0

    echo "$out" | grep -q 'stored in'
    assert_exit 1
done
