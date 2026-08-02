# npmpi

One CLI for managing Nginx Proxy Manager + Pi-hole hostnames across two
sites (e.g. a home network and a remote/travel site), instead of juggling
separate scripts per domain/scope.

Replaces: `addhost.py`, `addhostm.py`, `addhome.py`, `addm.py`,
`appendhost.py`, `appendhostm.py`, `appendhome.py`, `appendm.py`,
`synchome2m.py`, `syncm2home.py`, `gendash.py`, `npm_migrate.py`.

## Install

npmpi ships as a **standalone `npmpi.exe`** - no Python, no pip, nothing
else required on the machine you run it on. Every version tag builds
both forms below automatically via GitHub Actions and attaches them to
that release.

**Option A - self-extracting installer (recommended):**

Download `npmpi-setup.exe` from the [Releases page](../../releases) and
run it. Installs to `%LOCALAPPDATA%\npmpi`, adds that folder to your
user PATH, and registers a normal uninstaller in *Add/Remove Programs*.
No admin rights needed (per-user install, no UAC prompt). Uninstalling
never touches `~/.npmpi/config.json` or `credentials.dat` - those are
managed entirely by `npmpi setup`.

**Option B - installer script:**

```powershell
.\install.ps1
```

Downloads the latest `npmpi.exe` (not the installer - just the raw exe)
from this repo's GitHub Releases into `%LOCALAPPDATA%\npmpi` and adds
that folder to your user PATH, so `npmpi` works from any terminal - cmd,
PowerShell, Windows Terminal. Safe to re-run any time to grab an update.
No uninstaller entry (just delete the folder and PATH entry yourself if
you ever want it gone) - use Option A if you'd rather have a proper
uninstall path.

**Option C - manual download:**

Grab `npmpi.exe` from the [Releases page](../../releases) yourself and
put it anywhere on your PATH.

> Neither the exe nor the installer is code-signed (that needs a paid
> certificate), so Windows SmartScreen/Defender will likely flag it as
> unrecognized the first time you run it. That's expected for an indie
> tool, not a sign anything's wrong - click "More info" -> "Run anyway".
> If you'd rather avoid that prompt entirely, build it yourself locally
> instead (see below).

**Option D - build the exe yourself:**

```powershell
python -m pip install -e .[build]
.\build_exe.ps1
```

