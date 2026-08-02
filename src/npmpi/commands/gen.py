"""
npmpi gen - generate the static HTML dashboard of every proxy host on a
site's NPM (rolled in from the old gendash.py, unchanged behavior).

    npmpi gen

If `gen` hasn't been configured yet (no output path/site chosen), this
walks you through that setup on the spot instead of erroring, and offers
to save the choice into config.json for next time.
"""

from __future__ import annotations

import argparse
import datetime
import html
import os

from npmpi import npm as npm_api
from npmpi.config import write_config
from npmpi.creds import get_npm_password

DEFAULT_TITLE = "Home Services"

# Preference order when more than one *icon.* file is found - favicon.ico
# is the most universally-supported browser tab icon format, then the
# common raster/vector formats, then anything else.
_ICON_TYPE_BY_EXT = {
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_ICON_EXT_PRIORITY = [".ico", ".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp"]


def _resolve_output_path(output: str) -> str:
    """If the configured/entered path ends in a folder separator (\\ or /),
    treat it as a directory and write index.html inside it, instead of
    letting open() fail with a cryptic 'Invalid argument' - Windows refuses
    to open a path with no filename component at all."""
    if output.endswith("\\") or output.endswith("/"):
        return output + "index.html"
    return output


def _find_icon(output_dir: str) -> str | None:
    """Look in the same directory the dashboard is written to for any file
    named *icon.<ext> (e.g. favicon.ico, icon.png, tab-icon.svg) to use as
    the browser tab icon - case-insensitive, since Windows shares usually
    are. If more than one matches, prefers .ico, then .png/.svg, then
    whatever else, alphabetically within a tier."""
    try:
        entries = os.listdir(output_dir or ".")
    except OSError:
        return None

    candidates = []
    for name in entries:
        base, ext = os.path.splitext(name)
        ext = ext.lower()
        if base.lower().endswith("icon") and ext in _ICON_TYPE_BY_EXT:
            candidates.append(name)
    if not candidates:
        return None

    candidates.sort(key=lambda n: (_ICON_EXT_PRIORITY.index(os.path.splitext(n)[1].lower()), n.lower()))
    return candidates[0]


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "gen",
        help="Generate the static HTML services dashboard",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--output", default=None, help="Override the configured output path for this run only")
    p.add_argument("--title", default=None, help="Override the configured page title for this run only")
    p.set_defaults(func=cmd_gen)


def _ensure_gen_configured(cfg: dict) -> dict:
    gen = cfg.get("gen", {})
    if gen.get("enabled") and gen.get("output"):
        return gen

    print("`gen` hasn't been set up yet. Let's configure it now.\n")
    site_keys = list(cfg["sites"].keys())
    if len(site_keys) == 1:
        site = site_keys[0]
    else:
        site = input(f"Which site's NPM should the dashboard list? ({'/'.join(site_keys)}): ").strip()
        while site not in site_keys:
            site = input(f"Please enter one of {site_keys}: ").strip()

    output = input("Path to write index.html to (must include the filename, "
                   "e.g. \\\\server\\share\\home-services\\index.html): ").strip()
    title = input(f"Page title [{DEFAULT_TITLE}]: ").strip() or DEFAULT_TITLE

    cfg["gen"] = {"enabled": True, "site": site, "output": output, "title": title}
    write_config(cfg)
    print("\nSaved `gen` settings to config.json.\n")
    return cfg["gen"]


def build_cards(hosts: list[dict]) -> list[dict]:
    cards = []
    for h in hosts:
        if not h.get("enabled", True):
            continue
        domains = h.get("domain_names", [])
        if not domains:
            continue
        scheme = "https" if h.get("certificate_id", 0) else "http"
        primary = domains[0]
        aliases = domains[1:]
        cards.append({
            "primary": primary,
            "url": f"{scheme}://{primary}",
            "aliases": [{"name": a, "url": f"{scheme}://{a}"} for a in aliases],
        })
    cards.sort(key=lambda c: c["primary"].lower())
    return cards


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
{icon_link}<style>
  :root {{
    color-scheme: light dark;
    --bg: #14161a; --fg: #e6e6e6; --subtitle: #888;
    --input-bg: #1e2126; --input-border: #333; --accent: #5a8dee;
    --card-bg: #1e2126; --card-border: #2a2d33;
    --scheme-https-bg: #1f4d2e; --scheme-https-fg: #7be3a0;
    --scheme-http-bg: #4d3a1f; --scheme-http-fg: #e3b87b;
    --alias-fg: #999; --empty-fg: #666; --footer-fg: #555;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f5f6f8; --fg: #1a1a1a; --subtitle: #666;
      --input-bg: #ffffff; --input-border: #ccc; --accent: #2f5fd6;
      --card-bg: #ffffff; --card-border: #e0e2e6;
      --scheme-https-bg: #d9f2e3; --scheme-https-fg: #1f7a44;
      --scheme-http-bg: #f2e6d9; --scheme-http-fg: #8a5a1f;
      --alias-fg: #666; --empty-fg: #999; --footer-fg: #999;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: var(--bg); color: var(--fg); padding: 40px 24px; }}
  h1 {{ text-align: center; font-weight: 600; margin-bottom: 8px; }}
  .subtitle {{ text-align: center; color: var(--subtitle); margin-bottom: 28px; font-size: 0.9em; }}
  #search {{ display: block; margin: 0 auto 32px auto; width: 100%; max-width: 420px; padding: 10px 14px;
             border-radius: 8px; border: 1px solid var(--input-border); background: var(--input-bg);
             color: var(--fg); font-size: 1em; }}
  #search:focus {{ outline: none; border-color: var(--accent); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px;
           max-width: 1100px; margin: 0 auto; }}
  .card {{ position: relative; background: var(--card-bg); border: 1px solid var(--card-border);
           border-radius: 12px; padding: 16px 18px; transition: border-color 0.15s, transform 0.15s; cursor: pointer; }}
  .card:hover {{ border-color: var(--accent); transform: translateY(-2px); }}
  .card a.primary {{ color: var(--fg); text-decoration: none; font-size: 1.05em; font-weight: 600;
                      display: block; word-break: break-word; }}
  .card a.primary::after {{ content: ""; position: absolute; inset: 0; border-radius: 12px; }}
  .card a.primary:hover {{ color: var(--accent); }}
  .scheme-badge {{ display: inline-block; font-size: 0.7em; padding: 1px 6px; border-radius: 4px;
                    margin-left: 6px; vertical-align: middle; font-weight: 500; }}
  .scheme-https {{ background: var(--scheme-https-bg); color: var(--scheme-https-fg); }}
  .scheme-http {{ background: var(--scheme-http-bg); color: var(--scheme-http-fg); }}
  .aliases {{ position: relative; z-index: 1; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--card-border); }}
  .aliases a {{ position: relative; z-index: 1; display: block; font-size: 0.82em; color: var(--alias-fg);
                text-decoration: none; margin-top: 4px; }}
  .aliases a:hover {{ color: var(--accent); }}
  .empty {{ text-align: center; color: var(--empty-fg); margin-top: 60px; }}
  footer {{ text-align: center; color: var(--footer-fg); font-size: 0.8em; margin-top: 48px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">{count} services &middot; generated {generated}</div>
<input type="text" id="search" placeholder="Filter..." oninput="filterCards()">
<div class="grid" id="grid">
{cards}
</div>
<div class="empty" id="empty" style="display:none">No matches.</div>
<footer>Generated by npmpi gen</footer>
<script>
function filterCards() {{
  var q = document.getElementById('search').value.toLowerCase();
  var cards = document.querySelectorAll('.card');
  var visible = 0;
  cards.forEach(function(c) {{
    var match = c.dataset.search.indexOf(q) !== -1;
    c.style.display = match ? '' : 'none';
    if (match) visible++;
  }});
  document.getElementById('empty').style.display = visible === 0 ? 'block' : 'none';
}}
</script>
</body>
</html>
"""

CARD_TEMPLATE = """  <div class="card" data-search="{search}">
    <a class="primary" href="{url}" target="_blank" rel="noopener">{name}<span class="scheme-badge scheme-{scheme}">{scheme_label}</span></a>{aliases_html}
  </div>"""

ALIAS_TEMPLATE = """<a href="{url}" target="_blank" rel="noopener">{name}</a>"""


def render(cards: list[dict], title: str, icon: str | None = None) -> str:
    card_html_list = []
    for c in cards:
        scheme = c["url"].split(":", 1)[0]
        aliases_html = ""
        if c["aliases"]:
            alias_links = "".join(
                ALIAS_TEMPLATE.format(url=a["url"], name=html.escape(a["name"]))
                for a in c["aliases"]
            )
            aliases_html = f'<div class="aliases">{alias_links}</div>'
        search_terms = " ".join([c["primary"]] + [a["name"] for a in c["aliases"]]).lower()
        card_html_list.append(CARD_TEMPLATE.format(
            search=html.escape(search_terms), url=c["url"], name=html.escape(c["primary"]),
            scheme=scheme, scheme_label=scheme.upper(), aliases_html=aliases_html,
        ))

    icon_link = ""
    if icon:
        icon_type = _ICON_TYPE_BY_EXT.get(os.path.splitext(icon)[1].lower(), "image/x-icon")
        icon_link = f'<link rel="icon" type="{icon_type}" href="{html.escape(icon)}">\n'

    return PAGE_TEMPLATE.format(
        title=html.escape(title), count=len(cards),
        generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        cards="\n".join(card_html_list),
        icon_link=icon_link,
    )


def cmd_gen(cfg, creds, args) -> int:
    gen = _ensure_gen_configured(cfg)
    site_key = gen["site"]
    site = cfg["sites"][site_key]
    raw_output = args.output or gen["output"]
    output = _resolve_output_path(raw_output)
    if output != raw_output:
        print(f"[gen] output path '{raw_output}' has no filename - writing to '{output}' instead "
              f"(run `npmpi setup --gen` to fix the stored path itself)")
    title = args.title or gen.get("title", DEFAULT_TITLE)

    pw = get_npm_password(creds, site_key)
    print(f"[npm] logging in to {site['npm']['url']} ...")
    token = npm_api.login(site["npm"]["url"], site["npm"]["email"], pw)
    hosts = npm_api.get_proxy_hosts(site["npm"]["url"], token)

    cards = build_cards(hosts)
    print(f"[npm] found {len(cards)} enabled proxy host(s)")

    icon = _find_icon(os.path.dirname(output))
    if icon:
        print(f"[gen] using '{icon}' as the browser tab icon")

    page = render(cards, title, icon)
    with open(output, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {output} ({len(cards)} hosts)")
    return 0
