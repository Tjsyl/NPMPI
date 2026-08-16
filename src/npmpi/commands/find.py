"""
npmpi find - search for a hostname/backend across every configured site (or
just one), printing a match using the same column table as `npmpi list`.

    npmpi find esxi             every site
    npmpi find portainer        every site
    npmpi find h esxi           site 'h' only

Same '[SITE] TERM' convention as `npmpi list`: if the first word is a
configured site letter, it restricts the search to that site instead of
checking every one. When checking multiple sites, only sites with at least
one match are printed - a site with nothing matching is skipped silently
rather than printing an empty "(no matches)" table for it. If the term
isn't found anywhere it was checked, that's reported once instead.
"""

from __future__ import annotations

import argparse

from npmpi import npm as npm_api
from npmpi.commands.list import group_by_backend, matches, render_table, split_args
from npmpi.creds import get_npm_password


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "find",
        help="Search for a hostname/backend across one or every site, printed as a list-style table",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "args", nargs="+", metavar="[SITE] TERM",
        help="Optional site letter, then the search term, e.g. 'h esxi' or just 'esxi' for every site",
    )
    p.set_defaults(func=cmd_find)


def cmd_find(cfg, creds, args) -> int:
    site_keys = list(cfg["sites"].keys())
    site, query = split_args(args.args, site_keys)
    if not query:
        raise SystemExit("npmpi find: missing search TERM (got only a site letter). "
                          "Run `npmpi -e` for full syntax and examples.")
    sites_to_check = [site] if site else site_keys

    found_any = False
    unreachable = []
    for site_key in sites_to_check:
        site_cfg = cfg["sites"][site_key]
        npm_cfg = site_cfg["npm"]
        try:
            pw = get_npm_password(creds, site_key)
            token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
            hosts = npm_api.get_proxy_hosts(npm_cfg["url"], token)
        except Exception as e:
            print(f"[site '{site_key}'] UNREACHABLE: {e} - skipping")
            unreachable.append(site_key)
            continue

        groups = group_by_backend(hosts)
        groups.sort(key=lambda g: (g[0][1], g[0][2]))  # sort by backend IP, then port
        groups = [g for g in groups if matches(query, g[0][1], g[1])]

        if not groups:
            continue

        found_any = True
        print(f"\n--- site '{site_key}' ({npm_cfg['url']}) ---\n")
        for line in render_table(groups):
            print(line)

    if not found_any:
        if site:
            scope = f"site '{site}'" if not unreachable else f"site '{site}' (unreachable)"
        else:
            scope = "any reachable site" if unreachable else "any configured site"
        print(f"No proxy host matching '{query}' found on {scope}.")
        return 1

    if unreachable:
        print(f"\n(could not check: {', '.join(unreachable)})")

    return 0
