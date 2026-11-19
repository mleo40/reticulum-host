# Off-grid suite

The off-grid images are the Reticulum host with more programs for running without the internet, from the
`offgrid_suite` Ansible role. Everything in the [host guide](host-guide.md) applies to them too.

| Program | What it does | Unit | Where |
|---|---|---|---|
| Kiwix | Offline library: Wikipedia, medical, repair and survival guides, and more | `kiwix` | `http://reticulum-host.local/library/` |

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
