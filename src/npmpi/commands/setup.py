"""
npmpi setup - interactive first-run configuration, and targeted fixes for
one specific thing any time after that.

    npmpi setup                    full interactive wizard (first run, or a
                                    from-scratch re-run of everything)
    npmpi setup --fix              list everything that can be fixed
                                    individually, with its current value
    npmpi setup --paths            show where config.json / credentials.dat
                                    live on disk
    npmpi setup --npm [SITE]       re-run just one site's NPM config
                                    (prompts for SITE if omitted and you
                                    have more than one site)
    npmpi setup --pihole N [url]   re-run just Pi-hole #N's config - Pi-holes
                                    are numbered continuously across ALL
                                    sites (see `npmpi setup --fix` for the
                                    current numbering), not restarted per
                                    site. Add the literal word 'url' after N
                                    to fix only its URL and leave its name/
                                    password untouched.
    npmpi setup --gen              re-run just the dashboard (gen) config:
                                    which site, output path, page title

Full wizard: how many sites/networks (normally 2 - your two domain
letters), each site's domain/IP scheme/Pi-hole(s)/NPM, then collects and
encrypts all the passwords into one combined credential file (Windows
DPAPI - tied to this Windows user/machine, no master password ever
needed). Finishes by asking whether to set up `npmpi gen` now too.
"""

from __future__ import annotations

import argparse
import getpass

from npmpi.commands.gen import DEFAULT_TITLE as GEN_DEFAULT_TITLE, _resolve_output_path
from npmpi.config import DEFAULT_CONFIG_PATH, config_exists, load_config, write_config
from npmpi.creds import DEFAULT_CREDS_PATH, creds_exist, load_creds, save_creds
from npmpi.text import PLAIN_HELP


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "setup",
        help="Interactive setup / re-setup",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,  # cli.py intercepts `setup -h`/`--help` itself
    )
    p.add_argument("--fix", action="store_true",
                    help="List everything individually fixable, with its current value")
    p.add_argument("--paths", action="store_true",
                    help="Show where config.json and credentials.dat are stored")
    p.add_argument("--npm", nargs="?", const="_prompt_", default=None, metavar="SITE",
                    help="Re-run just one site's NPM config")
    p.add_argument("--pihole", nargs="+", default=None, metavar="N [url]",
                    help="Re-run just Pi-hole #N's config (optionally: only its url)")
    p.add_argument("--gen", action="store_true",
                    help="Re-run just the dashboard (gen) config: site/output path/title")
    p.set_defaults(func=cmd_setup, _skip_config_load=True)


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val or (default or "")


def _ask_url(prompt: str, default: str | None = None) -> str:
    """Like _ask, but rejects and re-prompts unless what's entered is a full
    http(s):// URL with an actual host after the scheme - requests (and
    therefore every NPM/Pi-hole call) fails with a fairly cryptic
    MissingSchema error on a bare IP/host with no scheme (or on a bare
    'http://' with nothing after it), so this catches the mistake right
    here instead of on the next `npmpi add`. URLs are always required, so
    empty input (no default given, Enter pressed anyway) is rejected too -
    it's never valid to save a blank NPM/Pi-hole URL."""
    while True:
        val = _ask(prompt, default)
        if val.startswith("http://") and len(val) > len("http://"):
            return val
        if val.startswith("https://") and len(val) > len("https://"):
            return val
        print("  You must specify a full URL with http:// or https:// and a host, e.g. http://10.0.1.1:81 - please retype it.")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive whole number.")


def _ask_password_keep(label: str) -> str | None:
    """getpass that returns None (meaning 'keep the existing one') on blank input."""
    pw = getpass.getpass(f"{label} (leave blank to keep the current password): ")
    return pw or None


