"""
npmpi add - create a new hostname (+ backend) on one site, optionally
mirroring it onto every other configured site too.

    npmpi add <SITE> <NODE-NAME> [-s] <OCTET> <PORT>
        Site-only: creates the hostname on <SITE>'s own NPM/Pi-hole(s).
        Nothing is touched on any other site.

    npmpi add multi <SITE> <NODE-NAME> [-s] <OCTET> <PORT>
        <SITE> is the ONE site this backend actually lives on (real NPM
        proxy host + Pi-hole DNS, created there exactly like the site-only
        form above). The hostname is then ALSO mirrored - DNS + proxy
        forwarding back across the SD-WAN mesh - onto every OTHER
        configured site, so it's reachable from all of them too. Use this
        instead of running the site-only form twice: doing that instead
        would create a SECOND, independent real backend on the other
        site's own network at the same OCTET, which is almost never what
        you want unless that site truly runs an identical backend of its
        own at that address.

-s / --https selects https as the backend scheme; omitted = http.

Idempotent: if the primary hostname already exists on a given NPM, that
step is reported and skipped rather than erroring (no separate "append"
command needed for the common case). Same idea if the OCTET/PORT you pass
already belongs to a different existing hostname's backend - the new name
gets appended onto that existing proxy host instead of creating a second
one pointed at the same backend, so changing the IP later only means
changing it in one place.
"""

from __future__ import annotations

import argparse

from npmpi.netops import create_or_skip_proxy_host, push_dns_to_site

MULTI_KEYWORD = "multi"


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "add",
        help="Create a new hostname on one site, optionally mirrored onto every other site",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "args", nargs="+", metavar="[multi] SITE NODE-NAME OCTET PORT",
        help="e.g. 'h test 99 8888' (site 'h' only) or "
             "'multi h test 99 8888' (real on site 'h', mirrored onto every other site)",
    )
    p.add_argument("-s", "--https", action="store_true", help="Use https to the backend (default: http)")
    p.set_defaults(func=cmd_add)


def _split_args(raw_args: list[str], site_keys: list[str]) -> tuple[bool, str, str, str, str]:
    if len(raw_args) == 5 and raw_args[0] == MULTI_KEYWORD:
        _, site, name, octet, port = raw_args
        if site not in site_keys:
            raise SystemExit(
                f"npmpi add multi: unknown site '{site}'. Configured sites: {site_keys}\n"
                f"Run `npmpi -e` for full syntax and examples."
            )
        return True, site, name, octet, port

    if len(raw_args) == 4 and raw_args[0] in site_keys:
        site, name, octet, port = raw_args
        return False, site, name, octet, port

    if len(raw_args) == 3:
        raise SystemExit(
            f"npmpi add: 'npmpi add NODE-NAME OCTET PORT' (no site) was removed - it used to silently "
            f"create a SEPARATE real backend on each site at the same octet, which is wrong unless both "
            f"sites truly run identical backends. Say which site the backend really lives on instead:\n"
            f"  npmpi add multi <SITE> {' '.join(raw_args)}   (real on <SITE>, mirrored onto every other site)\n"
            f"  npmpi add <SITE> {' '.join(raw_args)}         (site-only, no mirroring)\n"
            f"Configured sites: {site_keys}. Run `npmpi -e` for full syntax and examples."
        )

    raise SystemExit(
        f"npmpi add: expected 'SITE NODE-NAME OCTET PORT' or 'multi SITE NODE-NAME OCTET PORT' "
        f"(SITE one of {site_keys}), got: {' '.join(raw_args)}\n"
        f"Run `npmpi -e` for full syntax and examples."
    )


def _add_one_site(cfg, creds, site_key: str, name: str, scheme: str, octet: str, port: str) -> list[str]:
    site = cfg["sites"][site_key]
    hostname = f"{name}.{site['domain']}"
    backend_ip = f"{site['ip_prefix']}{octet}"

    print(f"\n=== {hostname} -> {scheme}://{backend_ip}:{port}  (site '{site_key}', local) ===")
    failures = []
    failures += push_dns_to_site(site, creds, site_key, [hostname], site["npm_target_ip"])
    ok, _ = create_or_skip_proxy_host(site, creds, site_key, [hostname], scheme, backend_ip, port, f"npm({site_key})")
    if not ok:
        failures.append(f"npm({site_key})")
    return failures


def _mirror_onto(cfg, creds, real_site_key: str, mirror_site_key: str, name: str,
                  scheme: str, real_backend_ip: str, port: str) -> list[str]:
    """Mirror real_site_key's real backend onto mirror_site_key (DNS + proxy forwarding across the SD-WAN mesh)."""
    real_site = cfg["sites"][real_site_key]
    mirror_site = cfg["sites"][mirror_site_key]
    hostname = f"{name}.{real_site['domain']}"

    print(f"\n=== mirroring {hostname} onto site '{mirror_site_key}' "
          f"(forwards back to {scheme}://{real_backend_ip}:{port}) ===")
    failures = []
    failures += push_dns_to_site(mirror_site, creds, mirror_site_key, [hostname], mirror_site["npm_target_ip"])
    label = f"npm({mirror_site_key},mirror)"
    ok, _ = create_or_skip_proxy_host(mirror_site, creds, mirror_site_key, [hostname], scheme, real_backend_ip, port, label)
    if not ok:
        failures.append(label)
    return failures


def cmd_add(cfg, creds, args) -> int:
    site_keys = list(cfg["sites"].keys())
    multi, site, name, octet, port = _split_args(args.args, site_keys)
    scheme = "https" if args.https else "http"

    failures: list[str] = []

    if not multi:
        failures += _add_one_site(cfg, creds, site, name, scheme, octet, port)
    else:
        other_sites = [k for k in site_keys if k != site]
        if not other_sites:
            print(f"Only one site is configured - nothing to mirror '{site}' onto. Add a second site via "
                  f"`npmpi setup`, or use `npmpi add {site} {name} {octet} {port}` instead.")
            return 1

        real_backend_ip = f"{cfg['sites'][site]['ip_prefix']}{octet}"
        failures += _add_one_site(cfg, creds, site, name, scheme, octet, port)
        for mirror_site in other_sites:
            failures += _mirror_onto(cfg, creds, site, mirror_site, name, scheme, real_backend_ip, port)

    print()
    if failures:
        print(f"Completed with failures in: {', '.join(failures)}")
        return 1
    print("All steps completed successfully.")
    return 0
