# npmpi

One CLI for managing Nginx Proxy Manager + Pi-hole hostnames across two
sites (e.g. a home network and a remote/travel site), instead of juggling
separate scripts per domain/scope.

Replaces: `addhost.py`, `addhostm.py`, `addhome.py`, `addm.py`,
`appendhost.py`, `appendhostm.py`, `appendhome.py`, `appendm.py`,
`synchome2m.py`, `syncm2home.py`, `gendash.py`, `npm_migrate.py`.

## Install

**Option A - one-time bootstrap (recommended):**

```powershell
.\install.ps1
```

Checks for Python, git, and pipx (offering to install any that are
missing via `winget`), then installs npmpi straight from GitHub with
`pipx` so the `npmpi` command works from any terminal - cmd, PowerShell,
Windows Terminal - with no wrapper scripts to maintain.

**Option B - manual:**

```powershell
pipx install git+https://github.com/USERNAME/npmpi.git
```

or, for local development against a cloned copy:

```powershell
pip install -e .
```

> `pipx` is strongly preferred over plain `pip install` for this -
> it installs npmpi into its own isolated environment and puts a real
> `npmpi` launcher on PATH automatically. A plain `pip install` only
> gives you a global command if the Python environment you installed
> into is already on PATH (true for a base/system Python install, not
> guaranteed for a venv).

## First run

```
npmpi setup
```

Walks you through:

- How many sites/networks (normally 2 - your two domain letters, e.g. `h`
  and `m`)
- Each site's domain suffix, backend IP prefix, NPM connection info, and
  one or more Pi-holes
- Whether to set up `npmpi gen` (the dashboard generator) now, or later

Credentials are collected once and encrypted into a single file via
Windows DPAPI - tied to your Windows user + machine, never a master
password to remember, but also not portable to another machine (see
[Credential storage](#credential-storage) below). Config lives in a
plain JSON file you can hand-edit afterward.

Re-run `npmpi setup` any time - e.g. after a password change or an IP
scheme change.

## Commands

Run `npmpi` with no arguments for a quick command list, or `npmpi -e` for
full syntax + examples for every command.

### `npmpi add`

```
npmpi add [SITE] NAME [-s|--https] OCTET PORT
```

- `npmpi add m test 99 8888` - creates `test.m.tjsyl.com`, http, backend
  `<m's ip prefix>99:8888`. Site `m` only - no cross-site mirroring.
- `npmpi add h test -s 99 8888` - creates `test.home.tjsyl.com`, https,
  backend `<h's ip prefix>99:8888`. Site `h` only.
- `npmpi add test -s 99 8888` (no site letter) - creates **both**
  `test.m.tjsyl.com` and `test.home.tjsyl.com` as real backends on their
  own networks, **and** cross-mirrors each onto the other site's
  Pi-hole(s)/NPM, so either name resolves and works no matter which
  network you're on.

Safe to re-run: if a hostname already exists on the target NPM, that step
is reported and skipped rather than erroring - no separate "append"
command needed for the common case.

### `npmpi sync`

```
npmpi sync [--dry-run] [--only PREFIX ...] [--repair-pihole]
```

Checks both sites and mirrors anything that only exists on one side -
e.g. things added with `npmpi add h`/`npmpi add m` (single-site, no
mirroring) while the other site was unreachable. This is the command to
run once the other site comes back online, to catch it up.

> **Why isn't full mirroring the default for every `add`?** The `m`
> network sits in a small travel hardcase and is only reachable when it's
> plugged in. `npmpi add m`/`npmpi add h` always work regardless of the
> other site's status; the mirroring step in a domain-less `npmpi add`
> can partially fail if the other site is offline at that moment - `sync`
> is the reliable catch-up path for exactly that case.

### `npmpi gen`

```
npmpi gen [--output PATH] [--title TEXT]
```

Regenerates the static HTML dashboard listing every enabled proxy host on
a site's NPM - one clickable card per host, alphabetically sorted, with a
client-side search box. Self-contained HTML (no external CSS/JS), so it
works fine served from a purely offline/LAN web server.

If `gen` was skipped during `npmpi setup`, running `npmpi gen` walks you
through picking a site/output path/title on the spot and saves the
choice to `config.json` for next time.

### `npmpi migrate`

```
npmpi migrate [SITE]
```

Interactively moves a site's NPM proxy hosts to a new NPM instance (e.g.
after rebuilding a broken container). Before touching anything, it:

1. Explains what it's about to do.
2. Backs up the source NPM's proxy hosts + certificates to a JSON file at
   a path you choose.
3. Offers to *also* back up that site's Pi-hole local DNS records to a
   separate JSON file - independent of the NPM backup, since the two
   systems can drift apart on their own.
4. Previews exactly what would be created on the destination NPM before
   asking you to confirm.

### `npmpi setup`

Re-run any time to change the number of sites, IP schemes, or
credentials.

## Config file

`~/.npmpi/config.json` - genuine JSON with `//` comments allowed (a tiny
loader strips them before parsing), so you can hand-edit e.g. an IP
address without re-running the whole wizard. Every field has an inline
comment explaining what it's for.

## Credential storage

`~/.npmpi/credentials.dat` - all passwords combined into one file,
encrypted with Windows DPAPI (`CryptProtectData`/`CryptUnprotectData` via
`ctypes`, no extra dependency). This ties the file to your Windows user
account **and** machine - it cannot be decrypted anywhere else, even by
you, even if copied. That's intentional: zero master password, zero
prompts, ever. If you ever need npmpi on a different machine, run
`npmpi setup` again there.

## Requirements

- Windows (credential storage is DPAPI-based)
- Python 3.10+
- git (only needed for the `pipx install git+...` install step)

## What changed from the old scripts

- 12 separate `.py`/`.cmd`/`.ps1` files → one installed command.
- 5 separate DPAPI credential files → 1 combined file.
- Hand-maintained `PATH`/wrapper `.cmd` files → a real installed console
  command via `pipx`.
- `synchome2m.py` + `syncm2home.py` → one `npmpi sync` (does both
  directions).
- `addhost*`/`addhome`/`addm` → one `npmpi add`, with the site letter
  (or lack of one) choosing scope instead of four separate scripts.
- `appendhost*`/`appendhome`/`appendm` → folded into `npmpi add`'s
  auto-detect-existing behavior; no separate command needed.
- `npm_migrate.py`'s export/import split → one guided `npmpi migrate`
  flow with backup prompts built in (including Pi-hole DNS, which the
  old tool didn't back up at all).
