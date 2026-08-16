"""
Shared help text. Kept separate from cli.py so commands (e.g. setup) can
print the command overview too without a circular import against cli.py.
"""

PLAIN_HELP = """npmpi - manage Nginx Proxy Manager + Pi-hole hostnames across your sites

Commands:
  npmpi add [SITE] NODE-NAME [-s] OCTET PORT   Create a new hostname
  npmpi sync                                   Backfill cross-site mirroring
  npmpi list [SITE] [SEARCH]                   List/search proxy hosts, grouped by backend
  npmpi find [SITE] TERM                       Search one/every site for TERM, list-style table
  npmpi gen                                    Creates an index.html listing all your NPM nodes
  npmpi migrate [SITE]                         Move an NPM instance, with backups
  npmpi setup                                  Run / re-run interactive setup
                                                (npmpi setup --fix to correct one thing instead)
  npmpi gui                                    Launch the desktop GUI (every command, one window)

Run `npmpi -e` for full syntax and examples for every command.
Run `npmpi setup -h` for just the setup section of that (including --fix).
"""
