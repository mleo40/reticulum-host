# reticulum-host

Sets up a Debian machine as a Reticulum host: a shared Reticulum node, a RetiBBS bulletin board, Partyline voice rooms
and a Reticulum git node, each running as a service.

There are two ways to use it:

- **Ansible role** (`ansible/`): apply it to a Debian machine you already have.
- **Live ISO** (`live-build/`): boot a ready host from USB, or install it to disk. It is built with live-build in a
  minimal Debian VM, by running the same Ansible role.

Every machine creates its own Reticulum identities and SSH host keys on first boot. The ISO build removes all
per-machine identifiers from the image and fails if any remain.

## What a host gets

- `rns` 1.6.1 in a venv at `/opt/reticulum/venv`, with its commands linked into `/usr/local/bin`: `rnsd`,
  `rnstatus`, `rnpath`, `rnprobe`, `rncp`, `rnx`, `rnid`, `rnodeconf`, `rnsh`, `rnpkg`, and the Reticulum git tools
  `rngit`, `rngcs` and `git-remote-rns` (so `git clone rns://...` works)
- `lxmf` 1.3.1 (`lxmd`) and `nomadnet` 1.5.0
- RetiBBS at a pinned commit in `/opt/reticulum/RetiBBS`, with a short "radio" theme for low bandwidth links
- Partyline 1.0.5 (`partyline-server`, `partyline-client`) with two rooms: Lobby (Opus 8 kbps) and Low bandwidth
  (Codec2 1200 bps)
- `git` and `ansible`, so the host can configure other machines the same way
- The host's Reticulum addresses (transport identity, RetiBBS, Partyline, rngit) and TCP address in the console login
  banner and the SSH login banner, written at boot once the services have created their identities
- Services running as the `reticulum` user, with data in `/var/lib/reticulum`:

  | Service | What it does | Enabled |
  |---|---|---|
  | `rnsd` | Shared Reticulum instance, AutoInterface plus TCP server on port 4242 | yes |
  | `retibbs` | RetiBBS server | yes |
  | `partyline` | Partyline voice room server | yes |
  | `rngit` | Reticulum git repository node | yes |
  | `lxmd` | LXMF router and propagation node | no |

## Compatibility

- Debian 13 (trixie) or newer, and systems based on it such as 64-bit Raspberry Pi OS. Tested on Debian 13 amd64.
- 64-bit only (amd64, arm64): some pinned Python packages have no 32-bit ARM wheels.
- Python packages are pinned in `ansible/roles/reticulum_host/files/requirements.txt`.

## Requirements

- Role: Ansible on the control machine; on the target, Debian with SSH, sudo and internet access
- ISO: a Debian 13 amd64 netinst ISO, libvirt with `virt-install` and the `default` network, your user in the
  `libvirt` group, an SSH key pair, `git`, internet access

## Configure a machine with the Ansible role

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

The playbook owns the Partyline config, so operators promoted from a client are lost on the next run; list them in
`reticulum_host_partyline_ops` instead.

The `ansible` folder stands alone; copy it anywhere.

## Build the ISO

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

4. Build. This takes 20 to 40 minutes:

   ```bash
   ./build-iso.sh
   ```

The ISO is copied to `build/reticulum-host-amd64.hybrid.iso`. Write it to a USB stick with `dd` or any image writer.

To build without the VM on any Debian 13 machine, install `live-build` and run `sudo live-build/build.sh` from the
checkout.

## Use the ISO

- **Live**: boot "Live system". The host runs from memory and creates new Reticulum identities, so new addresses, on
  every boot. Log in on the console as `rnsadmin`, password `live`. SSH is off in live sessions, since that password
  is public.
- **Live with persistence**: to keep identities and data across live boots, add a partition labelled `persistence`
  to the USB stick holding a `persistence.conf` with the line `/ union`.
- **Install**: boot "Install" for the Debian installer, which asks for the disk, user and password. The installed
  host keeps its identities and runs SSH.

## Use a host

The login banner lists the addresses clients connect to. To check the network:

```bash
rnstatus
```

To see a service's log, for example Partyline's:

```bash
sudo journalctl -u partyline
```

### Make the first RetiBBS admin

A new RetiBBS server has no admin, and only admins can create boards. RetiBBS has no command for the first one, so set
it in its user database:

1. Connect to the BBS once from a client and pick a display name. RetiBBS adds your account on first connect.

2. On the host, list the accounts and find your identity hash (32 hex characters) by your name:

   ```bash
   sudo sqlite3 /var/lib/reticulum/retibbs/users.db "SELECT hash_hex, name, is_admin FROM users;"
   ```

3. Make that account admin. It prints `1` when a row was updated, `0` when the hash did not match:

   ```bash
   sudo sqlite3 /var/lib/reticulum/retibbs/users.db \
     "UPDATE users SET is_admin=1 WHERE hash_hex='<your hash>'; SELECT changes();"
   ```

4. In the client, check your account again. No restart is needed.

Use the full path: `sqlite3 users.db` in another folder creates a new, empty database there.

### Standby copy

To keep a standby copy of a RetiBBS server at another site, see [Back up and restore RetiBBS](docs/retibbs-backup.md).

## Update pinned versions

Edit `ansible/roles/reticulum_host/files/requirements.txt` or `reticulum_host_retibbs_version`, rerun the playbook on
existing hosts, and rebuild the ISO.

## Revision history

- 0.2.0: Partyline voice rooms; complete ISO build steps
- 0.1.0: First version
