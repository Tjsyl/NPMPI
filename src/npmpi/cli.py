"""
npmpi CLI entry point: dispatch, bare-command plain-text help, and
`-e`/`--examples` extended help.
"""

from __future__ import annotations

import sys

from npmpi.commands import add, gen, migrate, setup, sync
from npmpi.config import DEFAULT_CONFIG_PATH, config_exists, load_config
from npmpi.creds import DEFAULT_CREDS_PATH, creds_exist, load_creds
from npmpi.text import PLAIN_HELP

COMMANDS = [add, sync, gen, migrate, setup]


def _help_sections() -> list[tuple]:
    return [
        (
            "add",
            "npmpi add [SITE] NODE-NAME [-s|--https] OCTET PORT",
            "Create a new hostname (+ backend). Safe to re-run - an already-existing "
            "hostname is reported and skipped, not an error.",
            [
                ("SITE", "Optional. One of your configured site letters (e.g. h/m) - creates "
                          "the hostname on that site only, no cross-site mirroring. Omit it "
                          "entirely to create a real backend on BOTH sites at once, PLUS "
                          "cross-mirror each onto the other site's Pi-hole(s)/NPM."),
                ("NODE-NAME", "The hostname prefix, e.g. 'test' -> test.example.com."),
                ("-s / --https", "Use https to the backend. Omit this flag for http (the default)."),
                ("OCTET", "Last octet of the backend IP - combined with the site's configured "
                           "IP prefix, e.g. prefix 10.0.1. + octet 99 -> 10.0.1.99."),
                ("PORT", "Backend port, e.g. 8888."),
            ],
            [
                "npmpi add m test 99 8888",
                "  -> test.m.example.com, http, backend 10.0.2.99:8888, site 'm' only.",
                "npmpi add h test -s 99 8888",
                "  -> test.home.example.com, https, backend 10.0.1.99:8888, site 'h' only.",
                "npmpi add test -s 99 8888",
                "  -> test.home.example.com AND test.m.example.com, https, backend ...99:8888",
                "     on EACH site's own network, plus each cross-mirrored onto the other site.",
            ],
        ),
        (
            "sync",
            "npmpi sync [--dry-run] [--only PREFIX ...] [--repair-pihole]",
            "Check both sites and mirror anything that only exists on one side "
            "(e.g. added earlier with `npmpi add h`/`npmpi add m` while the other "
            "site was offline). --dry-run previews with no changes. --repair-pihole "
            "also re-pushes DNS for hosts that look already-mirrored, for when a "
            "pihole's local records were lost independently of NPM.",
            [],
            [
                "npmpi sync",
                "  -> mirrors anything missing in both directions.",
                "npmpi sync --dry-run --only test",
                "  -> previews only, restricted to hostnames starting with 'test'.",
            ],
        ),
        (
            "gen",
            "npmpi gen [--output PATH] [--title TEXT]",
            "Creates an index.html listing all your NPM nodes - one clickable card per "
            "enabled proxy host on a site's NPM, alphabetically sorted, with a "
            "client-side search box. Regenerate it any time a host's added/removed/"
            "renamed. If never configured, walks you through picking a site/output "
            "path/title first and saves that choice to config.json.",
            [],
            [
                "npmpi gen",
                "  -> regenerates using the configured site/output/title.",
                "npmpi gen --title \"My Services\"",
                "  -> one-off title override, doesn't change the saved config.",
            ],
        ),
        (
            "migrate",
            "npmpi migrate [SITE]",
            "Interactively move a site's NPM proxy hosts to a new NPM instance. "
            "Explains what it's about to do, backs up the source NPM's proxy hosts "
            "to a JSON file you choose the path for, then previews the import before "
            "creating anything on the destination.",
            [
                ("Pi-hole backup (asked interactively, not a flag)",
                 "After the NPM backup, you're offered a backup of that site's Pi-hole(s) "
                 "too, your choice of two kinds:\n"
                 "            1. DNS records only - lightweight JSON export of just the "
                 "custom local DNS records (what npmpi itself manages).\n"
                 "            2. Full Teleporter backup - Pi-hole's own complete config "
                 "archive (DNS records, blocklists, groups, settings - everything), one "
                 ".zip per configured Pi-hole, via the same endpoint the Pi-hole web UI's "
                 "own Export button uses."),
            ],
            [
                "npmpi migrate",
                "  -> asks which configured site to migrate, then walks through the rest,",
                "     including which kind of Pi-hole backup you want along the way.",
                "npmpi migrate h",
                "  -> starts directly from site 'h', skipping the site-picker prompt.",
            ],
        ),
        (
            "setup",
            "npmpi setup",
            "Interactive setup wizard: how many sites, each site's domain/IP scheme/"
            "Pi-hole(s)/NPM, then collects and encrypts credentials into one combined "
            "file. Re-run any time - e.g. after a password change or an IP change. Made "
            "a typo in one field? You don't have to redo the whole thing - see the "
            "targeted-fix options below.",
            [
                ("--fix", "List everything individually fixable, with its current value, "
                           "so you know exactly which flag below to run."),
                ("--paths", "Show where config.json and credentials.dat live on disk, then exit."),
                ("--npm [SITE]", "Re-run just one site's NPM config (url/email/password). "
                                  "If you have more than one site and omit SITE, you're "
                                  "prompted which one."),
                ("--pihole N [url]", "Re-run just Pi-hole #N's config. Pi-holes are numbered "
                                      "continuously across ALL sites in the order they're "
                                      "configured (not restarted per site) - e.g. site h's two "
                                      "Pi-holes are #1/#2 and site m's first is #3; run `npmpi "
                                      "setup --fix` to see the current numbering. Add the "
                                      "literal word 'url' after N to fix only its URL and leave "
                                      "the name/password untouched."),
            ],
            [
                "npmpi setup",
                "  -> runs (or re-runs) the full interactive wizard.",
                "npmpi setup --fix",
                "  -> lists every site's NPM and every numbered Pi-hole with its current value.",
                "npmpi setup --npm h",
                "  -> re-asks just site h's NPM url/email/password.",
                "npmpi setup --pihole 2 url",
                "  -> re-asks just Pi-hole #2's URL, nothing else.",
            ],
        ),
    ]


