"""
Shared operations that both `npmpi add` and `npmpi sync` use: pushing a
Pi-hole DNS record to every pihole on a site, and creating (or idempotently
skipping) an NPM proxy host. Kept in one place so add/sync/append behavior
can't drift apart from each other.
"""

from __future__ import annotations

from typing import Any

from npmpi import npm as npm_api
from npmpi import pihole as pihole_api
from npmpi.creds import get_npm_password, get_pihole_password


def push_dns_to_site(site_cfg: dict[str, Any], creds: dict, site_key: str,
                      hostnames: list[str], target_ip: str) -> list[str]:
    """Push each hostname to every pihole configured for this site. Returns list of failure strings."""
    failures = []
    for ph in site_cfg["piholes"]:
        name = ph["name"]
        try:
            pw = get_pihole_password(creds, site_key, name)
            print(f"\n[{name}] logging in to {ph['url']} ...")
            sid = pihole_api.login(ph["url"], pw)
            try:
                for h in hostnames:
                    status = pihole_api.add_host_safe(ph["url"], sid, target_ip, h)
                    if status == "added":
                        print(f"[{name}] added: {target_ip} {h}")
                    else:
                        print(f"[{name}] {h} already present, skipping")
            finally:
                pihole_api.logout(ph["url"], sid)
        except Exception as e:
            print(f"[{name}] FAILED: {e}")
            failures.append(name)
    return failures


def create_or_skip_proxy_host(site_cfg: dict[str, Any], creds: dict, site_key: str,
                               hostnames: list[str], scheme: str, backend_ip: str,
                               backend_port: int | str, label: str) -> tuple[bool, str]:
    """
    Create a new proxy host for hostnames[0..] on this site's NPM. If a host
    with hostnames[0] already exists, this is treated as idempotent success
    (not an error) - matches the "auto-detect, don't hard-fail" behavior
    npmpi add uses instead of the old separate append* scripts.
    Returns (ok, message).
    """
    npm_cfg = site_cfg["npm"]
    pw = get_npm_password(creds, site_key)
    print(f"\n[{label}] logging in to {npm_cfg['url']} ...")
    token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)

    existing = npm_api.get_proxy_hosts(npm_cfg["url"], token)
    already = npm_api.find_proxy_host(hostnames[0], existing)
    if already is not None:
        msg = f"[{label}] {hostnames[0]} already exists on this NPM (host #{already['id']}) - leaving as-is"
        print(msg)
        return True, msg

    certs = npm_api.get_certificates(npm_cfg["url"], token)
    cert_id = npm_api.find_cert(hostnames[0], certs)
    npm_api.create_proxy_host(npm_cfg["url"], token, hostnames, scheme, backend_ip, backend_port, cert_id)
    cert_note = "with matched SSL cert" if cert_id else "NO SSL cert matched - created without SSL"
    names = ", ".join(hostnames)
    msg = f"[{label}] created proxy host: {names} -> {scheme}://{backend_ip}:{backend_port} ({cert_note})"
    print(msg)
    return True, msg
