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


def address_row(label, identity, name):
    """
    Make a banner row for one address, with the text its QR code holds.

    :param label: row label
    :param identity: RNS.Identity or None
    :param name: full destination name
    :return: (label, hex hash, QR text or None); LXMF addresses use lxma://hash:public key, which Columba scans
             to add a contact
    """
    value = destination(identity, name)
    if identity is None:
        return label, value, None
    if name == 'lxmf.delivery':
        return label, value, f'lxma://{value}:{identity.get_public_key().hex()}'
    return label, value, value


def qr_svg(text):
    """
    Draw a QR code as a small inline SVG, dark on white so it scans in dark mode too.

    :param text: what the code holds
    :return: SVG text, or an empty string when the qrcode package is missing
    """
    try:
        import qrcode
    except ImportError:
        return ''
    code = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(text)
    code.make(fit=True)
    matrix = code.get_matrix()
    size = len(matrix)
    runs = []
    for y, line in enumerate(matrix):
        x = 0
        while x < size:
            if line[x]:
                start = x
                while x < size and line[x]:
                    x += 1
                runs.append(f'M{start} {y}h{x - start}v1h-{x - start}z')
            else:
                x += 1
    return (f'<svg class="qr" viewBox="0 0 {size} {size}" role="img" aria-label="QR code: {html.escape(text)}" '
            f'shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg"><rect width="{size}" '
            f'height="{size}" fill="#fff"/><path fill="#000" d="{"".join(runs)}"/></svg>')


def ipv4_addresses():
    """
    List this host's IPv4 addresses, without loopback.

    :return: list of address strings
    """
    output = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=False).stdout
    return [address for address in output.split() if '.' in address]


def service_active(unit):
    """
    Check whether a systemd unit is running.

    :param unit: unit name
    :return: True when active
    """
    return subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=False).returncode == 0


def banner(rows, network_rows):
    """
    Build the banner text.

    :param rows: list of (label, value, QR text) tuples
    :param network_rows: the same, for what is reached over IP, shown first
    :return: banner text
    """
    rows = network_rows + rows
    width = max(len(row[0]) for row in rows)
    lines = ['Reticulum host'] + [f'  {label.ljust(width)}  {value}' for label, value, _ in rows]
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
<p class="when">Host name {name}. Addresses as of {when}. Tap an address to select it, then copy. To scan them
instead, open the <a href="/card.html">scannable QR codes</a>.</p>
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


def extra_addresses(folder):
    """
    List addresses other roles add, such as the check-in bot's.

    :param folder: folder of files holding "Label|identity file|aspect", or None
    :return: list of (label, identity path, aspect) tuples
    """
    found = []
    if folder and folder.is_dir():
        for path in sorted(folder.iterdir()):
            parts = [part.strip() for part in path.read_text(encoding='utf-8').strip().split('|')]
            if len(parts) == 3 and all(parts):
                found.append((parts[0], Path(parts[1]), parts[2]))
    return found


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


