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


def banner(rows, tcp_line):
    """
    Build the banner text.

    :param rows: list of (label, value) tuples
    :param tcp_line: line describing the TCP interface
    :return: banner text
    """
    width = max(len(label) for label, _ in rows)
    lines = ['Reticulum host', tcp_line] + [f'  {label.ljust(width)}  {value}' for label, value in rows]
    return '\n'.join(lines) + '\n\n'


def main():
    """Wait for the identities, then write both banners."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True, help='Reticulum service data folder')
    parser.add_argument('--port', type=int, required=True, help='TCP server port, 0 when off')
    parser.add_argument('--issue', type=Path, required=True, help='console banner file')
    parser.add_argument('--ssh-banner', type=Path, default=None, help='SSH banner file')
    parser.add_argument('--wait', type=int, default=120, help='seconds to wait for identities')
    args = parser.parse_args()

    files = {'transport': args.home / 'rns/storage/transport_identity',
             'retibbs': args.home / 'retibbs/server_identity.pem',
             'rngit': args.home / 'rngit/repositories_identity'}
    # Services create their identities on first start
    deadline = time.monotonic() + args.wait
    while not all(path.is_file() for path in files.values()) and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)

    transport = load_identity(files['transport'])
    retibbs = load_identity(files['retibbs'])
    rngit = load_identity(files['rngit'])
    rows = [('Transport identity', transport.hash.hex() if transport else 'not created yet'),
            ('RetiBBS', destination(retibbs, 'retibbs.bbs')),
            ('Git repositories', destination(rngit, 'git.repositories')),
            ('Git node pages', destination(rngit, 'nomadnetwork.node'))]

    if args.port:
        args.issue.write_text(banner(rows, f'  TCP interface       \\4:{args.port}'))
        addresses = ', '.join(f'{address}:{args.port}' for address in ipv4_addresses()) or 'no address'
        ssh_tcp = f'  TCP interface       {addresses}'
    else:
        args.issue.write_text(banner(rows, '  TCP interface       off'))
        ssh_tcp = '  TCP interface       off'
    if args.ssh_banner:
        args.ssh_banner.write_text(banner(rows, ssh_tcp))


if __name__ == '__main__':
    main()
