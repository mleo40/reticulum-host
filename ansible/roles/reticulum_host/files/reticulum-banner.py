"""Write this host's Reticulum addresses into the console and SSH login banners."""
import argparse
import subprocess
import time
from pathlib import Path

import RNS

POLL_SECONDS = 5


def load_identity(path):
    """
    Load an RNS identity file.

    :param path: identity file
    :return: RNS.Identity, or None if the file does not exist yet
    """
    return RNS.Identity.from_file(str(path)) if path.is_file() else None


def destination(identity, name):
    """
    Get the hex destination hash an identity serves under a name.

    :param identity: RNS.Identity or None
    :param name: full destination name, such as retibbs.bbs
    :return: hex hash, or a placeholder while the identity does not exist
    """
    if identity is None:
        return 'not created yet'
    return RNS.Destination.hash_from_name_and_identity(name, identity).hex()


def ipv4_addresses():
    """
    List this host's IPv4 addresses, without loopback.

    :return: list of address strings
    """
    output = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=False).stdout
    return [address for address in output.split() if '.' in address]


def banner(rows, network_rows):
    """
    Build the banner text.

    :param rows: list of (label, value) tuples
    :param network_rows: (label, value) tuples for what is reached over IP, shown first
    :return: banner text
    """
    rows = network_rows + rows
    width = max(len(label) for label, _ in rows)
    lines = ['Reticulum host'] + [f'  {label.ljust(width)}  {value}' for label, value in rows]
    return '\n'.join(lines) + '\n\n'


def main():
    """Wait for the identities, then write both banners."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True, help='Reticulum service data folder')
    parser.add_argument('--port', type=int, required=True, help='TCP server port, 0 when off')
    parser.add_argument('--issue', type=Path, required=True, help='console banner file')
    parser.add_argument('--ssh-banner', type=Path, default=None, help='SSH banner file')
    parser.add_argument('--wait', type=int, default=120, help='seconds to wait for identities')
    parser.add_argument('--nomadnet', action='store_true', help='the Nomad Network page node runs here')
    parser.add_argument('--propagation', action='store_true', help='the LXMF propagation node runs here')
    parser.add_argument('--http-port', type=int, default=0, help='web file sharing port, 0 when off')
    args = parser.parse_args()

    files = {'transport': args.home / 'rns/storage/transport_identity',
             'retibbs': args.home / 'retibbs/server_identity.pem',
             'rngit': args.home / 'rngit/repositories_identity',
             'partyline': args.home / 'partyline/server_identity'}
    if args.nomadnet:
        files['nomadnet'] = args.home / 'nomadnet/storage/identity'
    if args.propagation:
        files['lxmd'] = args.home / 'lxmd/identity'
    # Services create their identities on first start, and DHCP may still be running; the console banner's \\4 shows
    # the address only once an interface has one
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        if all(path.is_file() for path in files.values()) and (not args.port or ipv4_addresses()):
            break
        time.sleep(POLL_SECONDS)

    transport = load_identity(files['transport'])
    retibbs = load_identity(files['retibbs'])
    rngit = load_identity(files['rngit'])
    partyline = load_identity(files['partyline'])
    rows = [('Transport identity', transport.hash.hex() if transport else 'not created yet'),
            ('RetiBBS', destination(retibbs, 'retibbs.bbs')),
            ('Partyline voice', destination(partyline, 'lxst.room')),
            ('Git repositories', destination(rngit, 'git.repositories')),
            ('Git node pages', destination(rngit, 'nomadnetwork.node'))]
    # Also shown when the page node was turned on by hand and has made its identity
    nomadnet_path = args.home / 'nomadnet/storage/identity'
    if args.nomadnet or nomadnet_path.is_file():
        rows.append(('Nomad Network pages', destination(load_identity(nomadnet_path), 'nomadnetwork.node')))
    if args.propagation:
        rows.append(('LXMF propagation', destination(load_identity(files['lxmd']), 'lxmf.propagation')))

    # The console banner uses agetty's \\4, the current IPv4 address; the SSH banner lists them when written
    addresses = ipv4_addresses()
    console_rows = [('TCP interface', f'\\4:{args.port}' if args.port else 'off')]
    ssh_rows = [('TCP interface', (', '.join(f'{a}:{args.port}' for a in addresses) or 'no address') if args.port else 'off')]
    if args.http_port:
        suffix = '' if args.http_port == 80 else f':{args.http_port}'
        console_rows.append(('Web files', f'http://\\4{suffix}/'))
        ssh_rows.append(('Web files', ', '.join(f'http://{a}{suffix}/' for a in addresses) or 'no address'))
    args.issue.write_text(banner(rows, console_rows))
    if args.ssh_banner:
        args.ssh_banner.write_text(banner(rows, ssh_rows))


if __name__ == '__main__':
    main()
