# Reticulum host guide

How to run a host built from the ISO, the Raspberry Pi image or the Ansible role: what each program is, which user it
runs as, how to start and stop it, and where its settings live.

## Log in

| Built from | User | SSH |
|---|---|---|
| ISO, live session | `rnsadmin`, password `live` | Off |
| ISO, installed to disk | The user you created in the installer | On |
| Raspberry Pi image | The user you set in Raspberry Pi Imager, or created at first boot | On if you enabled it in Imager |
| Ansible role | Your existing users | Unchanged |

The login banner, shown before you log in on the console and over SSH, lists the host's Reticulum addresses.

Your login user is an admin user with `sudo`. The services do not run as that user.

## How the host is laid out

All services run as the system user `reticulum`, which has no login shell and is in the `dialout` group so it can use
serial radios such as an RNode.

| Program | systemd unit | Starts at boot | Settings | Data |
|---|---|---|---|---|
| Reticulum | `rnsd` | Yes | `/var/lib/reticulum/rns/config` | `/var/lib/reticulum/rns/storage/` |
| RetiBBS | `retibbs` | Yes | `/var/lib/reticulum/retibbs/server_config.json`, `themes/` | `/var/lib/reticulum/retibbs/` |
| Partyline | `partyline` | Yes | `/var/lib/reticulum/partyline/server.json` | `/var/lib/reticulum/partyline/` |
| Reticulum git node | `rngit` | Yes | `/var/lib/reticulum/rngit/config` | `/var/lib/reticulum/rngit/` |
| LXMF router | `lxmd` | No | `/var/lib/reticulum/lxmd/config` | `/var/lib/reticulum/lxmd/` |
| Login banner | `reticulum-banner` | Yes, runs once | Ansible variables | `/etc/issue.d/reticulum.issue`, `/etc/ssh/reticulum-banner` |

Other locations:

- `/opt/reticulum/venv`: the Python environment with Reticulum, LXMF, Nomad Network and Partyline. Their commands are
  linked into `/usr/local/bin`.
- `/opt/reticulum/RetiBBS`: the RetiBBS program.
- `/opt/reticulum-host/ansible`: on the ISO and the Pi image, a copy of the Ansible role the host was built with.
- `/etc/systemd/system/<unit>.service`: the unit files.

Every service except `rnsd` needs `rnsd` running. Stopping `rnsd` stops them too, and starting any of them starts
`rnsd` first.

## Start, stop and check a service

The commands are the same for every unit. For example, for RetiBBS:

```bash
sudo systemctl status retibbs      # running or not, and the last log lines
sudo systemctl restart retibbs     # after changing its settings
sudo systemctl stop retibbs
sudo systemctl start retibbs
sudo systemctl disable --now retibbs   # stop it and keep it off after reboots
sudo systemctl enable --now retibbs    # start it and at every boot
sudo journalctl -u retibbs -f      # follow its log
```

A service that crashes restarts by itself after 5 to 10 seconds.

## Changing settings

There are two ways. Pick one per host and stay with it.

**Edit the files on the host.** Simplest for a host built from the ISO or the Pi image. Edit the settings file listed
for the program, then restart its unit. Edit as root, for example `sudo nano /var/lib/reticulum/rns/config`, and
keep the files owned by `reticulum`.

**Set Ansible variables and rerun the role.** Best when you manage several hosts, or set the host up with the role.
The variables are in `ansible/roles/reticulum_host/defaults/main.yml`; override them in your inventory. On the ISO or
Pi image, you can rerun the copy on the host itself; it needs internet access:

```bash
cd /opt/reticulum-host/ansible
sudo ansible-playbook -i localhost, -c local site.yml
```

Running the role writes these files again and undoes hand edits to them:

- `/var/lib/reticulum/rns/config`
- `/var/lib/reticulum/retibbs/server_config.json` and the `default` and `radio` themes
- `/var/lib/reticulum/partyline/server.json`
- The unit files in `/etc/systemd/system`

It never touches the RetiBBS databases, the rngit and lxmd configs, or any identity.

## Reticulum (rnsd)

The shared Reticulum instance. Every other program on the host, and any Reticulum program you run yourself, connects
through it.

- Runs as `reticulum`, unit `rnsd`.
- Settings: `/var/lib/reticulum/rns/config`. Ansible variables: `reticulum_host_enable_transport`,
  `reticulum_host_tcp_server`, `reticulum_host_tcp_port`, `reticulum_host_loglevel`,
  `reticulum_host_extra_interfaces`.
- Identity: `/var/lib/reticulum/rns/storage/transport_identity`, created on first start.

Out of the box it routes for other nodes (transport on), finds peers on the local network with AutoInterface (UDP
multicast), and accepts Reticulum over TCP on port 4242.

To add an interface, such as an RNode radio, add a section under `[interfaces]` and restart `rnsd`. For example:

```ini
  [[RNode LoRa]]
    type = RNodeInterface
    enabled = Yes
    port = /dev/ttyUSB0
    frequency = 915000000
    bandwidth = 125000
    txpower = 7
    spreadingfactor = 8
    codingrate = 5
```

To check the network, as your own user:

```bash
rnstatus
rnpath <destination hash>
```

These connect to the shared instance. The first run creates a `~/.reticulum` folder for your user; that is normal.

## RetiBBS

A bulletin board with message boards and chat rooms. Clients connect to its address in the login banner.

- Runs as `reticulum`, unit `retibbs`.
- Settings: `/var/lib/reticulum/retibbs/server_config.json`. Ansible variables: `reticulum_host_bbs_name`,
  `reticulum_host_bbs_announce_interval` (seconds), `reticulum_host_bbs_theme`.
