"""
npmpi setup - interactive first-run configuration (and re-run any time,
e.g. after a password change or an IP scheme change).

    npmpi setup

Walks through: how many sites/networks (normally 2 - your two domain
letters), each site's domain/IP scheme/Pi-hole(s)/NPM, then collects and
encrypts all the passwords into one combined credential file (Windows
DPAPI - tied to this Windows user/machine, no master password ever
needed). Finishes by asking whether to set up `npmpi gen` now too.
"""

from __future__ import annotations

import argparse
import getpass

from npmpi.config import DEFAULT_CONFIG_PATH, config_exists, write_config
from npmpi.creds import DEFAULT_CREDS_PATH, save_creds
from npmpi.text import PLAIN_HELP


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "setup",
        help="Interactive setup / re-setup",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.set_defaults(func=cmd_setup, _skip_config_load=True)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or (default or "")


def _ask_url(prompt: str, default: str | None = None) -> str:
    """Like _ask, but rejects and re-prompts if what's entered has no
    http(s):// scheme - requests (and therefore every NPM/Pi-hole call)
    fails with a fairly cryptic MissingSchema error on a bare IP/host with
    no scheme, so this catches the mistake right here instead of on the
    next `npmpi add`."""
    while True:
        val = _ask(prompt, default)
        if not val or val.startswith("http://") or val.startswith("https://"):
            return val
        print("  You must specify http:// or https:// - please retype the full URL.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive whole number.")


def _setup_site(existing: dict | None = None) -> tuple[str, dict, dict]:
    print()
    key = _ask("Site letter/key (used in `npmpi add <key> ...`)", (existing or {}).get("_key", ""))
    domain = _ask("Domain suffix for this site (e.g. home.example.com)", (existing or {}).get("domain"))
    ip_prefix = _ask("Backend IP prefix, including trailing dot (e.g. 10.0.1.)", (existing or {}).get("ip_prefix"))

    print(f"\n-- NPM for site '{key}' --")
    npm_url = _ask_url("NPM URL", (existing or {}).get("npm", {}).get("url", "http://"))
    npm_email = _ask("NPM login email", (existing or {}).get("npm", {}).get("email", "") or "")
    npm_password = getpass.getpass("NPM password (stored encrypted, never shown again): ")
    npm_target_ip = _ask("IP this site's Pi-hole(s) should resolve new hostnames to", npm_url.split("//")[-1].split(":")[0])

    n_piholes = _ask_int(f"\nHow many Pi-holes does site '{key}' have", len((existing or {}).get("piholes", [])) or 1)
    piholes = []
    pihole_creds = {}
    for i in range(1, n_piholes + 1):
        print(f"\n-- Pi-hole #{i} for site '{key}' --")
        name = _ask("Name (used internally, e.g. pihole1)", f"pihole{i}")
        url = _ask_url("URL (e.g. https://10.0.1.2:8489)")
        pw = getpass.getpass(f"Password for {name} (stored encrypted, never shown again): ")
        piholes.append({"name": name, "url": url})
        pihole_creds[name] = pw

    site_cfg = {
        "domain": domain,
        "ip_prefix": ip_prefix,
        "npm": {"url": npm_url, "email": npm_email},
        "npm_target_ip": npm_target_ip,
        "piholes": piholes,
    }
    site_creds = {"npm_password": npm_password, "piholes": pihole_creds}
    return key, site_cfg, site_creds


def cmd_setup(cfg, creds, args) -> int:
    print(PLAIN_HELP)
    print("=== npmpi setup ===")
    if config_exists():
        print(f"(Existing config found at {DEFAULT_CONFIG_PATH} - values below default to what's already there.)")
    print()

    n_sites = _ask_int("How many sites/networks do you want to configure (normally 2)", 2)

    sites = {}
    all_creds = {}
    for i in range(1, n_sites + 1):
        print(f"\n### Site {i} of {n_sites} ###")
        key, site_cfg, site_creds = _setup_site()
        sites[key] = site_cfg
        all_creds[key] = site_creds

    new_cfg = {"sites": sites, "gen": {"enabled": False}}

    print("\n=== Dashboard (gen) ===")
    want_gen = input("Do you want to set up generating a web page with links to your nodes? (Y/N): ").strip().lower()
    if want_gen in ("y", "yes"):
        site_keys = list(sites.keys())
        gen_site = site_keys[0] if len(site_keys) == 1 else _ask(f"Which site's NPM should the dashboard list? ({'/'.join(site_keys)})", site_keys[0])
        gen_output = _ask("Path to write index.html to")
        gen_title = _ask("Page title", "Home Services")
        new_cfg["gen"] = {"enabled": True, "site": gen_site, "output": gen_output, "title": gen_title}
    else:
        print("Skipping - run `npmpi gen` any time later and it'll walk you through this then.")

    write_config(new_cfg)
    save_creds(all_creds)

    print(f"\nSaved config -> {DEFAULT_CONFIG_PATH}")
    print(f"Saved encrypted credentials -> {DEFAULT_CREDS_PATH}")
    print("\nSetup complete. Try `npmpi` with no arguments to see what's available.")
    return 0