CARD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QR codes {name}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body class="card">
<p class="noprint"><a href="/">Back to the host's page</a>. Scan a code with your phone's camera, or print this
page, or save it as a PDF, and keep it with the host.</p>
<h1>Reticulum host {name}</h1>
<p class="when">Printed from the host on {when}.</p>
<ol>
<li>Join the same network as the host, by Wi-Fi or cable.</li>
<li>Open the host's page, by scanning a web page code below, for the full guide.</li>
<li>In Sideband, MeshChat or Columba, add a TCP client interface to the host's TCP interface address.</li>
<li>Message the addresses below from your app; Columba can scan the codes to add a contact.</li>
</ol>
<div class="cards">
{cells}
</div>
<p class="when">The Reticulum addresses stay the same. The IP addresses may change when the router gives out new
ones; print a new card then.</p>
</body>
</html>
"""


def write_atomic(path, text):
    """
    Replace a web file in one step, so nginx never serves half of it.

    :param path: file to write
    :param text: content
    """
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.chmod(0o644)
    os.replace(temporary, path)


def write_page(web_root, rows, guide, links):
    """
    Write the web page with the addresses and the user guide, and the QR code page, which prints as an address card.

    :param web_root: folder nginx serves the pages from
    :param rows: list of (label, value, QR text) tuples
    :param guide: user guide Markdown file
    :param links: list of (label, path) tuples shown under the addresses
    """
    name = html.escape(socket.gethostname())
    when = time.strftime('%Y-%m-%d %H:%M %Z')
    cells = '\n'.join(f'<tr><th>{html.escape(label)}</th><td>{value_html(value)}</td></tr>' for label, value, _ in rows)
    links = links + [('Scannable QR codes', '/card.html')]
    links_html = ' &middot; '.join(f'<a href="{html.escape(path)}">{html.escape(label)}</a>' for label, path in links)
    write_atomic(web_root / 'index.html', PAGE.format(name=name, when=when, rows=cells, links=links_html,
                                                      guide=guide_html(guide)))
    cards = []
    # The transport identity is for operators, not for people connecting
    for label, value, code in rows:
        if label == 'Transport identity':
            continue
        for item, item_code in split_codes(value, code):
            cards.append(f'<div class="item">{qr_svg(item_code) if item_code else ""}<h2>{html.escape(label)}</h2>'
                         f'<code>{html.escape(item)}</code></div>')
    write_atomic(web_root / 'card.html', CARD.format(name=name, when=when, cells='\n'.join(cards)))


def split_codes(value, code):
    """
    Split a row with several items, such as one web address per IP address, into one card each.

    :param value: row value, items separated by ", "
    :param code: QR text for a single item row; web and TCP addresses always get their own
    :return: list of (item, QR text or None)
    """
    items = value.split(', ')
    if len(items) == 1:
        return [(value, code)]
    return [(item, item if item.startswith('http') or ':' in item else None) for item in items]


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
    parser.add_argument('--addresses', type=Path, default=None,
                        help='folder of extra addresses, "Label|identity file|aspect" per file, such as a bot')
    args = parser.parse_args()

    files = {'transport': args.home / 'rns/storage/transport_identity',
             'retibbs': args.home / 'retibbs/server_identity.pem',
             'rngit': args.home / 'rngit/repositories_identity',
             'partyline': args.home / 'partyline/server_identity'}
    # Also when the page node was turned on by hand, which the role's settings do not know about
    if args.nomadnet or service_active('nomadnet'):
        files['nomadnet'] = args.home / 'nomadnet/storage/identity'
    if args.propagation:
        files['lxmd'] = args.home / 'lxmd/identity'
    extra = extra_addresses(args.addresses)
    for label, path, _ in extra:
        files[label] = path
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
    rows = [('Transport identity', transport.hash.hex() if transport else 'not created yet', None),
            address_row('RetiBBS', retibbs, 'retibbs.bbs'),
            address_row('Partyline voice', partyline, 'lxst.room'),
            address_row('Git repositories', rngit, 'git.repositories'),
            address_row('Git pages', rngit, 'nomadnetwork.node')]
    if 'nomadnet' in files:
        rows.append(address_row('Nomad Network pages', load_identity(files['nomadnet']), 'nomadnetwork.node'))
    if args.propagation:
        rows.append(address_row('LXMF propagation', load_identity(files['lxmd']), 'lxmf.propagation'))
    for label, path, aspect in extra:
        rows.append(address_row(label, load_identity(path), aspect))

    # The console banner uses agetty's \\4, the current IPv4 address; the SSH banner lists them when written
    addresses = ipv4_addresses()
    console_rows = [('TCP interface', f'\\4:{args.port}' if args.port else 'off', None)]
    tcp = (', '.join(f'{a}:{args.port}' for a in addresses) or 'no address') if args.port else 'off'
    ssh_rows = [('TCP interface', tcp, tcp if args.port and len(addresses) == 1 else None)]
    if args.http_port:
        suffix = '' if args.http_port == 80 else f':{args.http_port}'
        # agetty's \\n is the host name
        if args.mdns:
            local = f'http://{socket.gethostname()}.local{suffix}/'
            console_rows.append(('Web page', f'http://\\n.local{suffix}/', None))
            ssh_rows.append(('Web page', local, local))
        by_ip = [f'http://{a}{suffix}/' for a in addresses]
        console_rows.append(('Web page' if not args.mdns else 'Web page by IP', f'http://\\4{suffix}/', None))
        ssh_rows.append(('Web page' if not args.mdns else 'Web page by IP', ', '.join(by_ip) or 'no address',
                         by_ip[0] if len(by_ip) == 1 else None))
    args.issue.write_text(banner(rows, console_rows))
    if args.ssh_banner:
        args.ssh_banner.write_text(banner(rows, ssh_rows))
    if args.web_root:
        write_page(args.web_root, ssh_rows + rows, args.guide, page_links(args.health, args.links))


if __name__ == '__main__':
    main()