- Text shown to users: `/var/lib/reticulum/retibbs/themes/<theme>/`. `welcome_message.txt` is the welcome message,
  `header.txt` and the `*_menu.txt` files are the menus. The host uses the short `radio` theme by default. RetiBBS
  reads the theme at start, so restart `retibbs` after editing it.
- Data: `users.db` (accounts and admin flags) and `boards.db` (boards and posts) in the same folder.
- Identity: `server_identity.pem`, which decides the BBS address.

Admin tasks are done in its databases with `sqlite3`:

- Make the first admin: see [Make the first RetiBBS admin](../README.md#make-the-first-retibbs-admin). Later admins
  can be made from a client.
- Delete a post: RetiBBS has no command for it. Back up `boards.db`, then delete the post and its replies, using the
  post number shown in the client:

  ```bash
  sudo sqlite3 /var/lib/reticulum/retibbs/boards.db \
    "DELETE FROM read_messages WHERE message_id IN (SELECT id FROM messages WHERE id=<n> OR parent_id=<n>);
     DELETE FROM messages WHERE id=<n> OR parent_id=<n>; SELECT changes();"
  ```

- Back up and restore: see [Back up and restore RetiBBS](retibbs-backup.md).

## Partyline

Voice rooms. Clients connect to its address in the login banner with the Partyline client.

- Runs as `reticulum`, unit `partyline`.
- Settings: `/var/lib/reticulum/partyline/server.json`: server name, welcome text (`motd`), default codec
  (`profile`), the most users on the server at once (`max_members`), operators (`ops`) and rooms. Ansible variables:
  `reticulum_host_partyline_name`, `reticulum_host_partyline_motd`, `reticulum_host_partyline_profile`,
  `reticulum_host_partyline_max_members`, `reticulum_host_partyline_ops`, `reticulum_host_partyline_rooms`.
- State: `operators.txt` and `banned.txt` in the same folder.
- Identity: `server_identity`, which decides the server address.

The default rooms are Lobby (Opus, 8 kbps) and Low bandwidth (Codec2, 1200 bps). Each room can have its own codec,
password, allow list or push to talk mode; see the [Partyline README](https://github.com/RFnexus/partyline) for the
room options. Restart `partyline` after editing.

Operators can kick, mute, ban and move users from a client. Add an operator by their identity hash in `ops`. If you
manage the host with Ansible, list operators in `reticulum_host_partyline_ops`; ones promoted from a client are lost
the next time the role runs.

Its usage counters go to the log once an hour: `sudo journalctl -u partyline`.

## Reticulum git node (rngit)

Serves git repositories over Reticulum, so others can `git clone rns://...`.

- Runs as `reticulum`, unit `rngit`.
- Settings: `/var/lib/reticulum/rngit/config`. Not managed by Ansible.
- Identity: `repositories_identity`, which decides the address in the login banner.

It starts with rngit's own sample settings, which point at folders that do not exist, so it serves nothing until you
set it up:

1. Create a folder for repositories and a bare repository in it:

   ```bash
   sudo -u reticulum mkdir -p /var/lib/reticulum/rngit/public
   sudo -u reticulum git init --bare /var/lib/reticulum/rngit/public/myproject.git
   ```

2. In `/var/lib/reticulum/rngit/config`, point a group at that folder under `[repositories]`, remove the sample
   groups you do not use, and set who may do what under `[access]`:

   ```ini
   [repositories]
   public = /var/lib/reticulum/rngit/public

   [access]
   public = r:all, rw:<your identity hash>
   ```

   `r` is read, `w` write, `c` create, `adm` admin; `all` means anyone. The comments in the file list every option,
   including a Nomad Network page server for browsing repositories (`serve_nomadnet`).

3. Restart: `sudo systemctl restart rngit`.

Your identity hash is the "Git Peer Identity" that `rngit -p` prints on the computer you push from.

## LXMF router (lxmd)

A store and forward router for LXMF messages, such as those from Sideband, MeshChat or NomadNet. Installed but off.

- Runs as `reticulum`, unit `lxmd`.
- Settings: `/var/lib/reticulum/lxmd/config`, created the first time it starts. Not managed by Ansible.

To turn it on:

```bash
sudo systemctl enable --now lxmd
```

To make it a propagation node, which holds messages for others while they are offline, set
`enable_node = yes` in the `[propagation]` section of its settings and restart it. To keep it on when you manage the host with Ansible, add `lxmd`
to `reticulum_host_services`.

## Nomad Network

A text client for Nomad Network pages and messages. It is not a service; run it as your own user:

```bash
nomadnet
```

It connects through the shared instance and keeps its settings in `~/.nomadnetwork`.

## Login banner

The `reticulum-banner` unit runs once at each boot, after the services have started, and writes the host's
addresses into the console and SSH login banners.

Run it again after the addresses change, for example after restoring a RetiBBS identity:

```bash
sudo systemctl restart reticulum-banner
```

Ansible variables: `reticulum_host_banner` (both banners) and `reticulum_host_ssh_banner` (the SSH one).

## SSH

- On an installed host, SSH is on. Host keys are created on first boot by the `ssh-hostkeys` unit.
- In the ISO's live session, SSH is off because the live password is public. To turn it on for one session, set a
  new password with `passwd`, then `sudo systemctl start ssh`.
- On the Raspberry Pi image, SSH follows the setting you chose in Raspberry Pi Imager. To turn it on later:
  `sudo systemctl enable --now ssh`.

## Network ports

| Port | Used by |
|---|---|
| TCP 4242 | Reticulum TCP server, for clients and other nodes over IP |
| UDP 29716, 42671 | Reticulum AutoInterface on the local network |
| TCP 22 | SSH |

The host has no firewall set up. If you add one, open these ports.