def _setup_site(existing: dict | None = None, pihole_start: int = 1) -> tuple[str, dict, dict, int]:
    print()
    while True:
        key = _ask("Site key (used in `npmpi add <key> ...` - any name works, e.g. 'home', "
                    "'mobile', 'denver', not just a single letter)", (existing or {}).get("_key", ""))
        if key == "multi":
            print("  'multi' is reserved (it's the `npmpi add multi <SITE> ...` keyword) - pick a different site key.")
            continue
        break
    domain = _ask("Domain suffix for this site (e.g. home.example.com)", (existing or {}).get("domain"))
    ip_prefix = _ask("Backend IP prefix, including trailing dot (e.g. 10.0.1.)", (existing or {}).get("ip_prefix"))

    print(f"\n-- NPM for site '{key}' --")
    npm_url = _ask_url("NPM URL (e.g. http://10.0.1.1:81 - NPM's admin UI is commonly plain "
                        "http unless you've put SSL in front of it yourself)",
                        (existing or {}).get("npm", {}).get("url"))
    npm_email = _ask("NPM login email", (existing or {}).get("npm", {}).get("email", "") or "")
    npm_password = getpass.getpass("NPM password (stored encrypted, never shown again): ")
    npm_target_ip = _ask("IP this site's Pi-hole(s) should resolve new hostnames to", npm_url.split("//")[-1].split(":")[0])

    n_piholes = _ask_int(f"\nHow many Pi-holes does site '{key}' have", len((existing or {}).get("piholes", [])) or 1)
    piholes = []
    pihole_creds = {}
    for i in range(n_piholes):
        idx = pihole_start + i
        print(f"\n-- Pi-hole #{idx} for site '{key}' --")
        name = _ask(f"Name (used internally, e.g. pihole{idx})", f"pihole{idx}")
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
    return key, site_cfg, site_creds, pihole_start + n_piholes


def _flat_piholes(cfg: dict) -> list[tuple[str, int, dict]]:
    """Every Pi-hole across every site, numbered continuously in config file
    order (site h's then site m's, etc.) - positional, not name-based, so
    this stays well-defined even if a Pi-hole's 'name' field was hand-edited
    away from the default pihole<N> convention."""
    flat = []
    for site_key, site in cfg["sites"].items():
        for idx, ph in enumerate(site["piholes"]):
            flat.append((site_key, idx, ph))
    return flat


def _require_existing_config() -> dict | None:
    if not config_exists():
        print(f"No config found at {DEFAULT_CONFIG_PATH} yet.\nRun `npmpi setup` (no flags) first to create one.")
        return None
    return load_config()


def _require_existing_creds() -> dict | None:
    if not creds_exist():
        print(f"No credential file found at {DEFAULT_CREDS_PATH} yet.\nRun `npmpi setup` (no flags) first to create one.")
        return None
    return load_creds()


def cmd_show_paths(args) -> int:
    cfg_note = "" if config_exists() else "  (not created yet)"
    creds_note = "" if creds_exist() else "  (not created yet)"
    print(f"Config:      {DEFAULT_CONFIG_PATH}{cfg_note}")
    print(f"Credentials: {DEFAULT_CREDS_PATH}{creds_note}")
    return 0


def cmd_fix_menu(args) -> int:
    cfg = _require_existing_config()
    if cfg is None:
        return 1

    print("Things you can fix individually:\n")
    print("  npmpi setup --paths".ljust(32) + "Show config/credential file locations")
    for site_key, site in cfg["sites"].items():
        print(f"  npmpi setup --npm {site_key}".ljust(32) + f"(site '{site_key}' NPM) currently: {site['npm']['url']}")
    for n, (site_key, idx, ph) in enumerate(_flat_piholes(cfg), start=1):
        print(f"  npmpi setup --pihole {n}".ljust(32) + f"(site '{site_key}', \"{ph['name']}\") currently: {ph['url']}")
        print(f"  npmpi setup --pihole {n} url".ljust(32) + "-> fix just its URL")
    gen = cfg.get("gen", {})
    if gen.get("enabled"):
        print("  npmpi setup --gen".ljust(32) + f"(dashboard, site '{gen.get('site')}') currently: {gen.get('output')}")
    print()
    print("  npmpi setup".ljust(32) + "Full re-run of everything")
    return 0


def _resolve_site(cfg: dict, requested: str | None) -> str | None:
    site_keys = list(cfg["sites"].keys())
    if requested and requested != "_prompt_":
        if requested not in site_keys:
            print(f"Unknown site '{requested}'. Configured sites: {site_keys}")
            return None
        return requested
    if len(site_keys) == 1:
        return site_keys[0]
    site = _ask(f"Which site? ({'/'.join(site_keys)})")
    while site not in site_keys:
        site = _ask(f"Please enter one of {site_keys}")
    return site


