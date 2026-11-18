# Back up and restore RetiBBS

RetiBBS has no replication of its own. For redundancy, back it up on the main host, copy the backup to a standby
host built the same way, and restore it there when the main host is lost. These steps are manual.

## What RetiBBS keeps

Everything is in `/var/lib/reticulum/retibbs`:

| File | Holds | Back up |
|---|---|---|
| `users.db` | Accounts: each user's identity hash, display name and admin flag | Yes |
| `boards.db` | Boards, messages, and what each user has read or watches | Yes |
| `server_identity.pem` | The server's private key, which decides its address | Only for same address failover, see below |
| `lxmf_storage/` | Queued LXMF notifications for this host | No, rebuilt on start |
| `server_config.json`, `themes/` | Settings | No, the playbook writes them |

Chat rooms are held in memory and are not saved.

Accounts carry over to another server because they are keyed by each user's own identity, not by the server's.

## Back up

On the main host. `sqlite3` makes a consistent copy while RetiBBS keeps running.

```bash
stamp=$(date +%Y%m%d-%H%M)
mkdir -p ~/retibbs-$stamp
```

```bash
sudo sqlite3 /var/lib/reticulum/retibbs/users.db ".backup $HOME/retibbs-$stamp/users.db"
sudo sqlite3 /var/lib/reticulum/retibbs/boards.db ".backup $HOME/retibbs-$stamp/boards.db"
```

Check both copies; each should print `ok`:

```bash
sudo sqlite3 ~/retibbs-$stamp/users.db "PRAGMA integrity_check"
sudo sqlite3 ~/retibbs-$stamp/boards.db "PRAGMA integrity_check"
```

Pack them:

```bash
sudo tar -C ~ -czf ~/retibbs-$stamp.tar.gz retibbs-$stamp
sudo chown "$USER": ~/retibbs-$stamp.tar.gz
```

Keep a few older backups; a copy taken after something went wrong is no help.

## Copy the backup to the standby host

Over IP, `scp` is simplest:

```bash
scp ~/retibbs-$stamp.tar.gz rnsadmin@standby:
```

Over Reticulum alone, for example a radio link with no IP between the sites, use `rncp`:

1. On the main host, print the identity `rncp` sends with, and note the identity hash:

   ```bash
   rncp -p
   ```

2. On the standby host, listen for files from that identity only. This prints the standby's `rncp` destination:

   ```bash
   mkdir -p ~/retibbs-incoming
   rncp -l -s ~/retibbs-incoming -a <main identity hash>
   ```

3. On the main host, send the backup to that destination:

   ```bash
   rncp ~/retibbs-<stamp>.tar.gz <standby destination>
   ```

4. Stop the listener on the standby with Ctrl+C.

Over slow radio links the backup grows with the boards; check its size with `ls -lh` before sending.

## Restore on the standby host

The standby is a host built from the ISO or the Ansible role. It runs its own RetiBBS with its own address.

1. Unpack the backup:

   ```bash
   tar -C ~ -xzf ~/retibbs-<stamp>.tar.gz
   ```

2. Stop RetiBBS, put the databases in place, and give them to the service user:

   ```bash
   sudo systemctl stop retibbs
   sudo install -o reticulum -g reticulum -m 0640 ~/retibbs-<stamp>/users.db ~/retibbs-<stamp>/boards.db \
     /var/lib/reticulum/retibbs/
   sudo systemctl start retibbs
   ```

3. Check that the accounts arrived:

   ```bash
   sudo sqlite3 /var/lib/reticulum/retibbs/users.db "SELECT name, is_admin FROM users"
   ```

4. Tell users the standby's RetiBBS address, shown in its login banner. They connect to it as a new server; their
   names and admin rights are already there.

## Same address failover

Clients can keep using the old address if the standby takes over the main server's identity. This copies a private
key between machines, so:

- Do it only when the main host is down and will stay down. Two servers running with the same identity confuse
  routing on the network.
- Treat `server_identity.pem` as a secret: copy it directly, never leave copies lying around.
- The main host must not start RetiBBS again until the identity is moved back or replaced.

Steps, in addition to the restore above:

1. While the main host still works, take a copy of its identity with the backup:

   ```bash
   sudo install -m 0600 -o "$USER" /var/lib/reticulum/retibbs/server_identity.pem ~/retibbs-<stamp>/
   ```

2. On the standby, with RetiBBS stopped, put it in place before starting RetiBBS:

   ```bash
   sudo install -o reticulum -g reticulum -m 0600 ~/retibbs-<stamp>/server_identity.pem /var/lib/reticulum/retibbs/
   ```

3. Refresh the login banner so it shows the address now in use:

   ```bash
   sudo systemctl restart reticulum-banner
   ```

## Moving back to the main host

Posts made on the standby exist only there. When the main host returns, back up the standby and restore that backup
on the main host with the same steps. Nothing merges two copies; the restored one replaces the other.
