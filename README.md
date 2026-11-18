# reticulum-host

Sets up a Debian machine as a Reticulum host: a shared Reticulum node, a RetiBBS bulletin board and a Reticulum git
node, each running as a service.

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
- `git` and `ansible`, so the host can configure other machines the same way
- The host's Reticulum addresses (transport identity, RetiBBS, rngit) and TCP address in the console login banner
  and the SSH login banner, written at boot once the services have created their identities
- Services running as the `reticulum` user, with data in `/var/lib/reticulum`:

  | Service | What it does | Enabled |
  |---|---|---|
  | `rnsd` | Shared Reticulum instance, AutoInterface plus TCP server on port 4242 | yes |
  | `retibbs` | RetiBBS server | yes |
  | `rngit` | Reticulum git repository node | yes |
  | `lxmd` | LXMF router and propagation node | no |

## Compatibility

- Tested on Debian 13 (trixie), amd64. The role uses only apt, pip and systemd, so Debian based systems such as
  Ubuntu and Raspberry Pi OS should work, but are not tested.
- Python packages are pinned in `ansible/roles/reticulum_host/files/requirements.txt`.

## Requirements

- Role: Ansible on the control machine; on the target, Debian with SSH, sudo and internet access
- ISO: a Debian 13 amd64 netinst ISO, libvirt with `virt-install` and the `default` network, internet access

## Configure a machine with the Ansible role

On another machine:

```bash
cd ansible
cp inventory.example.yml inventory.yml
ansible-playbook -i inventory.yml site.yml -K
```

On the machine you are on:

```bash
cd ansible
ansible-playbook -i localhost, -c local site.yml -K
```

Running it again updates the host to the versions pinned here. Settings are in
`ansible/roles/reticulum_host/defaults/main.yml`; override them per host in the inventory. For example, a BBS name and
a LoRa radio:

```yaml
reticulum_host_bbs_name: Club BBS
reticulum_host_extra_interfaces:
  - name: RNode LoRa
    options: {type: RNodeInterface, enabled: "Yes", port: /dev/ttyUSB0, frequency: 915000000,
              bandwidth: 125000, txpower: 7, spreadingfactor: 8, codingrate: 5}
```

The `ansible` folder stands alone; copy it anywhere.

## Build the ISO

1. Create the build VM, a minimal Debian 13 with live-build. It logs in with the public keys in `~/.ssh/*.pub` (set
   `SSH_PUBKEYS` to choose others) and has no password:

   ```bash
   ./vm/build-vm.sh ~/Downloads/debian-13.7.0-amd64-netinst.iso
   ```

2. Start the VM if it is off, then build:

   ```bash
   virsh -c qemu:///system start reticulum-build
   ```

   ```bash
   ./build-iso.sh
   ```

The ISO is copied to `build/reticulum-host-amd64.hybrid.iso`. Write it to a USB stick with `dd` or any image writer.

On any Debian 13 machine, `sudo live-build/build.sh` builds the ISO without the VM.

## Use the ISO

- **Live**: boot "Live system". The host runs from memory and creates new Reticulum identities, so new addresses, on
  every boot. Log in on the console as `rnsadmin`, password `live`. SSH is off in live sessions, since that password
  is public.
- **Live with persistence**: to keep identities and data across live boots, add a partition labelled `persistence`
  to the USB stick holding a `persistence.conf` with the line `/ union`.
- **Install**: boot "Install" for the Debian installer, which asks for the disk, user and password. The installed
  host keeps its identities and runs SSH.

## Use a host

```bash
rnstatus
```

```bash
sudo journalctl -u retibbs | grep 'Identity hash'
```

```bash
sudo -u reticulum rngit --config /var/lib/reticulum/rngit --rnsconfig /var/lib/reticulum/rns --print-identity
```

The RetiBBS identity hash is the address clients connect to. A new server has no admin; see the RetiBBS client
documentation for setting the first one in `/var/lib/reticulum/retibbs/users.db`.

## Update pinned versions

Edit `ansible/roles/reticulum_host/files/requirements.txt` or `reticulum_host_retibbs_version`, rerun the playbook on
existing hosts, and rebuild the ISO.

## Revision history

- 0.1.0: First version
