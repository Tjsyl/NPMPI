"""
Config file handling for npmpi.

The config file is genuine JSON with `//` line comments and `/* */` block
comments allowed in it (a superset sometimes called "JSONC"). Comments are
stripped by a small pre-processor before the file is handed to json.loads,
and every value npmpi writes back out is preceded by a `//` description
line so the file stays self-documenting if you open it by hand.

This is deliberately NOT YAML/TOML - Travis asked for a .json file, this
just makes it tolerate hand-written comments too.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_DIR = Path.home() / ".npmpi"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"

_STRING_OR_COMMENT = re.compile(
    r'"(?:\\.|[^"\\])*"'      # a JSON string literal (left untouched)
    r'|//[^\n]*'              # a // line comment
    r'|/\*.*?\*/',            # a /* block comment */
    re.DOTALL,
)


def strip_json_comments(text: str) -> str:
    """Remove //... and /*...*/ comments that live OUTSIDE string literals."""

    def _sub(m: re.Match) -> str:
        s = m.group(0)
        if s.startswith('"'):
            return s  # leave string literals alone
        return ""  # drop the comment

    return _STRING_OR_COMMENT.sub(_sub, text)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"No config found at {path}. Run `npmpi setup` first."
        )
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(strip_json_comments(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"Config file at {path} is not valid JSON: {e}") from e


def config_exists(path: Path = DEFAULT_CONFIG_PATH) -> bool:
    return path.exists()


# --------------------------------------------------------------------------
# Commented JSON writer
# --------------------------------------------------------------------------
#
# json.dump can't emit comments, so the config is written by hand as text
# with an explicit field order + one // description per field, instead of
# generically serializing a dict. Keeps the file readable/editable by hand,
# which is the whole point of allowing comments in it.

def _site_block(key: str, site: dict[str, Any], indent: str = "    ") -> str:
    piholes_lines = []
    for ph in site["piholes"]:
        piholes_lines.append(
            f'{indent}    {{ "name": {json.dumps(ph["name"])}, "url": {json.dumps(ph["url"])} }}'
        )
    piholes_json = ",\n".join(piholes_lines)

    return f'''{indent}// --- site "{key}" ---
{indent}"{key}": {{
{indent}    // Domain suffix hostnames on this site get, e.g. "example" -> example.{site["domain"]}
{indent}    "domain": {json.dumps(site["domain"])},

{indent}    // Backend IP prefix for this site's network. The last octet you pass to
{indent}    // `npmpi add` is appended to this, e.g. prefix {json.dumps(site["ip_prefix"])} + octet 99 -> {site["ip_prefix"]}99
{indent}    "ip_prefix": {json.dumps(site["ip_prefix"])},

{indent}    // This site's Nginx Proxy Manager
{indent}    "npm": {{
{indent}        "url": {json.dumps(site["npm"]["url"])},
{indent}        "email": {json.dumps(site["npm"]["email"])}
{indent}    }},

{indent}    // IP that this site's Pi-hole(s) should resolve new hostnames to (normally the NPM IP above)
{indent}    "npm_target_ip": {json.dumps(site["npm_target_ip"])},

{indent}    // This site's Pi-hole(s) - DNS records get pushed to every one listed here
{indent}    "piholes": [
{piholes_json}
{indent}    ]
{indent}}}'''


def write_config(cfg: dict[str, Any], path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    site_keys = list(cfg["sites"].keys())
    site_blocks = ",\n\n".join(_site_block(k, cfg["sites"][k], indent="        ") for k in site_keys)

    gen = cfg.get("gen", {"enabled": False})
    enabled_line = f'"enabled": {json.dumps(gen.get("enabled", False))}'
    if gen.get("enabled"):
        enabled_line += ","

    gen_block = f'''    // Dashboard generator (rolled in from the old gendash.py) - `npmpi gen`
    "gen": {{
        // Whether `npmpi gen` is configured. If false, running `npmpi gen` will
        // walk you through setup on demand instead of erroring.
        {enabled_line}'''

    if gen.get("enabled"):
        gen_block += f'''
        // Which site's NPM to read the proxy host list from
        "site": {json.dumps(gen.get("site", site_keys[0]))},
        // Where the generated index.html gets written (overwritten in place each run)
        "output": {json.dumps(gen.get("output", ""))},
        // Page title shown at the top of the generated dashboard
        "title": {json.dumps(gen.get("title", "Home Services"))}'''
    gen_block += "\n    }"

    text = f'''{{
    // npmpi config - see README for the full field reference.
    // This file is genuine JSON with // comments stripped before parsing,
    // so you can hand-edit it (e.g. change an IP) without re-running setup.
    // Re-run `npmpi setup` any time to regenerate this file interactively.

    "sites": {{
{site_blocks}
    }},

{gen_block}
}}
'''
    path.write_text(text, encoding="utf-8")
