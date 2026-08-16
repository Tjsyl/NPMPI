"""
npmpi list - show every proxy host on one or all configured sites' NPM as a
column table, with an optional search filter.

    npmpi list                  every host on every configured site
    npmpi list h                every host on site 'h' only
    npmpi list prowl            every site, filtered to hosts whose full
                                 hostname or backend IP contains "prowl"
    npmpi list h prowl          site 'h' only, filtered to "prowl"

Columns: HTTP/HTTPS, HOST, IP, PORT. Hosts that share the same backend
(scheme + IP + port) are grouped together - the first row of the group has
all four columns filled in, and every other hostname that forwards to that
same backend gets its own row below with only HOST filled in. This is
exactly the case `npmpi add` now auto-detects and appends onto instead of
creating a duplicate proxy host for, so this is also the fastest way to
check "is this IP:port already in use, and under what name(s)?" before
adding a new one.
"""

from __future__ import annotations

import argparse

from npmpi import npm as npm_api
from npmpi.creds import get_npm_password

_HEADER = ("HTTP/HTTPS", "HOST", "IP", "PORT")
_COL_GAP = "  "


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "list",
        help="List every proxy host as a column table, with an optional search filter",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "args", nargs="*", metavar="[SITE] [SEARCH]",
        help="Optional site letter and/or a search term, e.g. 'h prowl', just 'prowl', or nothing for everything",
    )
    p.set_defaults(func=cmd_list)


def split_args(raw_args: list[str], site_keys: list[str]) -> tuple[str | None, str | None]:
    """Split '[SITE] [SEARCH...]' positional args: if the first token is a
    configured site letter, it's pulled out as the site restriction and
    everything else is joined back into the search term. Shared with
    `npmpi find`, which uses the exact same '[SITE] TERM' convention."""
    rest = list(raw_args)
    site = None
    if rest and rest[0] in site_keys:
        site = rest.pop(0)
    query = " ".join(rest) if rest else None
    return site, query


def group_by_backend(hosts: list[dict]) -> list[tuple[tuple[str, str, int], list[str]]]:
    """Group enabled hosts by (forward_scheme, forward_host, forward_port),
    preserving each group's first-seen order but returning domain lists
    de-duplicated and un-sorted (caller sorts for display)."""
    groups: dict[tuple[str, str, int], list[str]] = {}
    order: list[tuple[str, str, int]] = []
    for h in hosts:
        if not h.get("enabled", True):
            continue
        key = (h.get("forward_scheme") or "http", h.get("forward_host") or "", h.get("forward_port") or 0)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].extend(h.get("domain_names", []))
    return [(key, groups[key]) for key in order]


def matches(query: str | None, backend_ip: str, domains: list[str]) -> bool:
    if not query:
        return True
    q = query.lower()
    if q in backend_ip.lower():
        return True
    return any(q in d.lower() for d in domains)


def build_rows(groups: list[tuple[tuple[str, str, int], list[str]]]) -> list[tuple[str, str, str, str]]:
    """One row per (group boundary, hostname): the first hostname in a group
    carries scheme/ip/port, every other hostname in that group is host-only."""
    rows = []
    for (scheme, ip, port), domains in groups:
        for i, d in enumerate(sorted(domains, key=str.lower)):
            if i == 0:
                rows.append((scheme.upper(), d, ip, str(port)))
            else:
                rows.append(("", d, "", ""))
    return rows


def render_table(groups: list[tuple[tuple[str, str, int], list[str]]]) -> list[str]:
    """Render groups as the fixed-column table: header row, then a blank
    line before each group, then that group's rows (first row full, any
    aliases below it with only HOST filled in)."""
    all_rows = [_HEADER] + build_rows(groups)
    widths = [max(len(r[i]) for r in all_rows) for i in range(4)]

    def fmt(row: tuple[str, str, str, str]) -> str:
        return _COL_GAP.join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()

    lines = [fmt(_HEADER)]
    for (scheme, ip, port), domains in groups:
        lines.append("")
        domains_sorted = sorted(domains, key=str.lower)
        for i, d in enumerate(domains_sorted):
            row = (scheme.upper(), d, ip, str(port)) if i == 0 else ("", d, "", "")
            lines.append(fmt(row))
    return lines


def _print_site(site_key: str, npm_url: str, hosts: list[dict], query: str | None) -> int:
    print(f"\n--- site '{site_key}' ({npm_url}) ---\n")
    groups = group_by_backend(hosts)
    groups.sort(key=lambda g: (g[0][1], g[0][2]))  # sort by backend IP, then port
    groups = [g for g in groups if matches(query, g[0][1], g[1])]

    if not groups:
        print("(no matches)" if query else "(no proxy hosts)")
        return 0

    for line in render_table(groups):
        print(line)
    return len(groups)


def cmd_list(cfg, creds, args) -> int:
    site_keys = list(cfg["sites"].keys())
    site, query = split_args(args.args, site_keys)
    sites_to_check = [site] if site else site_keys

    total = 0
    unreachable = []
    for site_key in sites_to_check:
        site_cfg = cfg["sites"][site_key]
        npm_cfg = site_cfg["npm"]
        try:
            pw = get_npm_password(creds, site_key)
            token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
            hosts = npm_api.get_proxy_hosts(npm_cfg["url"], token)
        except Exception as e:
            print(f"\n--- site '{site_key}' ({npm_cfg['url']}) --- UNREACHABLE: {e}")
            unreachable.append(site_key)
            continue
        total += _print_site(site_key, npm_cfg["url"], hosts, query)

    reached = len(sites_to_check) - len(unreachable)
    print(f"\n{total} backend(s) shown across {reached} of {len(sites_to_check)} site(s).")
    if unreachable:
        print(f"Could not reach: {', '.join(unreachable)}")
        return 1
    return 0
