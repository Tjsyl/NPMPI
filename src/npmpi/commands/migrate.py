"""
npmpi migrate - move an NPM instance's proxy hosts to a new instance
(e.g. rebuilding a broken LXC/container), with backups along the way.

    npmpi migrate            walks you through it interactively
    npmpi migrate h          migrate starting from site "h"'s NPM

Rolled in from the old npm_migrate.py export/import pair, now as one
guided flow: explains what it's about to do, asks where to save a backup
of the source NPM's proxy hosts before touching anything, offers to also
back up that site's Pi-hole local DNS records (separate from the NPM
backup - the two are independent systems and NPM's own export doesn't
cover pihole state), then previews and confirms before creating anything
on the destination.
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
from pathlib import Path

from npmpi import npm as npm_api
from npmpi import pihole as pihole_api
from npmpi.creds import get_npm_password, get_pihole_password

FIELDS_TO_STRIP = {"id", "created_on", "modified_on", "owner_user_id", "certificate", "owner", "access_list"}


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "migrate",
        help="Move an NPM instance's proxy hosts to a new instance, with backups",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("site", nargs="?", default=None, help="Site key to migrate from, e.g. h or m (asked interactively if omitted)")
    p.set_defaults(func=cmd_migrate)


def _pick_site(cfg, site_arg) -> str:
    site_keys = list(cfg["sites"].keys())
    if site_arg:
        if site_arg not in site_keys:
            raise SystemExit(f"Unknown site '{site_arg}'. Configured sites: {site_keys}")
        return site_arg
    if len(site_keys) == 1:
        return site_keys[0]
    site = input(f"Which site's NPM are you migrating? ({'/'.join(site_keys)}): ").strip()
    while site not in site_keys:
        site = input(f"Please enter one of {site_keys}: ").strip()
    return site


def _confirm(prompt: str) -> bool:
    return input(f"{prompt} (y/N): ").strip().lower() in ("y", "yes")


def cmd_migrate(cfg, creds, args) -> int:
    site_key = _pick_site(cfg, args.site)
    site = cfg["sites"][site_key]

    print(f"""
--- npmpi migrate: site '{site_key}' ({site['domain']}) ---

Here's what this is going to do:
  1. Log into the CURRENT NPM at {site['npm']['url']} and export every proxy
     host + certificate list to a local JSON backup file (nothing is
     changed on the source yet).
  2. Optionally also back up this site's Pi-hole local DNS records
     ({len(site['piholes'])} pihole(s) configured) to a separate JSON file -
     NPM's own export doesn't include DNS, and the two systems can drift
     independently, so this is a separate step.
  3. Ask for the NEW NPM's URL (e.g. a freshly rebuilt instance) and preview
     what would be recreated there before actually creating anything.

Nothing is written to the destination until you confirm the preview.
""")
    if not _confirm("Continue?"):
        print("Cancelled.")
        return 1

    default_backup = f"npmpi_migrate_{site_key}_{datetime.date.today().isoformat()}.json"
    backup_path = input(f"Path to save the NPM backup [{default_backup}]: ").strip() or default_backup

    pw = get_npm_password(creds, site_key)
    print(f"\n[npm] logging in to {site['npm']['url']} ...")
    token = npm_api.login(site["npm"]["url"], site["npm"]["email"], pw)
    hosts = npm_api.get_proxy_hosts(site["npm"]["url"], token)
    certs = npm_api.get_certificates(site["npm"]["url"], token)

    out = {"source_url": site["npm"]["url"], "proxy_hosts": hosts, "certificates": certs}
    Path(backup_path).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[npm] exported {len(hosts)} proxy hosts and {len(certs)} certificates -> {backup_path}")

    if _confirm("Also back up this site's Pi-hole(s)?"):
        print("""
  Two options:
    1. DNS records only  - lightweight JSON export of just the custom
                            local DNS records (what npmpi itself manages).
    2. Full Teleporter backup - Pi-hole's own complete config archive
                            (DNS records, blocklists, groups, settings -
                            everything), one .zip per pihole. Larger, but
                            a true full restore point.
