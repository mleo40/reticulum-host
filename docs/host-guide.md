# Reticulum host guide

How to run a host built from the ISO, the Raspberry Pi image or the Ansible role: what each program is, which user it
runs as, how to start and stop it, and where its settings live. For the people who connect to the host, see the
[user guide](../ansible/roles/reticulum_host/files/user-guide.md), which is also the host's web page.

## Log in

| Built from | User | SSH |
|---|---|---|
| ISO, live session | `rnsadmin`, logged in automatically; password `live` | Off |
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
| LXMF propagation node | `lxmd` | Yes | `/var/lib/reticulum/lxmd/config` | `/var/lib/reticulum/lxmd/storage/` |
| Nomad Network page node | `nomadnet` | No | `/var/lib/reticulum/nomadnet/config` | `/var/lib/reticulum/nomadnet/storage/` |
| Web page and file sharing | `nginx` | Yes | `/etc/nginx/sites-available/reticulum-files` | `/srv/reticulum-host/` |
| `.local` name | `avahi-daemon` | Yes | `/etc/avahi/` | |
| Firewall | `reticulum-firewall` | Yes | `/etc/reticulum-host/firewall.nft` | |
| Login banner | `reticulum-banner` | Yes, runs once | Ansible variables | `/etc/issue.d/reticulum.issue`, `/etc/ssh/reticulum-banner` |

The ISO and the Pi image are set up the same way. On a machine set up with the Ansible role, the web page, the
`.local` name and the firewall are off unless you turn them on.

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
- `/var/lib/reticulum/lxmd/config`
- `/var/lib/reticulum/nomadnet/config`
- `/etc/reticulum-host/firewall.nft`, when the firewall is on
- `/etc/nginx/sites-available/reticulum-files` and `/opt/reticulum/share/user-guide.md`, when the web page is on
- `/etc/avahi/services/reticulum-host.service`, when the `.local` name is on
- The unit files in `/etc/systemd/system`

It never touches the RetiBBS databases, the rngit config, stored LXMF messages, Nomad Network pages, or any
identity. It adds a starter `index.mu` page only when there is none.

## Login banner

The `reticulum-banner` unit runs once at each boot, after the services have started, and writes the host's
addresses into the console and SSH login banners, and onto the web page.

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

## Firewall

Hosts built from the ISO or the Raspberry Pi image have a firewall (nftables, unit `reticulum-firewall`). It drops
incoming traffic except:

| Port | Used by |
|---|---|
| TCP 22 | SSH |
| TCP 4242 | Reticulum TCP server, for clients and other nodes over IP |
| TCP 80 | Web page and file sharing |
| UDP 5353 | The `.local` name (mDNS) |
| UDP 29716, 42671 | Reticulum AutoInterface on the local network |
| UDP 68, 546 | Getting an address over DHCP |
| ICMP | Ping, and IPv6 neighbour discovery |

Replies to connections the host makes are allowed, and outgoing traffic is not limited. Partyline, RetiBBS, rngit
and Nomad Network pages need no ports of their own: they all travel over Reticulum.

The rules are in `/etc/reticulum-host/firewall.nft`. To open another port, for example for a Reticulum
`UDPInterface`, add a line such as `udp dport 4243 accept` next to the others, then:

```bash
sudo nft -c -f /etc/reticulum-host/firewall.nft   # check the rules first
sudo systemctl reload reticulum-firewall
sudo nft list table inet reticulum_host           # show the rules in use
```

To turn it off: `sudo systemctl disable --now reticulum-firewall`.

With Ansible: the firewall is off by default for the role, so it does not get in the way of a firewall the machine
already has. Turn it on with `reticulum_host_firewall: true`. `reticulum_host_firewall_ssh: false` closes SSH, and
`reticulum_host_firewall_extra_ports` opens more, for example `[{proto: udp, port: 4243}]`.

The firewall is a separate nftables table. If the machine has other nftables or ufw rules, a packet must pass both.

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

- Make the first admin: see below. Later admins can be made from a client.
- Delete a post: RetiBBS has no command for it. Back up `boards.db`, then delete the post and its replies, using the
  post number shown in the client:

  ```bash
  sudo sqlite3 /var/lib/reticulum/retibbs/boards.db \
    "DELETE FROM read_messages WHERE message_id IN (SELECT id FROM messages WHERE id=<n> OR parent_id=<n>);
     DELETE FROM messages WHERE id=<n> OR parent_id=<n>; SELECT changes();"
  ```

- Back up and restore: see [Back up and restore RetiBBS](retibbs-backup.md).

### Make the first admin

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

### Run a second BBS

One host can run more than one BBS, for example one for a club and one for an event. Each has its own folder,
identity (so its own address), accounts and boards. They share the RetiBBS program and `rnsd`, so the firewall needs
no change. These steps make `retibbs2`; use another name for a third.

1. Make its folder and copy the themes:

   ```bash
   sudo install -d -o reticulum -g reticulum /var/lib/reticulum/retibbs2
   sudo cp -a /var/lib/reticulum/retibbs/themes /var/lib/reticulum/retibbs2/
   ```

