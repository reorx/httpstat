---
name: httpstat
description: >
  Diagnose website and API performance using httpstat — a curl wrapper that visualizes
  HTTP timing breakdowns (DNS, TCP, TLS, server processing, content transfer).
  Use this skill whenever the user wants to debug slow websites, analyze HTTP/HTTPS
  latency, profile API response times, understand curl timing output, find network
  bottlenecks, check TLS handshake speed, measure Time to First Byte (TTFB), or
  troubleshoot any connection performance issue. Also trigger when the user has a
  curl command and wants to understand where time is being spent, or when they paste
  httpstat output and want help interpreting it. Even if the user doesn't mention
  "httpstat" by name — if they're asking "why is this endpoint slow?" or "what's
  taking so long?" for an HTTP request, this skill applies.
---

# httpstat: HTTP Performance Diagnostics

Use `httpstat` — a curl wrapper that breaks down HTTP request timing into discrete
phases — to diagnose where latency lives and what to do about it.

## When to use httpstat

- User says a website or API is slow
- User wants to profile an HTTP endpoint
- User has a curl command and wants timing visibility
- User asks about DNS, TLS, TTFB, or connection performance
- User pastes httpstat output and wants interpretation
- User wants to compare performance before/after a change

## Setup (do this first)

Before running any diagnostics, ensure httpstat is available:

```bash
which httpstat || pip install httpstat
```

If `pip` is not appropriate for the environment, try `uv pip install httpstat`,
`pipx install httpstat`, or `brew install httpstat` (macOS). The goal is to get
the `httpstat` command on PATH. Do not assume it is already installed — always
check first.

## Running httpstat

### Basic usage

```bash
httpstat <URL> [curl options]
```

### Get structured JSON output (preferred for analysis)

```bash
httpstat <URL> --format json [curl options]
```

### With SLO thresholds (exit code 4 if any threshold exceeded)

```bash
httpstat <URL> --format json --slo total=500,connect=100,ttfb=200
```

### Save results to file for later comparison

```bash
httpstat <URL> --format json --save results.json
```

### Supported curl options

Any curl flag works EXCEPT `-w`, `-D`, `-o`, `-s`, `-S` (reserved by httpstat).
Common useful ones:

- `-X POST --data '{"key":"val"}'` — test POST endpoints
- `-H "Authorization: Bearer TOKEN"` — authenticated requests
- `-L` — follow redirects
- `-k` — skip TLS verification (useful for self-signed certs)
- `--connect-timeout 10` — cap connection time
- `-6` or `-4` — force IPv6 or IPv4

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HTTPSTAT_SHOW_BODY=true` | false | Show response body (truncated to 1023 bytes) |
| `HTTPSTAT_SHOW_SPEED=true` | false | Show download/upload speed |
| `NO_COLOR=1` | unset | Disable colored output |

## Understanding the JSON output

The `--format json` output has this structure:

```
timings_ms:
  dns         — DNS resolution time
  connect     — TCP handshake duration (after DNS)
  tls         — TLS handshake duration (after TCP connect)
  server      — Server processing time (after TLS, before first byte)
  transfer    — Content download time (after first byte)
  total       — End-to-end total

  namelookup    — Cumulative: DNS done
  initial_connect — Cumulative: TCP done
  pretransfer   — Cumulative: TLS done, ready to send
  starttransfer — Cumulative: first byte received (TTFB)