""")
        choice = input("Which kind of backup? (1/2) [1]: ").strip() or "1"

        if choice == "2":
            for ph in site["piholes"]:
                name = ph["name"]
                default_zip = f"npmpi_migrate_{site_key}_{name}_teleporter_{datetime.date.today().isoformat()}.zip"
                zip_path = input(f"Path to save {name}'s Teleporter backup [{default_zip}]: ").strip() or default_zip
                try:
                    phpw = get_pihole_password(creds, site_key, name)
                    print(f"[{name}] logging in to {ph['url']} ...")
                    sid = pihole_api.login(ph["url"], phpw)
                    try:
                        archive = pihole_api.teleporter_export(ph["url"], sid)
                        Path(zip_path).write_bytes(archive)
                        print(f"[{name}] wrote Teleporter backup ({len(archive)} bytes) -> {zip_path}")
                    finally:
                        pihole_api.logout(ph["url"], sid)
                except Exception as e:
                    print(f"[{name}] FAILED to back up: {e}")
        else:
            default_dns_backup = f"npmpi_migrate_{site_key}_pihole_dns_{datetime.date.today().isoformat()}.json"
            dns_backup_path = input(f"Path to save the Pi-hole DNS backup [{default_dns_backup}]: ").strip() or default_dns_backup
            dns_out = {}
            for ph in site["piholes"]:
                name = ph["name"]
                try:
                    phpw = get_pihole_password(creds, site_key, name)
                    print(f"[{name}] logging in to {ph['url']} ...")
                    sid = pihole_api.login(ph["url"], phpw)
                    try:
                        dns_out[name] = {"url": ph["url"], "hosts": pihole_api.get_hosts(ph["url"], sid)}
                        print(f"[{name}] backed up {len(dns_out[name]['hosts'])} DNS record(s)")
                    finally:
                        pihole_api.logout(ph["url"], sid)
                except Exception as e:
                    print(f"[{name}] FAILED to back up: {e}")
            Path(dns_backup_path).write_text(json.dumps(dns_out, indent=2), encoding="utf-8")
            print(f"Wrote Pi-hole DNS backup -> {dns_backup_path}")
        print(f"Wrote Pi-hole DNS backup -> {dns_backup_path}")

    print()
    dest_url = input(f"New NPM URL to migrate hosts onto (e.g. {site['npm']['url']}): ").strip()
    if not dest_url:
        print("No destination given - stopping after backup. Your backup file is safe to use later:")
        print(f"  {backup_path}")
        return 0
    dest_email = input(f"Email for the new NPM [{site['npm']['email']}]: ").strip() or site["npm"]["email"]
    dest_pw = getpass.getpass("Password for the new NPM: ")

    exclude_raw = input("Any domain(s) to exclude, space-separated (blank for none): ").strip()
    exclude = set(exclude_raw.split()) if exclude_raw else set()

    to_import = [h for h in hosts if not (exclude & set(h["domain_names"]))]

    dest_token = npm_api.login(dest_url, dest_email, dest_pw)
    dest_certs = npm_api.get_certificates(dest_url, dest_token)

    def match_cert(domain_names: list[str]) -> int:
        for cert in dest_certs:
            for cd in cert.get("domain_names", []):
                for d in domain_names:
                    if cd == d or (cd.startswith("*.") and d.endswith(cd[1:])):
                        return cert["id"]
        return 0

    print(f"\nPreview - would create {len(to_import)} proxy host(s) on {dest_url}:")
    for h in to_import:
        clean = {k: v for k, v in h.items() if k not in FIELDS_TO_STRIP}
        cert_id = match_cert(h["domain_names"])
        cert_note = "with matched SSL cert" if cert_id else "NO SSL cert matched"
        target = f"{clean['forward_scheme']}://{clean['forward_host']}:{clean['forward_port']}"
        print(f"  {', '.join(h['domain_names'])} -> {target} ({cert_note})")

    if not _confirm(f"Create these {len(to_import)} proxy host(s) on {dest_url} now?"):
        print("Not applied. Your backup and this preview can be reused any time.")
        return 0

    created, failed = [], []
    for h in to_import:
        clean = {k: v for k, v in h.items() if k not in FIELDS_TO_STRIP}
        clean["certificate_id"] = match_cert(h["domain_names"])
        try:
            npm_api.create_proxy_host(
                dest_url, dest_token, clean["domain_names"], clean["forward_scheme"],
                clean["forward_host"], clean["forward_port"], clean["certificate_id"],
            )
            created.append(", ".join(h["domain_names"]))
            print(f"  created: {', '.join(h['domain_names'])}")
        except Exception as e:
            failed.append((", ".join(h["domain_names"]), str(e)))
            print(f"  FAILED: {', '.join(h['domain_names'])} :: {e}")

    print(f"\nDone. {len(created)} created, {len(failed)} failed.")
    return 1 if failed else 0