2. Copy the settings and give it its own name in `server_name`:

   ```bash
   sudo install -o reticulum -g reticulum -m 644 /var/lib/reticulum/retibbs/server_config.json \
     /var/lib/reticulum/retibbs2/
   sudo nano /var/lib/reticulum/retibbs2/server_config.json
   ```

3. Make its unit from the first one, pointing at the new folder:

   ```bash
   sed -e '/Ansible managed/d' -e 's#^Description=.*#Description=RetiBBS second board#' \
     -e 's#/var/lib/reticulum/retibbs\b#/var/lib/reticulum/retibbs2#g' \
     /etc/systemd/system/retibbs.service | sudo tee /etc/systemd/system/retibbs2.service
   ```

   Check that the output names `retibbs2` in `WorkingDirectory` and `--identity-file`.

4. Start it, and start it at boot:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now retibbs2
   ```

5. Show its address, to give to users. The login banner shows only the first BBS:

   ```bash
   sudo -u reticulum rnid --config /var/lib/reticulum/rns \
     -i /var/lib/reticulum/retibbs2/server_identity.pem -H retibbs.bbs
   ```

   The address is the `retibbs.bbs destination` it prints.

6. Make its first admin as in [Make the first admin](#make-the-first-admin), using
   `/var/lib/reticulum/retibbs2/users.db`. The same `sqlite3` admin tasks above work on its folder.

Start, stop and logs work as for the first, with `retibbs2`. Rerunning the Ansible role leaves `retibbs2` alone, but
updates the RetiBBS program both use; restart `retibbs2` afterwards. To remove it:
`sudo systemctl disable --now retibbs2`, then delete `/etc/systemd/system/retibbs2.service` and, if you no longer
want its accounts and posts, `/var/lib/reticulum/retibbs2`.

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

## LXMF propagation node (lxmd)

Holds LXMF messages, such as those from Sideband, MeshChat or NomadNet, for people who are offline, and hands them
over when they next connect. RetiBBS board alerts are LXMF messages too, so alerts to a phone that is out of range
wait here. Messages are end to end encrypted: the host cannot read them, but sees who they are for, their size and
when they arrive.

- Runs as `reticulum`, unit `lxmd`.
- Settings: `/var/lib/reticulum/lxmd/config`. Ansible variables: `reticulum_host_lxmd_propagation`,
  `reticulum_host_lxmd_node_name`, `reticulum_host_lxmd_announce_interval` (minutes),
  `reticulum_host_lxmd_storage_limit` (megabytes, 500 by default), `reticulum_host_lxmd_autopeer` and
  `reticulum_host_lxmd_autopeer_maxdepth` (hops). `lxmd --exampleconfig` lists every option.
- Stored messages: `/var/lib/reticulum/lxmd/storage/`. When the storage limit is reached, the oldest and largest
  messages are removed first.
- Identity: `/var/lib/reticulum/lxmd/identity`, which decides the node address. The login banner shows it as "LXMF
  propagation".

Clients use a propagation node only once someone picks it: in Sideband, for example, set it as the propagation node
in its settings, using the address from the login banner.

By default the node finds other propagation nodes up to 6 hops away and copies messages to and from them. That is
cheap over the internet or a local network, but can use much of a slow radio channel. On a host whose only links are
slow radio, lower `autopeer_maxdepth` or set `autopeer = no`, then restart `lxmd`. On a small SD card, consider a
lower storage limit.

To turn it off, `sudo systemctl disable --now lxmd`, or with Ansible remove `lxmd` from `reticulum_host_services`. To
keep `lxmd` running only as a plain router, set `enable_node = no`.

## Nomad Network pages

The host can serve Nomad Network pages: text pages, written in Micron, that people browse with Nomad Network or
MeshChat. The page node is installed but off.

- Runs as `reticulum`, unit `nomadnet`.
- Settings: `/var/lib/reticulum/nomadnet/config`. Ansible variables: `reticulum_host_nomadnet_node_name`,
  `reticulum_host_nomadnet_announce_interval` (minutes).
- Pages: `/var/lib/reticulum/nomadnet/storage/pages/`. `index.mu` is the front page; the host starts with a short one.
- Files to download: `/var/lib/reticulum/nomadnet/storage/files/`.
- Identity: `storage/identity`, which decides the node address. Once it exists, the login banner shows the address
  as "Nomad Network pages".

To turn it on:

```bash
sudo systemctl enable --now nomadnet
sudo systemctl restart reticulum-banner
```

To keep it on when you manage the host with Ansible, add `nomadnet` to `reticulum_host_services`.

### Where to put pages

Put pages that should always be reachable, such as a group's front page, net schedules or local information, on the
host. It is always on and announces the node to the network every 6 hours.

Pages must be readable by the `reticulum` user. Edit and add them as that user:

```bash
sudo -u reticulum nano /var/lib/reticulum/nomadnet/storage/pages/index.mu
sudo -u reticulum nano /var/lib/reticulum/nomadnet/storage/pages/schedule.mu
```

To copy pages written on another computer:

```bash
scp *.mu <you>@<host>:
sudo install -o reticulum -g reticulum -m 0640 ~/*.mu /var/lib/reticulum/nomadnet/storage/pages/
```

Edits to a page show up at once, and new pages and files within a minute; no restart is needed.

Link between pages with Micron links such as `` `[Net schedule`:/page/schedule.mu] ``, and to files with
`` `[Go-kit list`:/file/gokit.pdf] ``.

A page file marked executable (`chmod +x`) is run as a program each time it is requested, and what it prints is the
page. It runs as `reticulum`, so keep such programs short and trusted.

To limit who can see a page, put a file with `.allowed` added to its name next to it, such as
`schedule.mu.allowed`, listing the allowed identity hashes one per line.

Personal pages can also live on a person's own computer: Nomad Network serves `~/.nomadnetwork/storage/pages` when
`enable_node = yes` is set in `~/.nomadnetwork/config`. Those pages are only reachable while that computer is on.

### Browse pages from the host

`nomadnet` is also a text client. Run it as your own user; it keeps its settings in `~/.nomadnetwork`:

```bash
nomadnet
```

## Web page and file sharing

The host has a web page for the people who connect to it, so a host with no screen can still be found and used. Anyone
on its local network opens it in a browser at `http://reticulum-host.local/`, or at the host's IP address. The page
lists the host's addresses, then the [user guide](../ansible/roles/reticulum_host/files/user-guide.md). Under it,
`/files/` shares one folder as a read-only file list: no uploads, no logins, no scripts.

- Runs as nginx's own `www-data` user, unit `nginx`.
- Page: `/srv/reticulum-host/www/index.html`, written by the `reticulum-banner` unit at each boot. Do not edit it;
  edit the guide in the Ansible role instead, at `ansible/roles/reticulum_host/files/user-guide.md`, and rerun the
  role. On the host, the copy the page uses is `/opt/reticulum/share/user-guide.md`.
- Files: `/srv/reticulum-host/files/`, at `http://reticulum-host.local/files/`. Subfolders show up as folders.
- Settings: `/etc/nginx/sites-available/reticulum-files`. Ansible variables: `reticulum_host_http_files` (on or
  off), `reticulum_host_http_files_dir`, `reticulum_host_web_dir`, `reticulum_host_http_port`.

The `.local` name comes from avahi (mDNS), unit `avahi-daemon`, and follows the host name: `reticulum-host` on the ISO
and the Pi image, unless you chose another in the installer or Raspberry Pi Imager. A second host with the same name
on the network answers to `reticulum-host-2.local`; give each host its own name instead, with
`sudo hostnamectl set-hostname <name>` and a reboot. `.local` names work on most phones and computers but not all, so
the page is also reachable by IP. Ansible variable: `reticulum_host_mdns`.

The same folder is also shared over Reticulum by the Nomad Network page node, when that is on, as
`/file/shared/...`. People with only a radio link can download from it there, more slowly. Link to a shared file from
a page with `` `[Go-kit list`:/file/shared/gokit.pdf] ``.

To add files, copy them to your home folder on the host, then into the folder:

```bash
scp go-kit.pdf <you>@<host>:
sudo install -m 0644 ~/go-kit.pdf /srv/reticulum-host/files/
sudo mkdir -p /srv/reticulum-host/files/manuals
```

Files must be readable by everyone (`0644`, folders `0755`); that is what `install -m 0644` and `mkdir` give. New
files show up in the web list at once, and through the page node within a minute. Files whose names start with a dot
are never shared.

Everything in the folder is public to anyone who can reach the host. Do not put anything private in it.

To turn it off: `sudo systemctl disable --now nginx`, and for the name `sudo systemctl disable --now avahi-daemon`.
With Ansible, both are off by default for the role; turn them on with `reticulum_host_http_files: true` and
`reticulum_host_mdns: true`, which also open their ports in the firewall.

## Troubleshooting

- **A service is not running:** `sudo systemctl status <unit>` shows the last log lines, and
  `sudo journalctl -u <unit> -b` everything since boot. A settings file with a typo is the usual cause; fix it and
  restart the unit.
- **The banner says "not created yet":** that service had not started when the banner was written. Start it, then
  `sudo systemctl restart reticulum-banner`.
- **Clients cannot find the host:** check that `rnsd` is running and that `rnstatus` shows the interfaces up. Over
  TCP, check the client uses the host's IP address and port 4242, and that no other firewall blocks it. On the local
  network, guest Wi-Fi that keeps devices apart stops AutoInterface; use TCP there.
- **Clients find the host but not a service:** services announce themselves on start and then every few hours; a
  client that started earlier may need a minute, or to request the address again. `rnpath <address>` on the host
  shows whether the address is known.
- **Hand edits disappeared:** rerunning the Ansible role writes the files listed in
  [Changing settings](#changing-settings) again. Set the matching Ansible variables instead.
