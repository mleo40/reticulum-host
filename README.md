# reticulum-host

Turns a Debian machine or a 64-bit Raspberry Pi into a ready Reticulum community host: one always-on box that gives
a club, an event or an emergency net messaging that waits for people who are offline, a bulletin board, voice rooms,
git repositories and file sharing. It works over Wi-Fi, wired networks, the internet or radio, with no central
server, and needs no internet once it is set up.

Reticulum is an encrypted mesh networking stack; people use it with apps such as Sideband, MeshChat, the RetiBBS
client and Partyline. The host gives those apps something to connect to, and routes between everyone who reaches it.

There are three ways to get a host, all built from the same Ansible role:

- **Ansible role** (`ansible/`): set up a Debian machine you already have.
- **ISO** (`live-build/`): boot a host from a USB stick, or install it to disk.
- **Raspberry Pi image** (`pi/`): write it to an SD card.

The ISO and the Pi image each come in two types: the **standard** Reticulum host, and the **off-grid** image, which
adds the programs in the [off-grid suite](docs/offgrid-suite.md), from a second Ansible role: a Kiwix offline library,
and a check-in bot with a contacts page that shows operators who has checked in and everyone heard on the network.

Every machine creates its own Reticulum identities, so its own addresses, and SSH host keys on first boot. The
images hold no per-machine identifiers; their builds fail if any remain.

## What a host provides

| Service | For users | Unit | On by default |
|---|---|---|---|
| Reticulum node | Joins the local network, TCP port 4242 and any radios, and routes between them | `rnsd` | yes |
| LXMF propagation node | Holds messages for people who are offline | `lxmd` | yes |
| RetiBBS | Bulletin board and chat rooms, with a short theme for slow links | `retibbs` | yes |
| Partyline | Voice rooms: Lobby (Opus 8 kbps) and Low bandwidth (Codec2 1200 bps) | `partyline` | yes |
| Reticulum git node | Git repositories, cloned with `git clone rns://...` | `rngit` | yes |
| Nomad Network page node | Text pages, with a starter front page | `nomadnet` | no |
| Web page | The host's addresses and their QR codes, the user guide, and shared files | `nginx` | yes |
| `.local` name | Opens the web page at `http://reticulum-host.local/` without knowing the IP address | `avahi-daemon` | yes |
| Health page | Services, Reticulum interfaces, time, GPS, power and disks at a glance | `reticulum-health.timer` | yes |
| GPS and time | Keeps the clock right from a GPS receiver without internet, and serves it to the network | `gpsd`, `chrony` | yes |
| Firewall | Lets in only SSH, Reticulum, the web page, the `.local` name and time | `reticulum-firewall` | yes |

