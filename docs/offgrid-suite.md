# Off-grid suite

The off-grid images are the Reticulum host with more programs for running without the internet, from the
`offgrid_suite` Ansible role. Everything in the [host guide](host-guide.md) applies to them too.

| Program | What it does | Unit | Where |
|---|---|---|---|
| Kiwix | Offline library: Wikipedia, medical, repair and survival guides, and more | `kiwix` | `http://reticulum-host.local/library/` |
| Check-in bot | Check-ins, notices and the net schedule by LXMF message, and a list of everyone heard | `offgrid-checkin` | Its address in the login banner; `/notices/` and `/contacts/` |

## Get the off-grid images

Build them like the standard images, with `offgrid`:

```bash
./build-iso.sh offgrid
./build-pi-image.sh offgrid
```

They are copied to `build/reticulum-offgrid-amd64.hybrid.iso` and `build/reticulum-offgrid-pi-arm64.img.xz`, and are
used the same way as the standard ones.

To add the suite to a machine you already have, run `offgrid.yml` instead of `site.yml`, with the web page on:

```bash
cd ansible
ansible-playbook -i localhost, -c local offgrid.yml -K -e reticulum_host_http_files=true
```

## Kiwix offline library

Kiwix serves ZIM files: packed, searchable copies of websites. The images hold none, since a useful set is 10 to
100 GB; they go on an external drive that you prepare once on another computer.

### Prepare the library drive

1. Use a USB drive or SSD big enough for the ZIM files you want. An SSD is faster and more robust than a USB stick.

2. Format it as exFAT or ext4 and name (label) it `OFFGRID-ZIM`, exactly. For example, on Linux, where `/dev/sdX1` is
   the drive's partition (check with `lsblk` first; formatting erases it):

   ```bash
   sudo mkfs.exfat -L OFFGRID-ZIM /dev/sdX1
   ```

   On Windows or macOS, format it as exFAT and give it that name in the format dialog.

3. Download ZIM files from the [Kiwix library](https://library.kiwix.org/) and copy them to the top level of the
   drive, not into a folder. Good choices for off-grid use:

   | ZIM | About |
   |---|---|
   | WikiMed (`mdwiki_en_all`) | Medical encyclopedia, about 2 GB |
   | Wikipedia without pictures (`wikipedia_en_all_nopic`) | All of English Wikipedia, about 50 GB |
   | Wikivoyage (`wikivoyage_en_all`) | Travel and local information |
   | iFixit (`ifixit_en_all`) | Repair guides |
   | Wiktionary (`wiktionary_en_all`) | Dictionary |

   Each ZIM comes in sizes: `maxi` is complete, `nopic` has no pictures, and `mini` holds only summaries.

### Use it

Plug the drive into the host, at any time. The host mounts it read only at `/srv/offgrid/zim` and starts Kiwix; the
library is at `http://reticulum-host.local/library/`, linked from the host's page. Since it is mounted read only, it
can be unplugged at any time; Kiwix stops with it.

To add ZIM files, unplug the drive, copy them to it on another computer, and plug it back in.

Without the drive, the library page says it is not available, and the health page shows Kiwix as stopped until
needed.

### Settings

- Runs as a temporary system user, unit `kiwix`, on this host only; nginx serves it at `/library/`.
- Drive: `srv-offgrid-zim.mount`, which mounts any drive labelled `OFFGRID-ZIM`.
- Ansible variables: `offgrid_suite_kiwix` (on or off), `offgrid_suite_kiwix_drive_label`, `offgrid_suite_kiwix_dir`,
  `offgrid_suite_kiwix_port`.

To check it: `systemctl status srv-offgrid-zim.mount kiwix` shows whether the drive is mounted and Kiwix is running.
If Kiwix does not start, check the drive's label with `lsblk -f`, and that the `.zim` files are at its top level.

## Check-in bot

An LXMF address people message from Sideband, MeshChat or Columba, like any contact. It is how people tell the
operators they are OK, and how they get notices without a web browser. Its address is in the login banner and on
the host's page as "Check-in bot"; it also announces itself every 30 minutes, so it shows up in people's apps.

| Message | Reply |
|---|---|
| `checkin <status>`, such as `checkin All 4 of us OK at the school` | Confirms, with the time. A new check-in replaces the sender's earlier one. |
| `status` | The operators' notices |
| `nets` | The net schedule |
| `help`, or anything else | The list of commands |

Operators, listed by LXMF address, also have:

| Message | Does |
|---|---|
| `list` | The number checked in, and the latest ten |
| `notice <text>` | Replaces the notices |
| `nets <text>` | Replaces the net schedule |
| `broadcast <text>` | Sends the text to everyone who has checked in |

The bot answers a sender at most every 20 seconds, keeps messages short for radio links, never answers another
copy of itself, and sends replies through the host's propagation node when the sender is offline.

### Set it up

1. **Operators:** put each operator's LXMF address, one per line, in `/var/lib/reticulum/offgrid/operators.txt`. The
   bot reads it on every message; no restart is needed. With Ansible, list them in `offgrid_suite_operators`.

2. **Dashboard password:** the contacts page needs one, and the images ship without it. Set it on the host:

   ```bash
   sudo offgrid-dashboard-password
   ```

   It asks for a password for the user `operator`; give another name as the first argument for more users. The page
   is on plain HTTP, so the password crosses the local network unencrypted; use one you use nowhere else.

3. **Roster:** list the people you expect to hear from in `/var/lib/reticulum/offgrid/roster.txt`, one per line: their
   LXMF address, a space, and their name. Read every minute; no restart is needed.

4. **Notices and net schedule:** send `notice` and `nets` from an operator's phone, or edit
   `/var/lib/reticulum/offgrid/notices.txt` and `nets.txt` on the host.

Edit the files as the `reticulum` user, for example `sudo -u reticulum nano /var/lib/reticulum/offgrid/roster.txt`.

### Contacts page, for operators

`http://reticulum-host.local/contacts/`, behind the password. It is rewritten every minute:

- **Roster:** each expected person, marked OK, late (nothing heard for 6 hours), overdue (24 hours) or not heard,
  with their last check-in, status, when the host last heard their announce, and the route to them. People needing
  attention come first.
- **Check-ins from others:** people who checked in but are not on the roster.
- **Heard on the network:** every announce the host has heard, by kind: people, propagation nodes, bulletin boards,
  voice rooms, phones, page nodes, git nodes and others, with names, first and last heard, and route.

"Last heard" is the last announce. Apps announce when they start and every few hours, so someone can be active
without being heard for a while; a check-in is the sure sign.

The notices page, `http://reticulum-host.local/notices/`, is public: notices, the net schedule, and how to check in.

### Privacy

The bot keeps every check-in and announce in `/var/lib/reticulum/offgrid/offgrid.db`: names, addresses, statuses and
times. Only operators see check-ins, but anyone with root on the host can read the database. To start afresh, stop
the bot, delete the database, and start it again:

```bash
sudo systemctl stop offgrid-checkin
sudo rm /var/lib/reticulum/offgrid/offgrid.db
sudo systemctl start offgrid-checkin
```

### Settings

- Runs as `reticulum`, unit `offgrid-checkin`. Its identity, `/var/lib/reticulum/offgrid/identity`, decides its
  address.
- Ansible variables: `offgrid_suite_checkin` (on or off), `offgrid_suite_checkin_name`, `offgrid_suite_operators`,
  `offgrid_suite_checkin_announce_minutes`, `offgrid_suite_late_hours`, `offgrid_suite_overdue_hours`, and
  `offgrid_suite_checkin_stamp_cost`, a proof of work senders must add to each message, against flooding; 0 for none.