```

The "range" fields (dns, connect, tls, server, transfer) show how long each
phase took independently. The cumulative fields show elapsed time since request
start. Both are in milliseconds.

## Bottleneck diagnosis

After running httpstat, identify the bottleneck by finding the phase that
consumes the most time relative to total. Then apply the appropriate diagnosis.

### DNS is slow (dns > 50ms)

Typical healthy: 1-20ms (cached) or 20-80ms (cold lookup).

**Likely causes:**
- DNS resolver is far away or overloaded
- Domain has complex CNAME chains
- DNSSEC validation overhead
- No local DNS cache

**Suggestions:**
- Try a faster public resolver: `--resolve host:port:ip` to bypass DNS
- Check if DNS caching is enabled on the machine (`systemd-resolved`, `dnsmasq`)
- Run `dig +trace <domain>` to see the full resolution path
- Compare with `dig @8.8.8.8 <domain>` vs `dig @1.1.1.1 <domain>`

### TCP connect is slow (connect > 100ms)

Typical healthy: 5-50ms (same region), 100-200ms (cross-continent).

**Likely causes:**
- Server is geographically distant
- Network congestion or packet loss
- Server TCP backlog is full (SYN queue saturation)
- Firewall or security group adding latency

**Suggestions:**
- Check server location vs client: `curl -s ipinfo.io/<server-ip>`
- Run from a closer region if possible
- Check for packet loss: `mtr <host>` or `traceroute <host>`
- Compare IPv4 vs IPv6: run httpstat with `-4` and `-6`

### TLS handshake is slow (tls > 200ms)

Typical healthy: 30-100ms (TLS 1.3), 100-250ms (TLS 1.2).

**Likely causes:**
- TLS 1.2 with full handshake (no session resumption)
- OCSP stapling not configured (client does online revocation check)
- Large certificate chain
- Server doing expensive key exchange (RSA vs ECDHE)

**Suggestions:**
- Check TLS version: `curl -v <url> 2>&1 | grep 'SSL connection'`
- Check cert chain size: `openssl s_client -connect host:443 -showcerts`
- Verify OCSP stapling: `openssl s_client -connect host:443 -status`
- TLS 1.3 reduces round trips — check if server supports it

### Server processing is slow (server > 500ms)

This is TTFB minus connection overhead. It reflects backend work.

**Likely causes:**
- Slow database queries
- Missing cache (hitting origin every time)
- Cold start (serverless/lambda functions)
- Upstream dependency latency
- Heavy computation in request handler

**Suggestions:**
- This is an application-level issue, not a network issue
- Check server-side logs and APM tools
- Compare with a simpler endpoint on the same host to isolate
- Run multiple times — if first request is slow but subsequent are fast, it's a cold start
- Add `--slo server=200` to set a threshold and monitor

### Content transfer is slow (transfer > 500ms for small responses)

**Likely causes:**
- Large response body without compression
- Server sending data in small chunks with delays (streaming/SSE)
- Bandwidth limitation between client and server
- Transfer-Encoding: chunked with slow chunk generation

**Suggestions:**
- Check response size: look at Content-Length or `HTTPSTAT_SHOW_BODY=true`
- Verify compression: `-H "Accept-Encoding: gzip"` and check response headers
- If response is large, this may be expected — calculate effective bandwidth
- Compare `HTTPSTAT_SHOW_SPEED=true` output against expected bandwidth

## Diagnostic workflow

Follow this sequence when a user reports a slow endpoint:

1. **Run httpstat with JSON output** to get structured timings
2. **Identify the dominant phase** — which timing is the largest portion of total?
3. **Run 3-5 times** to check for variance (one slow DNS lookup doesn't mean DNS is the problem)
4. **Compare against baselines** — is this endpoint unusually slow, or is the server always like this?
5. **Drill into the bottleneck** using the phase-specific diagnostics above
6. **Set SLO thresholds** if the user wants ongoing monitoring: `--slo total=500,ttfb=300`

### Multiple-run comparison

Run httpstat several times and compare JSON output to distinguish consistent
bottlenecks from transient issues:

```bash
for i in 1 2 3; do
  httpstat <URL> --format json --save "run_$i.json"
done
```

Then compare the `timings_ms` across runs. High variance in one phase suggests
transient issues (DNS cache miss on first run, TLS session resumption on
subsequent runs, etc.).

## Converting curl commands

When a user has an existing curl command, convert it to httpstat by:

1. Replace `curl` with `httpstat`
2. Remove any `-w` (write-out format) flag — httpstat provides its own
3. Remove `-o /dev/null` or `-o <file>` — httpstat handles output
4. Remove `-s` and `-S` — httpstat sets these internally
5. Keep everything else (headers, method, data, auth, etc.)

Example:
```
# Original curl
curl -X POST https://api.example.com/v1/users \
  -H "Authorization: Bearer tok_xxx" \
  -H "Content-Type: application/json" \
  -d '{"name":"test"}' \
  -w "time_total: %{time_total}\n" -o /dev/null -s

# Converted to httpstat
httpstat https://api.example.com/v1/users \
  -X POST \
  -H "Authorization: Bearer tok_xxx" \
  -H "Content-Type: application/json" \
  -d '{"name":"test"}' \
  --format json
```

## SLO key reference

| SLO key | Maps to | What it measures |
|---------|---------|------------------|
| `dns` | time_namelookup | DNS resolution |
| `connect` | time_connect | DNS + TCP connect |
| `tls` | time_pretransfer | DNS + TCP + TLS |
| `ttfb` | time_starttransfer | Time to first byte |
| `total` | time_total | Complete request |

All values in milliseconds. Exit code is `4` when any threshold is exceeded.
