"""
Nginx Proxy Manager API client - ported directly from addhost.py / addhome.py /
appendhost.py / synchome2m.py / etc. Same endpoints, same request/response
shapes, unchanged.
"""

from __future__ import annotations

from typing import Any

import requests

# How long to wait for an NPM instance to respond before giving up - kept
# short (rather than requests' no-timeout default or a longer value) so a
# site that's expected to be down (e.g. off-VPN) gets reported and skipped
# quickly by callers like `npmpi list`/`npmpi find` instead of hanging.
TIMEOUT = 12


def login(base_url: str, email: str, password: str) -> str:
    resp = requests.post(
        f"{base_url}/api/tokens", json={"identity": email, "secret": password}, timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def get_proxy_hosts(base_url: str, token: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{base_url}/api/nginx/proxy-hosts",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def get_certificates(base_url: str, token: str) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{base_url}/api/nginx/certificates",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def find_cert(hostname: str, certs: list[dict[str, Any]]) -> int:
    for cert in certs:
        for cd in cert.get("domain_names", []):
            if cd == hostname:
                return cert["id"]
            if cd.startswith("*.") and hostname.endswith(cd[1:]):
                return cert["id"]
    return 0


def find_proxy_host(hostname: str, hosts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for h in hosts:
        if hostname in h.get("domain_names", []):
            return h
    return None


def find_proxy_host_by_backend(
    scheme: str, backend_ip: str, backend_port: int | str, hosts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Find an existing proxy host that already forwards to this exact
    scheme/IP/port, regardless of hostname. Used so a second hostname for
    the same backend gets appended onto that host's domain_names instead of
    creating a second, duplicate proxy host pointed at the same place."""
    port = int(backend_port)
    for h in hosts:
        if (
            h.get("forward_scheme") == scheme
            and h.get("forward_host") == backend_ip
            and int(h.get("forward_port", -1)) == port
        ):
            return h
    return None


def create_proxy_host(
    base_url: str, token: str, hostnames: list[str], scheme: str,
    backend_ip: str, backend_port: int | str, cert_id: int,
) -> dict[str, Any]:
    body = {
        "domain_names": hostnames,
        "forward_scheme": scheme,
        "forward_host": backend_ip,
        "forward_port": int(backend_port),
        "access_list_id": 0,
        "certificate_id": cert_id,
        "ssl_forced": bool(cert_id),
        "http2_support": bool(cert_id),
        "block_exploits": False,
        "caching_enabled": False,
        "allow_websocket_upgrade": True,
        "meta": {},
        "advanced_config": "",
        "locations": [],
    }
    resp = requests.post(
        f"{base_url}/api/nginx/proxy-hosts",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    return resp.json()


def update_proxy_host_add_names(
    base_url: str, token: str, host: dict[str, Any], new_names: list[str],
) -> list[str]:
    """Append new_names (aliases) onto an existing proxy host, keeping everything else unchanged."""
    domain_names = list(dict.fromkeys(host["domain_names"] + new_names))  # de-dup, preserve order

    certificate_id = host.get("certificate_id", 0)
    cert_newly_matched = False
    if not certificate_id:
        certs = get_certificates(base_url, token)
        for n in new_names:
            certificate_id = find_cert(n, certs)
            if certificate_id:
                cert_newly_matched = True
                break

    body = {
        "domain_names": domain_names,
        "forward_scheme": host["forward_scheme"],
        "forward_host": host["forward_host"],
        "forward_port": host["forward_port"],
        "access_list_id": host.get("access_list_id", 0),
        "certificate_id": certificate_id,
        "ssl_forced": host.get("ssl_forced", False) or cert_newly_matched,
        "http2_support": host.get("http2_support", False),
        "block_exploits": host.get("block_exploits", False),
        "caching_enabled": host.get("caching_enabled", False),
        "allow_websocket_upgrade": host.get("allow_websocket_upgrade", True),
        "meta": host.get("meta", {}),
        "advanced_config": host.get("advanced_config", ""),
        "locations": host.get("locations", []),
    }
    resp = requests.put(
        f"{base_url}/api/nginx/proxy-hosts/{host['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    return domain_names


def update_proxy_host_backend(
    base_url: str, token: str, host: dict[str, Any], backend_ip: str, backend_port: int | str,
) -> dict[str, Any]:
    """Change just the backend forward_host/forward_port on an existing
    proxy host - domain_names, cert, and every other setting untouched.
    Used by the GUI's List/Find inline IP/Port edit."""
    body = {
        "domain_names": host["domain_names"],
        "forward_scheme": host["forward_scheme"],
        "forward_host": backend_ip,
        "forward_port": int(backend_port),
        "access_list_id": host.get("access_list_id", 0),
        "certificate_id": host.get("certificate_id", 0),
        "ssl_forced": host.get("ssl_forced", False),
        "http2_support": host.get("http2_support", False),
        "block_exploits": host.get("block_exploits", False),
        "caching_enabled": host.get("caching_enabled", False),
        "allow_websocket_upgrade": host.get("allow_websocket_upgrade", True),
        "meta": host.get("meta", {}),
        "advanced_config": host.get("advanced_config", ""),
        "locations": host.get("locations", []),
    }
    resp = requests.put(
        f"{base_url}/api/nginx/proxy-hosts/{host['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    return resp.json()


def domains_for_suffix(host: dict[str, Any], suffix: str) -> list[str]:
    return [d for d in host.get("domain_names", []) if d == suffix or d.endswith("." + suffix)]


def delete_proxy_host(base_url: str, token: str, host_id: int) -> None:
    """Delete a proxy host entirely (all of its domain names go with it)."""
    resp = requests.delete(
        f"{base_url}/api/nginx/proxy-hosts/{host_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")


def update_proxy_host_remove_names(
    base_url: str, token: str, host: dict[str, Any], names_to_remove: list[str],
) -> list[str]:
    """Remove names_to_remove from an existing proxy host's domain_names,
    keeping everything else (backend, cert, etc.) unchanged - the mirror
    image of update_proxy_host_add_names. The host itself is left in place
    even if only one name remains. Raises if this would strip every domain
    name off the host (NPM requires at least one) - callers should route
    that case through delete_proxy_host instead."""
    domain_names = [d for d in host["domain_names"] if d not in names_to_remove]
    if not domain_names:
        raise ValueError("Cannot remove every domain name from a proxy host - delete the host instead.")

    body = {
        "domain_names": domain_names,
        "forward_scheme": host["forward_scheme"],
        "forward_host": host["forward_host"],
        "forward_port": host["forward_port"],
        "access_list_id": host.get("access_list_id", 0),
        "certificate_id": host.get("certificate_id", 0),
        "ssl_forced": host.get("ssl_forced", False),
        "http2_support": host.get("http2_support", False),
        "block_exploits": host.get("block_exploits", False),
        "caching_enabled": host.get("caching_enabled", False),
        "allow_websocket_upgrade": host.get("allow_websocket_upgrade", True),
        "meta": host.get("meta", {}),
        "advanced_config": host.get("advanced_config", ""),
        "locations": host.get("locations", []),
    }
    resp = requests.put(
        f"{base_url}/api/nginx/proxy-hosts/{host['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=TIMEOUT,
    )
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.text}")
    return domain_names
