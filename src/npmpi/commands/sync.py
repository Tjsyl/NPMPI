"""
npmpi sync - backfill cross-site mirroring in both directions.

    npmpi sync                  check both sites, mirror what's missing
    npmpi sync --dry-run        preview only, no changes made
    npmpi sync --only test r    only consider hostnames starting with these prefixes

Replaces the old synchome2m.py/syncm2home.py pair with one command that
does both directions. For each site, reads its NPM's proxy hosts filtered
to that site's own domain, and mirrors anything not yet present on the
OTHER site's NPM (+ that site's pihole(s)) - exactly what `npmpi add`
(no site letter) does at creation time, just retroactively and in bulk.

This is the command to run after the TUE7 hardcase gets plugged back in,
to catch up anything added locally-only (via `npmpi add h`/`npmpi add m`)
while it was offline.
"""

from __future__ import annotations

import argparse

from npmpi import npm as npm_api
from npmpi.creds import get_npm_password
from npmpi.netops import push_dns_to_site


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "sync",
        help="Backfill cross-site mirroring in both directions",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--dry-run", action="store_true", help="Show what would be mirrored, make no changes")
    p.add_argument("--only", nargs="+", default=None, metavar="PREFIX",
                    help="Only sync hostnames with these prefixes, e.g. --only test r")
    p.add_argument("--repair-pihole", action="store_true",
                    help="Also re-push DNS records for hosts already mirrored, in case a pihole's "
                         "local records were lost independently of NPM (e.g. after a pihole rebuild)")
    p.set_defaults(func=cmd_sync)


def _sync_direction(cfg, creds, src_key: str, dst_key: str, only_prefixes, dry_run: bool, repair_pihole: bool) -> list[str]:
    src = cfg["sites"][src_key]
    dst = cfg["sites"][dst_key]
    suffix = src["domain"]

    print(f"\n--- {src_key} -> {dst_key} ({suffix}) ---")

    src_pw = get_npm_password(creds, src_key)
    src_token = npm_api.login(src["npm"]["url"], src["npm"]["email"], src_pw)
    src_hosts = npm_api.get_proxy_hosts(src["npm"]["url"], src_token)

    dst_pw = get_npm_password(creds, dst_key)
    dst_token = npm_api.login(dst["npm"]["url"], dst["npm"]["email"], dst_pw)
    dst_hosts = npm_api.get_proxy_hosts(dst["npm"]["url"], dst_token)
    dst_all_domains = set()
    for h in dst_hosts:
        dst_all_domains.update(h.get("domain_names", []))

    only_names = None
    if only_prefixes:
        only_names = {f"{p}.{suffix}" for p in only_prefixes}

    to_mirror, already = [], []
    for h in src_hosts:
        domains = npm_api.domains_for_suffix(h, suffix)
        if not domains:
            continue
        if only_names is not None and not (set(domains) & only_names):
            continue
        if any(d in dst_all_domains for d in domains):
            already.append((domains, h["forward_host"]))
            continue
        to_mirror.append((domains, h["forward_scheme"], h["forward_host"], h["forward_port"]))

    print(f"Found {len(src_hosts)} proxy host(s) on {src_key} NPM total for {suffix}.")
    print(f"Already mirrored on {dst_key}: {len(already)}")
    print(f"To mirror: {len(to_mirror)}")
    for domains, scheme, fhost, fport in to_mirror:
        tag = "dry-run" if dry_run else "pending"
        if domains == [suffix]:
            print(f"  [{tag}] {suffix} -> direct DNS pointer to {fhost} (source NPM's own admin UI, no proxy mirror)")
        else:
            print(f"  [{tag}] {', '.join(domains)} -> {scheme}://{fhost}:{fport}")

    if dry_run:
        if repair_pihole and already:
            print(f"[dry-run] --repair-pihole would also re-push DNS for the {len(already)} already-mirrored host(s) above.")
        return []

    if not to_mirror and not (repair_pihole and already):
        print("Nothing to do.")
        return []

    failures = []
    for domains, scheme, fhost, fport in to_mirror:
        if domains == [suffix]:
            # Bare apex = source NPM's own admin UI, not a real backend - point
            # dst pihole(s) straight at the real IP, no proxy mirror created.
            print(f"[apex] {suffix} is {src_key}'s own NPM admin UI - direct DNS pointer only.")
            failures += push_dns_to_site(dst, creds, dst_key, [suffix], fhost)
            continue
        try:
            certs = npm_api.get_certificates(dst["npm"]["url"], dst_token)
            cert_id = npm_api.find_cert(domains[0], certs)
            npm_api.create_proxy_host(dst["npm"]["url"], dst_token, domains, scheme, fhost, fport, cert_id)
            cert_note = "matched cert" if cert_id else "no cert matched"
            print(f"[{dst_key} NPM] mirrored: {', '.join(domains)} -> {scheme}://{fhost}:{fport} ({cert_note})")
        except Exception as e:
            print(f"[{dst_key} NPM] FAILED to mirror {', '.join(domains)}: {e}")
            failures.append(", ".join(domains))
            continue
        failures += push_dns_to_site(dst, creds, dst_key, domains, dst["npm_target_ip"])

    if repair_pihole and already:
        print(f"[repair] re-checking DNS on {dst_key} for {len(already)} already-mirrored host(s)...")
        for domains, fhost in already:
            target = fhost if domains == [suffix] else dst["npm_target_ip"]
            failures += push_dns_to_site(dst, creds, dst_key, domains, target)

    return failures


def cmd_sync(cfg, creds, args) -> int:
    site_keys = list(cfg["sites"].keys())
    if len(site_keys) < 2:
        print("Only one site is configured - nothing to sync.")
        return 1
    s1, s2 = site_keys[0], site_keys[1]

    failures = []
    failures += _sync_direction(cfg, creds, s1, s2, args.only, args.dry_run, args.repair_pihole)
    failures += _sync_direction(cfg, creds, s2, s1, args.only, args.dry_run, args.repair_pihole)

    print()
    if args.dry_run:
        print("Dry run - no changes made.")
        return 0
    if failures:
        print(f"Completed with failures in: {', '.join(failures)}")
        return 1
    print("All mirrored hosts synced successfully.")
    return 0
