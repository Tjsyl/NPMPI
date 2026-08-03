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

        # The raw backend NPM actually forwards to - bypasses the reverse
        # proxy entirely (e.g. for direct/internal access or debugging).
        fwd_scheme = h.get("forward_scheme") or "http"
        fwd_host = h.get("forward_host")
        fwd_port = h.get("forward_port")
        destination_url = f"{fwd_scheme}://{fwd_host}:{fwd_port}" if fwd_host and fwd_port else None

        cards.append({
            "primary": primary,
            "url": f"{scheme}://{primary}",
            "aliases": [{"name": a, "url": f"{scheme}://{a}"} for a in aliases],
            "destination_url": destination_url,
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
    --scheme-https-bg: #4d1f1f; --scheme-https-fg: #e37b7b;
    --scheme-http-bg: #4d3a1f; --scheme-http-fg: #e3b87b;
    --alias-fg: #999; --empty-fg: #666; --footer-fg: #555;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f5f6f8; --fg: #1a1a1a; --subtitle: #666;
      --input-bg: #ffffff; --input-border: #ccc; --accent: #2f5fd6;
      --card-bg: #ffffff; --card-border: #e0e2e6;
      --scheme-https-bg: #f2d9d9; --scheme-https-fg: #7a1f1f;
      --scheme-http-bg: #f2e6d9; --scheme-http-fg: #8a5a1f;
      --alias-fg: #666; --empty-fg: #999; --footer-fg: #999;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: var(--bg); color: var(--fg); padding: 40px 24px; }}
  h1 {{ text-align: center; font-weight: 600; margin-bottom: 4px; }}
  .subtitle {{ text-align: center; color: var(--subtitle); margin-bottom: 28px; font-size: 0.9em; }}
  .header-row {{ display: flex; align-items: center; justify-content: center; gap: 16px;
                 flex-wrap: wrap; margin-bottom: 28px; }}
  .title-icon {{ height: 72px; width: 72px; object-fit: contain; flex-shrink: 0; }}
  .header-text {{ text-align: left; }}
  .header-text h1 {{ text-align: left; margin: 0 0 4px; }}
  .header-text .subtitle {{ text-align: left; margin: 0; }}
  .controls-row {{ display: flex; align-items: center; justify-content: center; gap: 24px;
                    max-width: 620px; margin: 0 auto 32px auto; flex-wrap: wrap; }}
  #search {{ display: block; flex: 1 1 320px; max-width: 420px; padding: 10px 14px;
             border-radius: 8px; border: 1px solid var(--input-border); background: var(--input-bg);
             color: var(--fg); font-size: 1em; }}
  #search:focus {{ outline: none; border-color: var(--accent); }}
  .toggle-stack {{ display: flex; flex-direction: column; gap: 10px; flex-shrink: 0; }}
  .toggle {{ display: flex; align-items: center; gap: 8px; font-size: 0.8em; color: var(--subtitle);
             user-select: none; cursor: pointer; }}
  .toggle input {{ display: none; }}
  .toggle .slider {{ width: 36px; height: 20px; border-radius: 999px; background: var(--input-border);
                      position: relative; flex-shrink: 0; transition: background 0.15s; }}
  .toggle .slider::before {{ content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px;
                              border-radius: 50%; background: #fff; transition: transform 0.15s; }}
  .toggle input:checked + .slider {{ background: var(--accent); }}
  .toggle input:checked + .slider::before {{ transform: translateX(16px); }}
  .toggle input:disabled + .slider {{ opacity: 0.4; }}
  .toggle:has(input:disabled) {{ cursor: default; opacity: 0.6; }}
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
  .destination {{ position: relative; z-index: 1; display: none; margin-top: 8px; padding-top: 8px;
                   border-top: 1px solid var(--card-border); font-size: 0.78em; word-break: break-word; }}
  body.show-destinations .destination {{ display: block; }}
  .destination a {{ position: relative; z-index: 1; color: var(--alias-fg); text-decoration: none;
                     pointer-events: none; cursor: default; }}
  body.clickable-destinations .destination a {{ color: var(--accent); text-decoration: underline;
                                                  pointer-events: auto; cursor: pointer; }}
  .empty {{ text-align: center; color: var(--empty-fg); margin-top: 60px; }}
  footer {{ text-align: center; color: var(--footer-fg); font-size: 0.8em; margin-top: 48px; }}
</style>
</head>
<body>
{header_block}
<div class="controls-row">
<input type="text" id="search" placeholder="Filter..." oninput="filterCards()">
<div class="toggle-stack">
  <label class="toggle">
    <input type="checkbox" id="toggle-dest" onchange="toggleDestinations()">
    <span class="slider"></span>Show Destinations
  </label>
  <label class="toggle">
    <input type="checkbox" id="toggle-clickable" disabled onchange="toggleClickable()">
    <span class="slider"></span>Clickable Destinations
  </label>
</div>
</div>
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
function toggleDestinations() {{
  var shown = document.getElementById('toggle-dest').checked;
  document.body.classList.toggle('show-destinations', shown);
  var clickableToggle = document.getElementById('toggle-clickable');
  clickableToggle.disabled = !shown;
  if (!shown) {{
    clickableToggle.checked = false;
    document.body.classList.remove('clickable-destinations');
  }}
}}
function toggleClickable() {{
  document.body.classList.toggle('clickable-destinations', document.getElementById('toggle-clickable').checked);
}}
</script>
</body>
</html>
"""

CARD_TEMPLATE = """  <div class="card" data-search="{search}">
    <a class="primary" href="{url}" target="_blank" rel="noopener">{name}<span class="scheme-badge scheme-{scheme}">{scheme_label}</span></a>{aliases_html}{destination_html}
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

        destination_html = ""
        if c.get("destination_url"):
            dest_url = html.escape(c["destination_url"])
            destination_html = f'<div class="destination"><a href="{dest_url}" target="_blank" rel="noopener">{dest_url}</a></div>'

        search_terms = " ".join([c["primary"]] + [a["name"] for a in c["aliases"]]).lower()
        card_html_list.append(CARD_TEMPLATE.format(
            search=html.escape(search_terms), url=c["url"], name=html.escape(c["primary"]),
            scheme=scheme, scheme_label=scheme.upper(), aliases_html=aliases_html,
            destination_html=destination_html,
        ))

    escaped_title = html.escape(title)
    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle_text = f"{len(cards)} services &middot; generated {generated}"

    icon_link = ""
    if icon:
        icon_href = html.escape(icon)
        icon_type = _ICON_TYPE_BY_EXT.get(os.path.splitext(icon)[1].lower(), "image/x-icon")
        icon_link = f'<link rel="icon" type="{icon_type}" href="{icon_href}">\n'
        # Icon to the left of a left-aligned title+subtitle stack, vertically
        # centered against that two-line block (align-items: center on the
        # flex row) - not a standalone centered image, and not inline with
        # just one of the two lines.
        header_block = (
            f'<div class="header-row">'
            f'<img class="title-icon" src="{icon_href}" alt="">'
            f'<div class="header-text"><h1>{escaped_title}</h1>'
            f'<div class="subtitle">{subtitle_text}</div></div>'
            f'</div>'
        )
    else:
        header_block = f'<h1>{escaped_title}</h1>\n<div class="subtitle">{subtitle_text}</div>'

    return PAGE_TEMPLATE.format(
        title=escaped_title,
        cards="\n".join(card_html_list),
        icon_link=icon_link,
        header_block=header_block,
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
