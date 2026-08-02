"""
npmpi add - create a new hostname (+ backend) on one or both sites.

    npmpi add h <name> [-s] <octet> <port>   site "h" only, local, no mirror
    npmpi add m <name> [-s] <octet> <port>   site "m" only, local, no mirror
    npmpi add <name> [-s] <octet> <port>     BOTH sites, real backend on each,
                                              PLUS cross-site mirror of each

-s / --https selects https as the backend scheme; omitted = http.

Idempotent: if the primary hostname already exists on a given NPM, that
step is reported and skipped rather than erroring (no separate "append"
command needed for the common case).
"""

from __future__ import annotations

import argparse
import sys

from npmpi.netops import create_or_skip_proxy_host, push_dns_to_site


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "add",
        help="Create a new hostname on one or both sites",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("args", nargs="+", metavar="[SITE] NAME OCTET PORT",
                    help="e.g. 'h test 99 8888' or 'test 99 8888' (both sites)")
    p.add_argument("-s", "--https", action="store_true", help="Use https to the backend (default: http)")
    p.set_defaults(func=cmd_add)


def _split_args(raw_args: list[str], site_keys: list[str]) -> tuple[str | None, str, str, str]:
    if len(raw_args) == 4 and raw_args[0] in site_keys:
        site, name, octet, port = raw_args
        return site, name, octet, port
    if len(raw_args) == 3:
        name, octet, port = raw_args
        return None, name, octet, port
    raise SystemExit(
        f"npmpi add: expected '[SITE] NAME OCTET PORT' (SITE one of {site_keys}), "
        f"got: {' '.join(raw_args)}\nRun `npmpi -e` for full syntax and examples."
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
    site, name, octet, port = _split_args(args.args, site_keys)
    scheme = "https" if args.https else "http"

    failures: list[str] = []

    if site is not None:
        failures += _add_one_site(cfg, creds, site, name, scheme, octet, port)
    else:
        if len(site_keys) < 2:
            print("Only one site is configured - nothing to mirror. Add a second site via `npmpi setup`, "
                  "or specify a site letter explicitly.")
            return 1
        s1, s2 = site_keys[0], site_keys[1]
        backend1 = f"{cfg['sites'][s1]['ip_prefix']}{octet}"
        backend2 = f"{cfg['sites'][s2]['ip_prefix']}{octet}"

        failures += _add_one_site(cfg, creds, s1, name, scheme, octet, port)
        failures += _add_one_site(cfg, creds, s2, name, scheme, octet, port)
        failures += _mirror_onto(cfg, creds, s1, s2, name, scheme, backend1, port)
        failures += _mirror_onto(cfg, creds, s2, s1, name, scheme, backend2, port)

    print()
    if failures:
        print(f"Completed with failures in: {', '.join(failures)}")
        return 1
    print("All steps completed successfully.")
    return 0
