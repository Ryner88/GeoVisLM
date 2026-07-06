#!/usr/bin/env python3
"""Verify GeoVis LM staging reachability and Cloudflare Access heuristics.

Usage: python3 scripts/verify_staging.py [domain]

This script does NOT perform login. It checks DNS, HTTPS headers, Caddy/CF presence,
and whether the app port 8000 is reachable externally (it should NOT be).
"""
import argparse
import os
import socket
import subprocess

import requests

from staging_helpers import (
    https_check,
    normalize_staging_target,
    print_cloudflare_access_heuristics,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "domain",
        nargs="?",
        default=None,
        help="Hostname to verify (defaults to VERIFY_DOMAIN, DOMAIN, or geovis.nextgenbytes.me)",
    )
    parser.add_argument(
        "--domain",
        dest="domain_flag",
        default=None,
        help="Hostname or URL to verify (overrides positional argument)",
    )
    return parser.parse_args()


def get_domain(cli_domain):
    return cli_domain or os.environ.get("VERIFY_DOMAIN") or os.environ.get("DOMAIN") or "geovis.nextgenbytes.me"


def run_curl(args):
    for arg in args:
        if not isinstance(arg, str) or "\x00" in arg:
            raise ValueError("invalid curl argument")
    cmd = ["curl", *args]
    try:
        # shell=False and the fixed executable keep user-controlled host/IP values as argv,
        # not shell syntax. Arguments are assembled only by this script.
        r = subprocess.run(cmd, shell=False, check=False, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)


def resolve(host):
    try:
        addrs = socket.getaddrinfo(host, None)
        ips = sorted({ai[4][0] for ai in addrs})
        return ips
    except Exception as e:
        print(f"DNS resolution failed: {e}")
        return []


def format_host(host):
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def curl_resolve_check(target, ip):
    print(f"Curl with --resolve to {ip} (HTTPS)")
    return run_curl(["-I", "-k", "--resolve", f"{target.host}:{target.port}:{ip}", target.url, "-m", "10"])


def ip_port_check(ip, port):
    print(f"Checking {ip}:{port}")
    url = f"http://{format_host(ip)}:{port}"
    return run_curl(["-I", "--max-time", "5", url, "-sS"])


def main():
    args = parse_args()
    target = normalize_staging_target(get_domain(args.domain_flag or args.domain))

    ips = resolve(target.host)
    print("Resolved IPs:", ips)
    print("\n--- External HTTPS check ---")
    https_check(target)

    print("\n--- Per-IP HTTPS via --resolve ---")
    for ip in ips:
        code, out = curl_resolve_check(target, ip)
        print(out)

    print("\n--- Check port 8000 on resolved IPs (should be refused externally) ---")
    for ip in ips:
        code, out = ip_port_check(ip, 8000)
        print(out)

    # Try public-facing IP of this host if available
    try:
        host_ip = requests.get("https://ifconfig.me", timeout=5).text.strip()
    except Exception:
        host_ip = None
    if host_ip:
        print("\n--- Check host public IP 8000 ---")
        code, out = ip_port_check(host_ip, 8000)
        print(out)

    print("\n--- Heuristic: Cloudflare Access detection ---")
    code, headers, body = https_check(target)
    print_cloudflare_access_heuristics(headers, body)

    print("\nDone. For interactive Access login verification, open " + target.url)


if __name__ == "__main__":
    main()