Produces `dist\npmpi.exe` using PyInstaller, built locally so there's
nothing to trust but your own machine. Must be run on Windows
(PyInstaller doesn't cross-compile). If `python` errors with "Python was
not found..." even though you've installed it, that's the Windows Store's
App Execution Alias stub shadowing the real thing - `build_exe.ps1`
auto-detects and falls back to the `py` launcher, but if both fail, see
the error message it prints for the fix (reinstall with PATH checked +
new terminal window, or disable the alias under *Settings > Apps >
Advanced app settings > App execution aliases*).

**Option E - build the installer yourself:**

```powershell
.\build_installer.ps1 -Version 0.1.8
```

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed.
Builds `dist\npmpi.exe` first, then compiles `npmpi_installer.iss` into
`installer_output\npmpi-setup.exe`. `-Version` is just cosmetic (shown in
Add/Remove Programs) - omit it and it defaults to `0.0.0-dev`.

**Option F - run from source (for development):**

```powershell
pip install -e .
```

Gives you a `npmpi` command backed by your local Python install rather
than a compiled exe - useful while making changes to the code.

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

Made a typo in one field later on (wrong IP, missing port, bad URL)?
You don't have to redo the whole wizard - see `npmpi setup --fix` under
[`npmpi setup`](#npmpi-setup) below.

## Commands

Run `npmpi` with no arguments for a quick command list, or `npmpi -e` for
full syntax + examples for every command.

### `npmpi add`

```
npmpi add [SITE] NODE-NAME [-s|--https] OCTET PORT
```

- `npmpi add m test 99 8888` - creates `test.m.example.com`, http, backend
  `10.0.2.99:8888`. Site `m` only - no cross-site mirroring.
- `npmpi add h test -s 99 8888` - creates `test.home.example.com`, https,
  backend `10.0.1.99:8888`. Site `h` only.
- `npmpi add test -s 99 8888` (no site letter) - creates **both**
  `test.m.example.com` and `test.home.example.com` as real backends on
  their own networks, **and** cross-mirrors each onto the other site's
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
works fine served from a purely offline/LAN web server. It reads live
from NPM every time it runs - nothing about the dashboard's contents is
frozen at setup time, only *which* site/path/title to use is configured
once.

The output path **must include the filename** (e.g.
`\\server\share\home-services\index.html`), not just a folder. If it's
given a path ending in a folder separator by mistake, it writes
`index.html` inside that folder rather than erroring.

For a browser tab icon *and* a small logo next to the page title, drop
any file named `*icon.*` (e.g. `favicon.ico`, `icon.png`,
`tab-icon.svg`) in the same folder as the generated `index.html` - it's
picked up automatically on the next `npmpi gen`, no config needed, and
used for both. If no icon file is found, the title just shows on its
own (e.g. "Home Services" or whatever custom title you set via
`npmpi setup --gen`, with no icon). Matching is case-insensitive; if
more than one icon file is present, `.ico` wins, then `.png`/`.svg`,
then anything else (alphabetically as a final tiebreak).

If `gen` was skipped during `npmpi setup`, running `npmpi gen` walks you
through picking a site/output path/title on the spot and saves the
choice to `config.json` for next time. Already configured but need to
change the site/path/title? `npmpi setup --gen` re-runs just that (see
[`npmpi setup`](#npmpi-setup) below) instead of the whole wizard.

### `npmpi migrate`

```
npmpi migrate [SITE]
```

Interactively moves a site's NPM proxy hosts to a new NPM instance (e.g.
after rebuilding a broken container). Before touching anything, it:

1. Explains what it's about to do.
2. Backs up the source NPM's proxy hosts + certificates to a JSON file at
   a path you choose.
3. Offers to *also* back up that site's Pi-hole(s) - independent of the
   NPM backup, since the two systems can drift apart on their own. Your
   choice of:
   - **DNS records only** - lightweight JSON export of just the custom
     local DNS records (what npmpi itself manages).
   - **Full Teleporter backup** - Pi-hole's own complete config archive
     (DNS records, blocklists, groups, settings - everything), via the
     same `/api/teleporter` endpoint the web UI's Export button uses.
     One `.zip` per configured Pi-hole.
4. Previews exactly what would be created on the destination NPM before
   asking you to confirm.

### `npmpi setup`

Re-run any time to change the number of sites, IP schemes, or
credentials. Made one mistake in one field? You don't have to redo the
whole wizard:

```
npmpi setup --fix              List everything fixable, with its current value
npmpi setup --paths            Show where config.json / credentials.dat live
npmpi setup --npm [SITE]       Re-run just one site's NPM config
npmpi setup --pihole N [url]   Re-run just Pi-hole #N's config
npmpi setup --gen              Re-run just the dashboard (gen) config
```

Pi-holes are numbered continuously across **all** sites, in the order
they're configured - not restarted per site. So if site `h` has two
Pi-holes and site `m` has one, they're `#1`/`#2`/`#3`, not `#1`/`#2`
for `h` and a separate `#1` for `m`. Run `npmpi setup --fix` any time to
see the current numbering and every current value. Add the word `url`
after the number (e.g. `npmpi setup --pihole 2 url`) to fix only that
Pi-hole's URL and leave its name/password untouched.

`npmpi setup -h` shows just this section (syntax + examples for
`setup` only); `npmpi -e` includes it as part of the full command
reference.

## Uninstalling

If you installed via **Option A** (`npmpi-setup.exe`): uninstall through
*Add/Remove Programs* (or *Apps* in Windows Settings) like any normal
app - this removes `npmpi.exe` and the PATH entry it added, and leaves
`~/.npmpi/config.json`/`credentials.dat` in place.

If you installed via **Option B/C** (`install.ps1` or a manual download):
there's no registered uninstaller - delete `%LOCALAPPDATA%\npmpi` and
remove that folder from your user PATH (System Properties -> Environment
Variables, or `[Environment]::SetEnvironmentVariable` in PowerShell)
yourself.

Either way, `~/.npmpi/config.json` and `~/.npmpi/credentials.dat` are
never touched automatically - delete them yourself if you want a
completely clean slate.

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

To **run** the `npmpi.exe`/`npmpi-setup.exe` release build: Windows
only (credential storage is DPAPI-based). Nothing else - no Python
needed.

To **build the exe** yourself: Python 3.10+ and `pip install -e .[build]`
(pulls in PyInstaller).

To **build the installer** yourself: the above, plus
[Inno Setup 6](https://jrsoftware.org/isinfo.php).

## What changed from the old scripts

- 12 separate `.py`/`.cmd`/`.ps1` files → one standalone `npmpi.exe`
  (or `npmpi-setup.exe` for a proper installed/uninstallable copy).
- 5 separate DPAPI credential files → 1 combined file.
- Hand-maintained `PATH`/wrapper `.cmd` files → a real command on PATH,
  no Python installation required to run it at all.
- Domain suffix, IP prefix, NPM/Pi-hole URLs → nothing is hardcoded in
  the code anywhere; all of it is defined interactively in `npmpi setup`
  (or by hand-editing the commented `config.json` it writes) and re-runnable
  any time IP schemes or passwords change - including one field at a time
  via `npmpi setup --fix`/`--npm`/`--pihole`/`--gen`, without redoing the
  whole wizard.
- `synchome2m.py` + `syncm2home.py` → one `npmpi sync` (does both
  directions).
- `addhost*`/`addhome`/`addm` → one `npmpi add`, with the site letter
  (or lack of one) choosing scope instead of four separate scripts.
- `appendhost*`/`appendhome`/`appendm` → folded into `npmpi add`'s
  auto-detect-existing behavior; no separate command needed.
- `npm_migrate.py`'s export/import split → one guided `npmpi migrate`
  flow with backup prompts built in - DNS-records-only or a full Pi-hole
  Teleporter archive, your choice (the old tool didn't back up Pi-hole
  at all).