def _render_section(section: tuple) -> list[str]:
    name, syntax, desc, options, examples = section
    lines = [f"--- {name} ---", f"  {syntax}\n", f"  {desc}\n"]
    if options:
        lines.append("  Options:")
        for opt_name, opt_desc in options:
            lines.append(f"    {opt_name}")
            lines.append(f"        {opt_desc}")
        lines.append("")
    lines.append("  Examples:")
    for ex in examples:
        lines.append(f"    {ex}")
    lines.append("")
    return lines


def _extended_help() -> str:
    lines = ["npmpi - full command reference\n"]
    for section in _help_sections():
        lines.extend(_render_section(section))
    return "\n".join(lines)


def _setup_help_section() -> str:
    setup_section = next(s for s in _help_sections() if s[0] == "setup")
    lines = ["npmpi setup - full syntax and examples\n"]
    lines.extend(_render_section(setup_section))
    return "\n".join(lines)


def _load_state():
    if not config_exists():
        print(f"No config found at {DEFAULT_CONFIG_PATH}.\nRun `npmpi setup` first.")
        sys.exit(1)
    cfg = load_config()
    if not creds_exist():
        print(f"No credential file found at {DEFAULT_CREDS_PATH}.\nRun `npmpi setup` first.")
        sys.exit(1)
    creds = load_creds()
    return cfg, creds


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv

    if not argv:
        if not config_exists():
            print("No configuration found - looks like this is your first run.\n")
            rc = setup.cmd_setup({}, {}, None)
            sys.exit(rc or 0)
        print(PLAIN_HELP)
        return

    if argv[0] in ("-e", "--examples"):
        print(_extended_help())
        return

    if argv[0] in ("-h", "--help"):
        print(PLAIN_HELP)
        return

    cmd_name = argv[0]
    rest = argv[1:]

    if cmd_name == "setup" and rest and rest[0] in ("-h", "--help"):
        print(_setup_help_section())
        return

    import argparse
    parser = argparse.ArgumentParser(prog="npmpi", add_help=False)
    subparsers = parser.add_subparsers(dest="command")
    for mod in COMMANDS:
        mod.register(subparsers)

    if cmd_name not in {"add", "sync", "gen", "migrate", "setup"}:
        print(f"Unknown command: {cmd_name}\n")
        print(PLAIN_HELP)
        sys.exit(1)

    args = parser.parse_args(argv)

    if getattr(args, "_skip_config_load", False):
        # setup: config/creds may not exist yet, and setup itself doesn't need them
        cfg, creds = {}, {}
    else:
        cfg, creds = _load_state()

    rc = args.func(cfg, creds, args)
    sys.exit(rc or 0)
