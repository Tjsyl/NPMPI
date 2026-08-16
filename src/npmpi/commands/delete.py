"""
npmpi delete - remove a hostname (and its Pi-hole DNS record(s)) from NPM,
either as an alias or as the entire proxy host it belongs to.

    npmpi delete [SITE]           list everything (or just SITE), numbered,
                                   then asks which number to delete
    npmpi delete [SITE] TERM      same '[SITE] TERM' convention as `npmpi
                                   find` - if TERM uniquely matches one
                                   entry, skips straight to the
                                   confirmation prompt instead of listing

Every proxy host's domain name is numbered - the PRIMARY name (the first,
alphabetically, of a host - the one with HTTP/HTTPS, IP, and PORT shown)
and every ALIAS (an extra domain name sharing that same backend) each get
their own number.

Selecting a PRIMARY deletes the ENTIRE proxy host: every domain name on
it, from NPM, plus the Pi-hole DNS record for each of them on this site's
pihole(s).

Selecting an ALIAS removes ONLY that one domain name from NPM (the proxy
host, its backend, and its other domain names are left alone), plus that
one domain name's own Pi-hole DNS record on this site's pihole(s) - it
got its own record when it was added, same as any primary.

Only ever acts on the ONE site the selected entry belongs to - a hostname
mirrored onto another site via `npmpi add multi` is a completely separate
proxy host there and needs its own separate delete.

Always asks for a yes/no confirmation before touching anything - picking a
number never deletes by itself.
"""

from __future__ import annotations

import argparse

from npmpi import npm as npm_api
from npmpi.commands import list as list_cmd
from npmpi.creds import get_npm_password
from npmpi.netops import remove_dns_from_site


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "delete",
        help="Remove a hostname (alias) or an entire proxy host from NPM/Pi-hole",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "args", nargs="*", metavar="[SITE] [TERM]",
        help="Optional site letter and/or a search term - same convention as `npmpi list`/`npmpi find`",
    )
    p.set_defaults(func=cmd_delete)


class _Entry:
    """One selectable line: a single domain name on a real NPM host record
    (never merged across two different hosts, even if they happen to share
    a backend - that merging is fine for list/find's read-only display but
    not safe to delete against)."""

    __slots__ = ("site_key", "host", "domain", "is_primary")

    def __init__(self, site_key: str, host: dict, domain: str, is_primary: bool) -> None:
        self.site_key = site_key
        self.host = host
        self.domain = domain
        self.is_primary = is_primary


