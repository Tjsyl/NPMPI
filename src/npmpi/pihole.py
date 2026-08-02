"""
Pi-hole v6 API client - ported directly from addhost.py / addhome.py / etc.
Same endpoints, same auth flow, unchanged.
"""

from __future__ import annotations

import urllib.parse

import requests

requests.packages.urllib3.disable_warnings()  # pihole admin UIs use self-signed certs


def login(base_url: str, password: str) -> str:
    resp = requests.post(f"{base_url}/api/auth", json={"password": password}, verify=False, timeout=15)
    resp.raise_for_status()
    return resp.json()["session"]["sid"]


def add_host(base_url: str, sid: str, ip: str, hostname: str) -> None:
    value = f"{ip} {hostname}"
    encoded = urllib.parse.quote(value, safe="")
    url = f"{base_url}/api/config/dns%2Fhosts/{encoded}"
    resp = requests.put(url, headers={"X-FTL-SID": sid}, verify=False, timeout=15)
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"{resp.status_code} {resp.text}")


def add_host_safe(base_url: str, sid: str, ip: str, hostname: str) -> str:
    """Like add_host, but treats 'already present' as a soft skip. Returns a status string."""
    value = f"{ip} {hostname}"
    encoded = urllib.parse.quote(value, safe="")
    url = f"{base_url}/api/config/dns%2Fhosts/{encoded}"
    resp = requests.put(url, headers={"X-FTL-SID": sid}, verify=False, timeout=15)
    if resp.status_code in (200, 201, 204):
        return "added"
    if "already present" in resp.text.lower():
        return "already_present"
    raise RuntimeError(f"{resp.status_code} {resp.text}")


def get_hosts(base_url: str, sid: str) -> list[str]:
    """Return the raw list of 'ip hostname' custom DNS record strings."""
    resp = requests.get(
        f"{base_url}/api/config/dns/hosts",
        headers={"X-FTL-SID": sid},
        verify=False,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    # Pi-hole v6 wraps this as {"config": {"dns": {"hosts": [...]}}}
    try:
        return data["config"]["dns"]["hosts"]
    except (KeyError, TypeError):
        return data if isinstance(data, list) else []


def logout(base_url: str, sid: str) -> None:
    try:
        requests.delete(f"{base_url}/api/auth", headers={"X-FTL-SID": sid}, verify=False, timeout=10)
    except Exception:
        pass


def teleporter_export(base_url: str, sid: str) -> bytes:
    """
    Full Pi-hole Teleporter backup (complete config archive: DNS records,
    blocklists, groups, settings - everything, not just custom DNS hosts).
    Same endpoint the web UI's Settings -> Teleporter -> Export button
    calls. Returns the raw archive bytes (Pi-hole v6 packages this as a
    .zip) - write them to disk as-is, don't try to parse/modify them.
    """
    resp = requests.get(
        f"{base_url}/api/teleporter",
        headers={"X-FTL-SID": sid},
        verify=False,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.content