Every item is in both the ISO and the Pi image. The Ansible role installs the same set, but on a machine you already
have it leaves the web and health pages, the `.local` name, GPS and time, and the firewall off, so they do not clash
with what the machine already runs; see
[Set up a machine with the Ansible role](#set-up-a-machine-with-the-ansible-role).

The console and SSH login banners list the host's addresses, which the operator hands out to users. The host also
has `git`, `ansible` and the Reticulum command line tools. Versions are pinned: rns 1.6.1, lxmf 1.3.1, nomadnet 1.5.0,
Partyline 1.0.5 and RetiBBS at a fixed commit; the full list is in
`ansible/roles/reticulum_host/files/requirements.txt`.

## Documentation

- [User guide](ansible/roles/reticulum_host/files/user-guide.md): for people who connect to a host; which app to use
  for each service. It is also the host's web page, below the host's addresses. Short
  enough to print for an event.
- [Off-grid suite](docs/offgrid-suite.md): the off-grid images' extra programs, and how to prepare the drive for the
  offline library.
- [Host guide](docs/host-guide.md): for operators; each program's user, unit, settings and admin tasks, the firewall
  and troubleshooting.
- [Back up and restore RetiBBS](docs/retibbs-backup.md): keep a standby copy of a bulletin board at another site.

## Compatibility

- Debian 13 (trixie) or newer, and systems based on it such as 64-bit Raspberry Pi OS. Tested on Debian 13 amd64.
- 64-bit only (amd64, arm64): some pinned Python packages have no 32-bit ARM wheels.
- Raspberry Pi 3, 4, 5 and Zero 2 W, with an SD card of at least 8 GB.

## Requirements

- Role: Ansible on the control machine; on the target, Debian with SSH, sudo and internet access.
- ISO and Pi image builds: a Debian 13 amd64 netinst ISO, libvirt with `virt-install` and the `default` network,
  your user in the `libvirt` group, an SSH key pair, `git`, `curl` and internet access. The builds run in a small
  build VM, so the build machine needs no other tools.

## Set up a machine with the Ansible role

Get the code:

```bash
git clone https://github.com/mleo40/reticulum-host.git
cd reticulum-host/ansible
```

On another machine:

```bash
cp inventory.example.yml inventory.yml
ansible-playbook -i inventory.yml site.yml -K
```

On the machine you are on:

```bash
ansible-playbook -i localhost, -c local site.yml -K
```

Running it again updates the host to the versions pinned here. Settings are in
`ansible/roles/reticulum_host/defaults/main.yml`; override them per host in the inventory. For example, a BBS name,
a Partyline operator and a LoRa radio:

```yaml
reticulum_host_bbs_name: Club BBS
reticulum_host_partyline_ops: [0123456789abcdef0123456789abcdef]
reticulum_host_extra_interfaces:
  - name: RNode LoRa
    options: {type: RNodeInterface, enabled: "Yes", port: /dev/ttyUSB0, frequency: 915000000,
              bandwidth: 125000, txpower: 7, spreadingfactor: 8, codingrate: 5}
```

The role leaves the web and health pages, the `.local` name, GPS and time, and the firewall off, so they do not clash
with a machine's existing setup. To set a machine up like the images, pass the settings they are built with:

```bash
ansible-playbook -i localhost, -c local site.yml -K -e @image.yml
```

For the off-grid suite as well, run `offgrid.yml` instead of `site.yml`; see [Off-grid suite](docs/offgrid-suite.md).

The `ansible` folder stands alone; copy it anywhere.

## Set up a host from the ISO

### Build the ISO

The build copies your checkout into the build VM, so it builds exactly what you have, including uncommitted changes.

1. Get the code and the Debian netinst ISO:

   ```bash
   git clone https://github.com/mleo40/reticulum-host.git
   cd reticulum-host
   ```

   Download `debian-13.x.y-amd64-netinst.iso` from <https://www.debian.org/CD/netinst/>.

2. Create the build VM once. It is a minimal Debian 13 with live-build, logs in with the public keys in
   `~/.ssh/*.pub` (set `SSH_PUBKEYS` to choose others) and has no password. The install is unattended and takes
   10 to 15 minutes; leave its console alone while it runs:

   ```bash
   ./vm/build-vm.sh ~/Downloads/debian-13.7.0-amd64-netinst.iso
   ```

3. Start the VM if it is off:

   ```bash
   virsh -c qemu:///system start reticulum-build
   ```

4. Build. This takes 20 to 40 minutes. For the off-grid image, add `offgrid`:

   ```bash
   ./build-iso.sh
   ./build-iso.sh offgrid
   ```

The ISO is copied to `build/reticulum-host-amd64.hybrid.iso`, or `build/reticulum-offgrid-amd64.hybrid.iso`. Write it
to a USB stick with `dd` or any image writer.

To build without the VM on any Debian 13 machine, install `live-build` and run
`sudo live-build/build.sh <output-dir> [host|offgrid]` from the checkout.

### Use the ISO

- **Live**: boot "Live system". The host runs from memory and creates new Reticulum identities, so new addresses, on
  every boot. The console logs in automatically as `rnsadmin` once the addresses are shown; its password, for
  `sudo` and other consoles, is `live`. SSH is off in live sessions, since that password is public.
- **Live with persistence**: to keep identities and data across live boots, add a partition labelled `persistence`
  to the USB stick holding a `persistence.conf` with the line `/ union`.
- **Install**: boot "Start installer". Language, keyboard, network, time zone and partitioning are answered for you
  (English, US keyboard, UTC, the whole disk); the installer asks for your name, user name and password, which disk
  when there is more than one, and before it erases the disk. It reboots when done; remove the USB stick. The
  installed host keeps its identities, runs SSH, and boots with Secure Boot on or off.

## Set up a host from the Raspberry Pi image

### Build the Pi image

The build starts from Raspberry Pi OS Lite (64-bit), pinned in `build-pi-image.sh`, and runs the same Ansible role
inside it. It uses the build VM from the ISO steps and runs the Pi's arm64 programs through emulation; it takes about
20 minutes.

1. Create and start the build VM as in [Build the ISO](#build-the-iso), steps 1 to 3.

2. Build. This downloads Raspberry Pi OS Lite (about 525 MB) to `build/` the first time and checks its SHA-256. For
   the off-grid image, add `offgrid`:

   ```bash
   ./build-pi-image.sh
   ./build-pi-image.sh offgrid
   ```

The image is copied to `build/reticulum-host-pi-arm64.img.xz`, or `build/reticulum-offgrid-pi-arm64.img.xz`. To
build without the VM on any Debian 13 machine, run
`sudo pi/build-image.sh <raspios-lite-arm64.img.xz> <output-dir> [host|offgrid]` from the checkout.

### Use the Pi image

Write the image to an SD card with Raspberry Pi Imager ("Use custom"), and set the user name,
password, SSH and Wi-Fi in its settings. Without them, the first boot asks for a user on the console and SSH stays
off. On first boot the card's file system grows to fill it, and the host creates its own SSH host keys and
Reticulum identities.

## After setup

People on the host's network open `http://reticulum-host.local/` for its addresses and the user guide; no screen or
SSH is needed. The login banner shows the same addresses. A new
bulletin board has no admin yet; see [Make the first admin](docs/host-guide.md#make-the-first-admin) in the host
guide.

## Update pinned versions

Edit `ansible/roles/reticulum_host/files/requirements.txt` or `reticulum_host_retibbs_version`, rerun the role on
existing hosts, and rebuild the ISO and the Pi image.

## Revision history

- 0.9.0: A page of QR codes for the host's addresses, which also prints as an address card, at `/card.html`; one
  notice per line and the net schedule as a table, with commands to add and remove each; a clearer contacts page
  with a summary, names from RetiBBS and Partyline announces, and "on this host" for local programs; a repeater
  list from a CHIRP or RepeaterBook export, nearest first by GPS; "Git pages" named apart from the Nomad Network
  page node, whose address shows while it runs; curl and wget
- 0.8.0: Check-in bot and operators' contacts page in the off-grid suite: check-ins, notices, net schedule, a roster
  with overdue warnings, and every announce heard
- 0.7.0: Health page; GPS and time served to the local network; off-grid images with a Kiwix offline library, from
  the new `offgrid_suite` role; image settings in `ansible/image.yml`; services start once `rnsd` is ready, which fixes
  `rnstatus` and other tools being rejected after the first boot
- 0.6.0: The web page lists the host's addresses and the user guide, at `http://reticulum-host.local/`; shared
  files move to `/files/`
- 0.5.1: User guide; README reorganised by setup method; first admin steps, SSH and the firewall moved in the host
  guide; troubleshooting
- 0.5.0: LXMF propagation node on by default, with its address in the login banner
- 0.4.0: Nomad Network page node; web file sharing and a firewall on the ISO and Pi image; the ISO's live login
  works and installed systems boot with Secure Boot on
- 0.3.0: Raspberry Pi image
- 0.2.0: Partyline voice rooms; complete ISO build steps
- 0.1.0: First version
