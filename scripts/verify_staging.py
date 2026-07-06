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
import sys

import requests


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


def run(cmd):
    try:
        r = subprocess.run(cmd, shell=False, check=False, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)


def resolve(domain):
    try:
        addrs = socket.getaddrinfo(domain, None)
        ips = sorted({ai[4][0] for ai in addrs})
        return ips
    except Exception as e:
        print(f"DNS resolution failed: {e}")
        return []


def https_check(domain):
    print(f"Checking HTTPS GET {domain}")
    try:
        r = requests.get(f"https://{domain}", timeout=10)
        print(f"Status: {r.status_code}")
        print("Server:", r.headers.get("server"))
        print("Via:", r.headers.get("via"))
        body = r.text[:400]
        print("Body preview:", body.replace("\n", " "))
        return r.status_code, r.headers, r.text
    except requests.exceptions.SSLError as e:
        print("SSL error when connecting (expected if using origin cert locally):", e)
    except Exception as e:
        print("HTTPS request failed:", e)
    return None, None, None


def format_host(host):
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def curl_resolve_check(domain, ip):
    print(f"Curl with --resolve to {ip} (HTTPS)")
    cmd = ["curl", "-I", "-k", "--resolve", f"{domain}:443:{ip}", f"https://{domain}", "-m", "10"]
    return run(cmd)


def ip_port_check(ip, port):
    print(f"Checking {ip}:{port}")
    url = f"http://{format_host(ip)}:{port}"
    cmd = ["curl", "-I", "--max-time", "5", url, "-sS"]
    return run(cmd)


def main():
    args = parse_args()
    domain = get_domain(args.domain_flag or args.domain)

    ips = resolve(domain)
    print("Resolved IPs:", ips)
    print("\n--- External HTTPS check ---")
    https_check(domain)

    print("\n--- Per-IP HTTPS via --resolve ---")
    for ip in ips:
        code, out = curl_resolve_check(domain, ip)
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
    # Look for signs of Access in headers or body
    code, headers, body = https_check(domain)
    if headers:
        loc = headers.get("location", "")
        if "cloudflare" in loc.lower() or "access" in loc.lower():
            print("Redirects to Cloudflare Access login (heuristic)")
        if headers.get("server", "").lower().find("cloudflare") != -1:
            print("Server header is Cloudflare (expected)")
    if body and ("Cloudflare" in body or "Access" in body or "access" in body.lower()):
        print("Found Cloudflare/Access text in body (heuristic)")

    print("\nDone. For interactive Access login verification, open https://" + domain)


if __name__ == "__main__":
    main()
