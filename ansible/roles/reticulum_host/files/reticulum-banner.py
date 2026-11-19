"""Write this host's Reticulum addresses into the console and SSH login banners, and its web page."""
import argparse
import html
import os
import socket
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


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reticulum host {name}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<h1>Reticulum host</h1>
<p class="when">Host name {name}. Addresses as of {when}. Tap an address to select it, then copy.</p>
<table>
{rows}
</table>
<p>{links}</p>
<hr>
{guide}
</body>
</html>
"""


def guide_html(path):
    """
    Render the user guide to HTML.

    :param path: Markdown file
    :return: HTML text, or an empty string when the file is missing
    """
    if not path or not path.is_file():
        return ''
    text = path.read_text(encoding='utf-8')
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        return f'<pre>{html.escape(text)}</pre>'
    return MarkdownIt('commonmark', {'html': False}).enable('table').render(text)


def page_links(health, folder):
    """
    List the links shown under the addresses.

    :param health: include the health page
    :param folder: folder of files holding "Label|/path", one link each, or None
    :return: list of (label, path) tuples
    """
    links = [('Shared files', '/files/')] + ([('Host health', '/health.html')] if health else [])
    if folder and folder.is_dir():
        for path in sorted(folder.iterdir()):
            label, _, target = path.read_text(encoding='utf-8').strip().partition('|')
            if label and target:
                links.append((label.strip(), target.strip()))
    return links


def write_page(web_root, rows, guide, links):
    """
    Write the web page with the addresses and the user guide.

    :param web_root: folder nginx serves the page from
    :param rows: list of (label, value) tuples
    :param guide: user guide Markdown file
    :param links: list of (label, path) tuples shown under the addresses
    """
    name = html.escape(socket.gethostname())
    cells = '\n'.join(f'<tr><th>{html.escape(label)}</th><td>{value_html(value)}</td></tr>' for label, value in rows)
    links_html = ' &middot; '.join(f'<a href="{html.escape(path)}">{html.escape(label)}</a>' for label, path in links)
    page = PAGE.format(name=name, when=time.strftime('%Y-%m-%d %H:%M %Z'), rows=cells, links=links_html,
                       guide=guide_html(guide))
    temporary = web_root / '.index.html.tmp'
    temporary.write_text(page, encoding='utf-8')
    temporary.chmod(0o644)
    os.replace(temporary, web_root / 'index.html')


def value_html(value):
    """
    Show one banner value on the web page: addresses as selectable code, web links as links.

    :param value: text from the banner rows, possibly several comma separated items
    :return: HTML
    """
    items = []
    for item in value.split(', '):
        safe = html.escape(item)
        if item.startswith('http'):
            items.append(f'<a href="{safe}">{safe}</a>')
        elif item not in ('off', 'no address') and item[0].isalnum() and ' ' not in item:
            items.append(f'<code class="addr">{safe}</code>')
        else:
            items.append(safe)
    return '<br>'.join(items)


def main():
    """Wait for the identities, then write both banners and the web page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True, help='Reticulum service data folder')
    parser.add_argument('--port', type=int, required=True, help='TCP server port, 0 when off')
    parser.add_argument('--issue', type=Path, required=True, help='console banner file')
    parser.add_argument('--ssh-banner', type=Path, default=None, help='SSH banner file')
    parser.add_argument('--wait', type=int, default=120, help='seconds to wait for identities')
    parser.add_argument('--nomadnet', action='store_true', help='the Nomad Network page node runs here')
    parser.add_argument('--propagation', action='store_true', help='the LXMF propagation node runs here')
    parser.add_argument('--http-port', type=int, default=0, help='web page port, 0 when off')
    parser.add_argument('--web-root', type=Path, default=None, help='folder to write the web page into')
    parser.add_argument('--guide', type=Path, default=None, help='user guide shown on the web page')
    parser.add_argument('--mdns', action='store_true', help='the host answers to <hostname>.local')
    parser.add_argument('--health', action='store_true', help='link to the health page')
    parser.add_argument('--links', type=Path, default=None, help='folder of extra page links, "Label|/path" per file')
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
    tcp = (', '.join(f'{a}:{args.port}' for a in addresses) or 'no address') if args.port else 'off'
    ssh_rows = [('TCP interface', tcp)]
    if args.http_port:
        suffix = '' if args.http_port == 80 else f':{args.http_port}'
        # agetty's \\n is the host name
        if args.mdns:
            console_rows.append(('Web page', f'http://\\n.local{suffix}/'))
            ssh_rows.append(('Web page', f'http://{socket.gethostname()}.local{suffix}/'))
        console_rows.append(('Web page' if not args.mdns else 'Web page by IP', f'http://\\4{suffix}/'))
        ssh_rows.append(('Web page' if not args.mdns else 'Web page by IP',
                         ', '.join(f'http://{a}{suffix}/' for a in addresses) or 'no address'))
    args.issue.write_text(banner(rows, console_rows))
    if args.ssh_banner:
        args.ssh_banner.write_text(banner(rows, ssh_rows))
    if args.web_root:
        write_page(args.web_root, ssh_rows + rows, args.guide, page_links(args.health, args.links))


if __name__ == '__main__':
    main()