def cmd_fix_npm(args) -> int:
    cfg = _require_existing_config()
    creds = _require_existing_creds()
    if cfg is None or creds is None:
        return 1

    site_key = _resolve_site(cfg, args.npm)
    if site_key is None:
        return 1

    site = cfg["sites"][site_key]
    print(f"\n-- NPM for site '{site_key}' (currently: {site['npm']['url']}) --")
    npm_url = _ask_url("NPM URL (e.g. http://10.0.1.1:81)", site["npm"]["url"])
    npm_email = _ask("NPM login email", site["npm"]["email"])
    new_pw = _ask_password_keep("NPM password")

    site["npm"]["url"] = npm_url
    site["npm"]["email"] = npm_email
    if new_pw is not None:
        creds.setdefault(site_key, {})["npm_password"] = new_pw

    write_config(cfg)
    save_creds(creds)
    print(f"\nUpdated site '{site_key}' NPM config -> {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_fix_pihole(args) -> int:
    cfg = _require_existing_config()
    creds = _require_existing_creds()
    if cfg is None or creds is None:
        return 1

    raw = args.pihole
    try:
        n = int(raw[0])
    except ValueError:
        print("Usage: npmpi setup --pihole N [url]   (N is the number shown by `npmpi setup --fix`)")
        return 1
    field = raw[1].lower() if len(raw) > 1 else None
    if field not in (None, "url"):
        print(f"Unknown field '{field}'. Only 'url' can be targeted individually - omit it to fix the whole entry.")
        return 1

    flat = _flat_piholes(cfg)
    if not (1 <= n <= len(flat)):
        print(f"No Pi-hole #{n}. You have {len(flat)} configured - run `npmpi setup --fix` to see current numbering.")
        return 1

    site_key, idx, ph = flat[n - 1]
    print(f"\n-- Pi-hole #{n} on site '{site_key}' (currently: \"{ph['name']}\" @ {ph['url']}) --")

    if field == "url":
        new_url = _ask_url("URL (e.g. https://10.0.1.2:8489)", ph["url"])
        cfg["sites"][site_key]["piholes"][idx]["url"] = new_url
    else:
        new_name = _ask("Name (used internally)", ph["name"])
        new_url = _ask_url("URL (e.g. https://10.0.1.2:8489)", ph["url"])
        new_pw = _ask_password_keep(f"Password for {new_name}")

        pihole_creds = creds.setdefault(site_key, {}).setdefault("piholes", {})
        if new_name != ph["name"]:
            old_pw = pihole_creds.pop(ph["name"], None)
            if new_pw is None:
                new_pw = old_pw
        if new_pw is not None:
            pihole_creds[new_name] = new_pw

        cfg["sites"][site_key]["piholes"][idx] = {"name": new_name, "url": new_url}

    write_config(cfg)
    save_creds(creds)
    print(f"\nUpdated Pi-hole #{n} -> {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_fix_gen(args) -> int:
    cfg = _require_existing_config()
    if cfg is None:
        return 1

    existing = cfg.get("gen", {})
    site_keys = list(cfg["sites"].keys())
    print(f"\n-- Dashboard (gen) config (currently: {'enabled, site ' + repr(existing.get('site')) if existing.get('enabled') else 'not enabled'}) --")

    default_site = existing.get("site") if existing.get("site") in site_keys else (site_keys[0] if site_keys else None)
    site = site_keys[0] if len(site_keys) == 1 else _ask(f"Which site's NPM should the dashboard list? ({'/'.join(site_keys)})", default_site)
    while site not in site_keys:
        site = _ask(f"Please enter one of {site_keys}")

    raw_output = _ask("Path to write index.html to (must include the filename, "
                       "e.g. \\\\server\\share\\home-services\\index.html)", existing.get("output"))
    output = _resolve_output_path(raw_output)
    if output != raw_output:
        print(f"  (no filename given - will write to '{output}' instead)")
    title = _ask("Page title", existing.get("title", GEN_DEFAULT_TITLE))

    cfg["gen"] = {"enabled": True, "site": site, "output": output, "title": title}
    write_config(cfg)
    print(f"\nUpdated dashboard (gen) config -> {DEFAULT_CONFIG_PATH}")
    return 0


def cmd_setup(cfg, creds, args) -> int:
    if args is not None:
        if getattr(args, "paths", False):
            return cmd_show_paths(args)
        if getattr(args, "fix", False):
            return cmd_fix_menu(args)
        if getattr(args, "npm", None) is not None:
            return cmd_fix_npm(args)
        if getattr(args, "pihole", None) is not None:
            return cmd_fix_pihole(args)
        if getattr(args, "gen", False):
            return cmd_fix_gen(args)

    print(PLAIN_HELP)
    print("=== npmpi setup ===")
    if config_exists():
        print(f"(Existing config found at {DEFAULT_CONFIG_PATH} - values below default to what's already there.)")
    print()

    n_sites = _ask_int("How many sites/networks do you want to configure (normally 2)", 2)

    sites = {}
    all_creds = {}
    pihole_counter = 1
    for i in range(1, n_sites + 1):
        print(f"\n### Site {i} of {n_sites} ###")
        key, site_cfg, site_creds, pihole_counter = _setup_site(pihole_start=pihole_counter)
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
