#!/usr/bin/env python3
"""Verify GeoVis LM staging reachability and Cloudflare Access heuristics.

Usage: python3 scripts/verify_staging.py

This script does NOT perform login. It checks DNS, HTTPS headers, Caddy/Cf presence,
and whether the app port 8000 is reachable externally (it should NOT be).
"""
import socket
import subprocess
import requests
import sys

DOMAIN = "geovis.nextgenbytes.me"

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True, timeout=15)
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
        print("Server:", r.headers.get('server'))
        print("Via:", r.headers.get('via'))
        body = r.text[:400]
        print("Body preview:", body.replace('\n',' ') )
        return r.status_code, r.headers, r.text
    except requests.exceptions.SSLError as e:
        print("SSL error when connecting (expected if using origin cert locally):", e)
    except Exception as e:
        print("HTTPS request failed:", e)
    return None, None, None

def curl_resolve_check(ip):
    print(f"Curl with --resolve to {ip} (HTTPS)")
    cmd = f"curl -I -k --resolve {DOMAIN}:443:{ip} https://{DOMAIN} -m 10"
    return run(cmd)

def ip_port_check(ip, port):
    print(f"Checking {ip}:{port}")
    cmd = f"curl -I --max-time 5 http://{ip}:{port} -sS || true"
    return run(cmd)

def main():
    ips = resolve(DOMAIN)
    print("Resolved IPs:", ips)
    print('\n--- External HTTPS check ---')
    https_check(DOMAIN)

    print('\n--- Per-IP HTTPS via --resolve ---')
    for ip in ips:
        code, out = curl_resolve_check(ip)
        print(out)

    print('\n--- Check port 8000 on resolved IPs (should be refused externally) ---')
    for ip in ips:
        code, out = ip_port_check(ip, 8000)
        print(out)

    # Try public-facing IP of this host if available
    try:
        host_ip = requests.get('https://ifconfig.me', timeout=5).text.strip()
    except Exception:
        host_ip = None
    if host_ip:
        print('\n--- Check host public IP 8000 ---')
        code, out = ip_port_check(host_ip, 8000)
        print(out)

    print('\n--- Heuristic: Cloudflare Access detection ---')
    # Look for signs of Access in headers or body
    code, headers, body = https_check(DOMAIN)
    if headers:
        loc = headers.get('location','')
        if 'cloudflare' in loc.lower() or 'access' in loc.lower():
            print('Redirects to Cloudflare Access login (heuristic)')
        if headers.get('server','').lower().find('cloudflare') != -1:
            print('Server header is Cloudflare (expected)')
    if body and ('Cloudflare' in body or 'Access' in body or 'access' in body.lower()):
        print('Found Cloudflare/Access text in body (heuristic)')

    print('\nDone. For interactive Access login verification, open https://' + DOMAIN)

if __name__ == '__main__':
    main()