def _join_and(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _build_entries(cfg: dict, creds: dict, site_keys: list[str]) -> tuple[list["_Entry"], list[str]]:
    entries: list[_Entry] = []
    unreachable: list[str] = []
    for site_key in site_keys:
        site = cfg["sites"][site_key]
        npm_cfg = site["npm"]
        try:
            pw = get_npm_password(creds, site_key)
            token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
            hosts = npm_api.get_proxy_hosts(npm_cfg["url"], token)
        except Exception as e:  # noqa: BLE001 - reported, not swallowed
            print(f"\n--- site '{site_key}' ({npm_cfg['url']}) --- UNREACHABLE: {e}")
            unreachable.append(site_key)
            continue
        for host in hosts:
            if not host.get("enabled", True):
                continue
            domains = sorted(host.get("domain_names", []), key=str.lower)
            for i, d in enumerate(domains):
                entries.append(_Entry(site_key, host, d, i == 0))
    return entries, unreachable


def _entry_matches(query: str | None, e: "_Entry") -> bool:
    if not query:
        return True
    q = query.lower()
    if q in e.domain.lower():
        return True
    return q in e.host.get("forward_host", "").lower()


def _print_numbered(entries: list["_Entry"]) -> None:
    current_site = None
    for n, e in enumerate(entries, start=1):
        if e.site_key != current_site:
            print(f"\n--- site '{e.site_key}' ---\n")
            current_site = e.site_key
        if e.is_primary:
            scheme = e.host.get("forward_scheme", "http").upper()
            ip = e.host.get("forward_host", "")
            port = e.host.get("forward_port", "")
            print(f"  {n}. {scheme}  {e.domain}  {ip}:{port}")
        else:
            print(f"  {n}.      {e.domain}  (alias)")


def _pihole_str(cfg: dict, site_key: str) -> str:
    pihole_names = [ph["name"] for ph in cfg["sites"][site_key].get("piholes", [])]
    return _join_and(pihole_names) if pihole_names else "(no piholes configured on this site)"


def _confirm_message(cfg: dict, e: "_Entry") -> str:
    scheme = e.host.get("forward_scheme", "http")
    pihole_str = _pihole_str(cfg, e.site_key)
    if e.is_primary:
        domains = sorted(e.host.get("domain_names", []), key=str.lower)
        names_str = ", ".join(domains)
        ip = e.host.get("forward_host", "")
        port = e.host.get("forward_port", "")
        return (
            f"Are you sure you want to remove {scheme}://{names_str} {ip} at port {port} "
            f"from NPM and its DNS records from {pihole_str}?"
        )
    return (
        f"Are you sure you want to remove the {scheme}://{e.domain} additional domain name "
        f"from NPM and its DNS record from {pihole_str}?"
    )


def _confirm(cfg: dict, e: "_Entry") -> bool:
    return input(_confirm_message(cfg, e) + " (y/N): ").strip().lower() in ("y", "yes")


def _delete_host(cfg: dict, creds: dict, site_key: str, host: dict) -> list[str]:
    """Delete an NPM proxy host entirely, plus the Pi-hole DNS record for
    every one of its domain names on this site's pihole(s). Non-interactive
    - the caller (the CLI wizard above, or the GUI) confirms first."""
    site = cfg["sites"][site_key]
    npm_cfg = site["npm"]
    domain_names = host.get("domain_names", [])
    scheme = host.get("forward_scheme", "http")
    backend_ip = host.get("forward_host", "")
    backend_port = host.get("forward_port", "")

    print(f"\n=== deleting {', '.join(domain_names)} -> {scheme}://{backend_ip}:{backend_port}  (site '{site_key}') ===")
    failures = remove_dns_from_site(site, creds, site_key, domain_names, site["npm_target_ip"])

    try:
        pw = get_npm_password(creds, site_key)
        token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
        npm_api.delete_proxy_host(npm_cfg["url"], token, host["id"])
        print(f"[npm({site_key})] deleted proxy host #{host['id']} ({', '.join(domain_names)})")
    except Exception as e:  # noqa: BLE001
        print(f"[npm({site_key})] FAILED to delete: {e}")
        failures.append(f"npm({site_key})")
    return failures


def _delete_alias(cfg: dict, creds: dict, site_key: str, host: dict, domain_names: list[str]) -> list[str]:
    """Remove one or more domain names from an existing NPM proxy host - the
    host, its backend, and any other domain names on it are untouched -
    plus each removed domain's own Pi-hole DNS record on this site's
    pihole(s) (every domain gets its own record when added, same as any
    primary). Batched into a single NPM update + a single DNS-removal pass
    (rather than one call per name) so removing more than one alias off
    the SAME host in one go can't race against a `host` dict that's gone
    stale after the first name was already removed from it - see
    `_group_for_batch()`. Non-interactive - the caller (the CLI wizard
    above, or the GUI) confirms first."""
    site = cfg["sites"][site_key]
    npm_cfg = site["npm"]
    names_str = ", ".join(domain_names)
    print(f"\n=== removing alias(es) {names_str} from NPM host #{host['id']} and their DNS record(s) (site '{site_key}') ===")
    failures = remove_dns_from_site(site, creds, site_key, domain_names, site["npm_target_ip"])

    try:
        pw = get_npm_password(creds, site_key)
        token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
        remaining = npm_api.update_proxy_host_remove_names(npm_cfg["url"], token, host, domain_names)
        print(f"[npm({site_key})] removed {names_str} - remaining on this host: {', '.join(remaining)}")
    except Exception as e:  # noqa: BLE001
        print(f"[npm({site_key})] FAILED to remove {names_str}: {e}")
        failures.append(f"npm({site_key})")
    return failures


def _dedupe_for_batch(entries: list["_Entry"]) -> list["_Entry"]:
    """Given a set of selected entries (possibly a mix of primaries and
    aliases, possibly spanning multiple hosts/sites - used by the GUI's
    multi-select Delete), drop any alias entry whose own host is ALSO
    selected as a primary in the same batch. That alias is already
    covered: deleting the primary removes every domain name on the host,
    the alias included, so processing it again would just fail against an
    already-deleted host."""
    primary_hosts = {(e.site_key, e.host["id"]) for e in entries if e.is_primary}
    return [e for e in entries if e.is_primary or (e.site_key, e.host["id"]) not in primary_hosts]


def _group_for_batch(entries: list["_Entry"]) -> list[tuple[tuple[str, int], list["_Entry"]]]:
    """Group a (deduped) entry list into per-real-host units, preserving
    first-seen order: either a single PRIMARY entry (whole host + all its
    domain names), or one-or-more ALIAS entries that all belong to the
    same host record, batched together so they're removed in one NPM
    update instead of one call per alias."""
    groups: dict[tuple[str, int], list[_Entry]] = {}
    order: list[tuple[str, int]] = []
    for e in entries:
        key = (e.site_key, e.host["id"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(e)
    return [(key, groups[key]) for key in order]


def confirm_message_for_selection(cfg: dict, entries: list["_Entry"]) -> str:
    """Build one confirmation message covering an arbitrary set of selected
    entries - used by the GUI's multi-select Delete (the CLI only ever
    selects one entry at a time and uses _confirm_message() directly).
    Falls back to the exact single-entry wording when there's only one
    line to show, so a single-row GUI selection reads identically to the
    CLI's prompt for the same entry."""
    deduped = _dedupe_for_batch(entries)
    lines = []
    for (site_key, _host_id), group in _group_for_batch(deduped):
        if group[0].is_primary:
            lines.append(_confirm_message(cfg, group[0]))
        else:
            scheme = group[0].host.get("forward_scheme", "http")
            names = ", ".join(e.domain for e in group)
            pihole_str = _pihole_str(cfg, site_key)
            plural = "s" if len(group) > 1 else ""
            lines.append(
                f"Are you sure you want to remove the {scheme}://{names} additional domain name{plural} "
                f"from NPM and {'their' if plural else 'its'} DNS record{plural} from {pihole_str}?"
            )
    if len(lines) == 1:
        return lines[0]
    numbered = "\n\n".join(f"{i}. {line}" for i, line in enumerate(lines, start=1))
    return f"Are you sure you want to do the following {len(lines)} deletions?\n\n{numbered}"


def delete_selection(cfg: dict, creds: dict, entries: list["_Entry"]) -> list[str]:
    """Execute a (possibly multi-row) delete non-interactively - the GUI
    confirms first via confirm_message_for_selection(). Dedupes/batches
    exactly the same way that function does, so what got shown in the
    confirmation is exactly what gets deleted."""
    deduped = _dedupe_for_batch(entries)
    failures: list[str] = []
    for (site_key, _host_id), group in _group_for_batch(deduped):
        if group[0].is_primary:
            failures += _delete_host(cfg, creds, site_key, group[0].host)
        else:
            failures += _delete_alias(cfg, creds, site_key, group[0].host, [e.domain for e in group])
    return failures


def cmd_delete(cfg: dict, creds: dict, args) -> int:
    site_keys = list(cfg["sites"].keys())
    site, query = list_cmd.split_args(args.args, site_keys)
    sites_to_check = [site] if site else site_keys

    all_entries, unreachable = _build_entries(cfg, creds, sites_to_check)
    entries = [e for e in all_entries if _entry_matches(query, e)]

    if not entries:
        print("(no matches)" if query else "(nothing to delete)")
        return 1 if unreachable else 0

    if query and len(entries) == 1:
        selected = entries[0]
    else:
        _print_numbered(entries)
        raw = input("\nPlease select a number (blank to cancel): ").strip()
        if not raw:
            print("Cancelled.")
            return 0
        if not raw.isdigit() or not (1 <= int(raw) <= len(entries)):
            print(f"'{raw}' isn't a valid number 1-{len(entries)}.")
            return 1
        selected = entries[int(raw) - 1]

    if not _confirm(cfg, selected):
        print("Cancelled.")
        return 0

    if selected.is_primary:
        failures = _delete_host(cfg, creds, selected.site_key, selected.host)
    else:
        failures = _delete_alias(cfg, creds, selected.site_key, selected.host, [selected.domain])

    print()
    if failures:
        print(f"Completed with failures in: {', '.join(failures)}")
        return 1
    print("Done.")
    return 0
