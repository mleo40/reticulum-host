"""Check-in bot and contacts list: answers LXMF messages, records announces, writes the contacts and notices pages.

The data folder holds identity, offgrid.db, and the files operators edit: operators.txt, roster.txt, notices.txt and
nets.txt.
"""
import argparse
import csv
import html
import json
import math
import os
import re
import socket
import sqlite3
import threading
import time
from pathlib import Path

import LXMF
import RNS
from RNS.vendor import umsgpack

# Marks messages from this bot, so two bots never answer each other
BOT_FIELD = 0xFB
BOT_MARK = b'reticulum-host.checkin'
MAX_TEXT = 500
REPLY_GAP = 20  # seconds between replies to one sender
HELP_GAP = 3600  # seconds between replies to unknown commands from one sender
PENDING_FOR = 600  # seconds to keep trying to reach a sender we have no path to
KINDS = {'lxmf.delivery': 'People', 'lxmf.propagation': 'Propagation nodes', 'retibbs.bbs': 'Bulletin boards',
         'lxst.room': 'Voice rooms', 'lxst.telephony': 'Phones', 'nomadnetwork.node': 'Nomad Network pages',
         'git.repositories': 'Git repositories'}
HELP = ('Commands: checkin <your status>, status (notices), nets (schedule), repeaters (nearest), help. '
        'Checking in records your name, status and time for the operators.')
OPERATOR_HELP = (' Operators: list; notice <text> adds a notice; net <when> | <frequency> | <net> adds a net; '
                 'notice remove <n> and net remove <n>; notice clear and net clear; broadcast <text>.')
MAX_LINES = 20  # notices or nets kept; the oldest go first
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>{title}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<h1>{title}</h1>
<p class="when">Updated {when}; this page updates every minute. <a href="/">Back to the host's page</a></p>
{body}
</body>
</html>
"""


def ago(moment, now):
    """
    Show how long ago a time was.

    :param moment: epoch seconds, or None
    :param now: epoch seconds
    :return: text such as 14:05 (2 h ago)
    """
    if not moment:
        return 'never'
    minutes = int((now - moment) // 60)
    span = f'{minutes} min' if minutes < 60 else f'{minutes // 60} h' if minutes < 2880 else f'{minutes // 1440} d'
    return f'{time.strftime("%Y-%m-%d %H:%M", time.localtime(moment))} ({span} ago)'


def table(rows, headings):
    """
    Build an HTML table. Cells are HTML already.

    :param rows: list of row tuples
    :param headings: heading tuple
    :return: HTML
    """
    if not rows:
        return '<p>None yet.</p>'
    head = '<tr>' + ''.join(f'<th>{h}</th>' for h in headings) + '</tr>\n'
    return '<table>\n' + head + '\n'.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows) + \
        '\n</table>'


def write_page(path, title, body):
    """
    Write a page in one step, so readers never see half of it.

    :param path: file to write
    :param title: page title
    :param body: HTML body
    """
    when = time.strftime('%Y-%m-%d %H:%M:%S %Z')
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(PAGE.format(title=html.escape(title), when=when, body=body), encoding='utf-8')
    temporary.chmod(0o644)
    os.replace(temporary, path)


NAME_KEYS = ('name', 'server_name', 'display_name', 'title')


# Column names in repeater lists, lower case; CHIRP and RepeaterBook exports use these
REPEATER_COLUMNS = {
    'output': ('output freq', 'output frequency', 'frequency', 'output', 'freq'),
    'input': ('input freq', 'input frequency', 'input'),
    'duplex': ('duplex',),
    'offset': ('offset',),
    'tone': ('uplink tone', 'pl', 'ctcss', 'access tone', 'tone up', 'rtonefreq'),
    'tone_mode': ('tone',),
    'call': ('call', 'callsign', 'name'),
    'place': ('nearest city', 'location', 'city', 'landmark', 'county'),
    'notes': ('notes', 'comment', 'use', 'coverage'),
    'mode': ('mode',),
    'lat': ('lat', 'latitude'),
    'lon': ('long', 'lon', 'longitude'),
}
MAX_REPEATERS = 50  # rows on the page


def read_repeaters(path):
    """
    Read a repeater list exported from CHIRP or RepeaterBook as CSV.

    :param path: CSV file; missing is fine
    :return: list of dicts with output, input, tone, call, place, notes, mode, lat and lon, as text or None
    """
    if not path.is_file():
        return []
    with path.open(encoding='utf-8-sig', errors='replace', newline='') as handle:
        reader = csv.DictReader(handle)
        headings = {(name or '').strip().lower(): name for name in reader.fieldnames or []}
        chirp = 'rtonefreq' in headings
        found = []
        for row in reader:
            def cell(key):
                for alias in REPEATER_COLUMNS[key]:
                    # CHIRP's Location is the memory channel, not a place
                    if chirp and key == 'place' and alias == 'location':
                        continue
                    value = (row.get(headings.get(alias)) or '').strip() if alias in headings else ''
                    if value:
                        return value
                return None
            output = cell('output')
            if not output:
                continue
            item = {key: cell(key) for key in REPEATER_COLUMNS}
            if not item['input'] and item['offset'] and item['duplex'] in ('+', '-'):
                try:
                    shift = float(item['offset']) * (1 if item['duplex'] == '+' else -1)
                    item['input'] = str(float(output) + shift)
                except ValueError:
                    pass
            for key in ('output', 'input'):
                item[key] = megahertz(item[key])
            if chirp and item['tone_mode'] not in ('Tone', 'TSQL'):
                item['tone'] = None
            for key in ('lat', 'lon'):
                try:
                    item[key] = float(item[key]) if item[key] else None
                except ValueError:
                    item[key] = None
            found.append(item)
    return found


def megahertz(text):
    """
    Write a frequency the usual way, such as 146.940 or 446.0125.

    :param text: frequency in MHz, or None
    :return: text, unchanged when it is not a number
    """
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    return f'{value:.3f}' if round(value, 3) == round(value, 4) else f'{value:.4f}'


def distance_text(km):
    """
    Show a distance in kilometres and miles.

    :param km: kilometres, or None
    :return: text such as 68 km (42 mi), or an empty string
    """
    return '' if km is None else f'{km:.0f} km ({km / 1.609344:.0f} mi)'


def gps_position(seconds=2.0):
    """
    Ask gpsd for this host's position.

    :param seconds: how long to wait for a fix
    :return: (latitude, longitude), or None without a fix or gpsd
    """
    try:
        with socket.create_connection(('127.0.0.1', 2947), timeout=seconds) as connection:
            connection.sendall(b'?WATCH={"enable":true,"json":true};')
            deadline = time.monotonic() + seconds
            buffer = b''
            while time.monotonic() < deadline:
                connection.settimeout(max(0.1, deadline - time.monotonic()))
                chunk = connection.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                *lines, buffer = buffer.split(b'\n')
                for line in lines:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if message.get('class') == 'TPV' and message.get('mode', 0) >= 2 and 'lat' in message:
                        return message['lat'], message['lon']
    except OSError:
        pass
    return None


def distance_km(here, lat, lon):
    """
    Great circle distance.

    :param here: (latitude, longitude)
    :param lat: latitude
    :param lon: longitude
    :return: kilometres
    """
    lat1, lon1, lat2, lon2 = map(math.radians, (here[0], here[1], lat, lon))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest_repeaters(repeaters, here):
    """
    Sort repeaters nearest first, when the host knows where it is and the list has positions.

    :param repeaters: from read_repeaters
    :param here: (latitude, longitude), or None
    :return: list of (distance in km or None, repeater), in file order without a position
    """
    if not here:
        return [(None, item) for item in repeaters]
    placed = [(distance_km(here, item['lat'], item['lon']), item) for item in repeaters
              if item['lat'] is not None and item['lon'] is not None]
    unplaced = [(None, item) for item in repeaters if item['lat'] is None or item['lon'] is None]
    return sorted(placed, key=lambda pair: pair[0]) + unplaced


def repeater_text(distance, item):
    """
    Describe one repeater in a short line, for messages.

    :param distance: km or None
    :param item: repeater dict
    :return: text such as W1ABC 146.940 (in 146.340) tone 100.0 FM, Boston, 3 km
    """
    parts = [item['call'] or '', item['output']]
    if item['input']:
        parts.append(f'(in {item["input"]})')
    if item['tone']:
        parts.append(f'tone {item["tone"]}')
    if item['mode']:
        parts.append(item['mode'])
    text = ' '.join(part for part in parts if part)
    for extra in (item['place'], distance_text(distance)):
        if extra:
            text += f', {extra}'
    return text


def net_cells(line):
    """
    Split one line of nets.txt into its three columns.

    :param line: such as Daily 08:00 | 146.520 MHz | Voice net
    :return: [when, frequency, net]; a line without | is all in the first column
    """
    cells = [cell.strip() for cell in line.split('|', 2)]
    return cells + [''] * (3 - len(cells))


def announce_name(kind, app_data):
    """
    Read the name a destination announces.

    :param kind: aspect name such as lxmf.delivery, or None
    :param app_data: announce data
    :return: name, or an empty string
    """
    if not app_data:
        return ''
    try:
        if kind == 'lxmf.delivery':
            return LXMF.display_name_from_app_data(app_data) or ''
        if kind == 'lxmf.propagation':
            return LXMF.pn_name_from_app_data(app_data) or ''
        text = app_data.decode('utf-8')
        if text.startswith(('{', '[')):
            text = first_name(json.loads(text))
    except UnicodeDecodeError:
        try:
            text = first_name(umsgpack.unpackb(app_data))
        except Exception:
            return ''
    except Exception:
        return ''
    return text if text.isprintable() and len(text) <= 64 else ''


def first_name(data):
    """
    Pick the name out of structured announce data: JSON from RetiBBS, msgpack from voice rooms.

    :param data: decoded dict, list or value
    :return: a name field, or the first text in it, or an empty string
    """
    if isinstance(data, dict):
        data = [data[key] for key in data if str(key).lower() in NAME_KEYS] + list(data.values())
    for value in data if isinstance(data, (list, tuple)) else [data]:
        if isinstance(value, bytes):
            value = value.decode('utf-8', 'replace')
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


class Store:
    """The bot's database: announces heard and check-ins."""

    def __init__(self, path):
        """
        Open or create the database.

        :param path: database file
        """
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS heard (dest TEXT PRIMARY KEY, identity TEXT, kind TEXT, name TEXT,
                                              first REAL, last REAL, count INTEGER);
            CREATE TABLE IF NOT EXISTS checkins (source TEXT PRIMARY KEY, name TEXT, status TEXT, time REAL,
                                                 count INTEGER);''')

    def heard(self, dest, identity, kind, name):
        """
        Record an announce.

        :param dest: destination hash, hex
        :param identity: identity hash, hex
        :param kind: aspect name, or None
        :param name: announced name
        """
        now = time.time()
        with self.lock, self.db:
            self.db.execute('''INSERT INTO heard VALUES (?, ?, ?, ?, ?, ?, 1) ON CONFLICT(dest) DO UPDATE SET
                               kind=excluded.kind, name=CASE WHEN excluded.name != '' THEN excluded.name ELSE name END,
                               last=excluded.last, count=count+1''', (dest, identity, kind or '', name, now, now))
            if name:
                # A check-in that came before the sender's announce holds a placeholder such as <1a2b3c4d>
                self.db.execute("UPDATE checkins SET name=? WHERE source=? AND name LIKE '<%'", (name, dest))

    def checkin(self, source, name, status):
        """
        Record a check-in, replacing the sender's earlier one.

        :param source: sender's LXMF address, hex
        :param name: sender's name
        :param status: text the sender gave
        """
        with self.lock, self.db:
            self.db.execute('''INSERT INTO checkins VALUES (?, ?, ?, ?, 1) ON CONFLICT(source) DO UPDATE SET
                               name=excluded.name, status=excluded.status, time=excluded.time, count=count+1''',
                            (source, name, status, time.time()))

    def rows(self, query, values=()):
        """
        Read rows.

        :param query: SQL
        :param values: query values
        :return: list of tuples
        """
        with self.lock:
            return self.db.execute(query, values).fetchall()


class Bot:
    """Answers LXMF messages and records announces."""

    def __init__(self, args):
        """
        Start Reticulum, the LXMF router and the announce listener.

        :param args: parsed command line
        """
        self.args = args
        self.data = Path(args.data)
        self.reticulum = RNS.Reticulum(args.rnsconfig)
        identity_path = self.data / 'identity'
        if identity_path.is_file():
            self.identity = RNS.Identity.from_file(str(identity_path))
        else:
            self.identity = RNS.Identity()
            self.identity.to_file(str(identity_path))
        self.store = Store(self.data / 'offgrid.db')
        self.router = LXMF.LXMRouter(identity=self.identity, storagepath=str(self.data))
        self.source = self.router.register_delivery_identity(self.identity, display_name=args.name,
                                                             stamp_cost=args.stamp_cost or None)
        self.router.register_delivery_callback(self.received)
        pn = Path(args.propagation_identity) if args.propagation_identity else None
        if pn and pn.is_file():
            pn_hash = RNS.Destination.hash_from_name_and_identity('lxmf.propagation',
                                                                  RNS.Identity.from_file(str(pn)))
            self.router.set_outbound_propagation_node(pn_hash)
        self.last_reply, self.last_help, self.pending = {}, {}, []
        self.pending_lock = threading.Lock()
        self.aspect_filter = None
        RNS.Transport.register_announce_handler(self)

    def received_announce(self, destination_hash, announced_identity, app_data):
        """
        Record every announce the host hears.

        :param destination_hash: announced destination
        :param announced_identity: its identity
        :param app_data: announce data
        """
        if destination_hash == self.source.hash or announced_identity is None:
            return
        hashes = {name: RNS.Destination.hash_from_name_and_identity(name, announced_identity) for name in KINDS}
        kind = next((name for name, value in hashes.items() if value == destination_hash), None)
        self.store.heard(destination_hash.hex(), announced_identity.hash.hex(), kind, announce_name(kind, app_data))

    def name_of(self, source):
        """
        Find a sender's announced name.

        :param source: LXMF address, hex
        :return: name, or a short form of the address
        """
        found = self.store.rows("SELECT name FROM heard WHERE dest=? AND name != ''", (source,))
        return found[0][0] if found else f'<{source[:8]}>'

    def received(self, message):
        """
        Handle a message sent to the bot.

        :param message: LXMF.LXMessage
        """
        source = message.source_hash.hex()
        fields = message.fields or {}
        if message.source_hash == self.source.hash or fields.get(BOT_FIELD) == BOT_MARK:
            return
        now = time.time()
        if now - self.last_reply.get(source, 0) < REPLY_GAP:
            return
        text = (message.content_as_string() or '').strip()[:MAX_TEXT]
        command, _, rest = text.partition(' ')
        command, rest = command.lower(), rest.strip()
        operator = source in self.operators()
        notices, nets = self.data / 'notices.txt', self.data / 'nets.txt'
        if command in ('checkin', 'check-in', 'ci'):
            name = self.name_of(source)
            self.store.checkin(source, name, rest or 'checked in')
            reply = (f'Checked in at {time.strftime("%H:%M %Z")}: {name}, {rest or "checked in"}. Send checkin '
                     'again to update; status for notices.')
        elif command in ('status', 'notices'):
            reply = '\n'.join(f'{n}. {line}' for n, line in enumerate(self.lines(notices), 1)) or 'No notices.'
        elif command in ('nets', 'net') and not (operator and rest):
            reply = '\n'.join(f'{n}. {", ".join(net_cells(line))}' for n, line in enumerate(self.lines(nets), 1)) \
                or 'No net schedule.'
        elif command in ('repeaters', 'repeater', 'rpt'):
            nearest = nearest_repeaters(read_repeaters(self.data / 'repeaters.csv'), self.position())[:5]
            reply = '\n'.join(repeater_text(distance, item) for distance, item in nearest) or 'No repeater list.'
        elif command == 'help':
            reply = HELP + (OPERATOR_HELP if operator else '')
        elif operator and command == 'list':
            rows = self.store.rows('SELECT name, status, time FROM checkins ORDER BY time DESC LIMIT 10')
            total = self.store.rows('SELECT COUNT(*) FROM checkins')[0][0]
            reply = f'{total} checked in. Latest: ' + '; '.join(
                f'{n}: {s} ({time.strftime("%H:%M", time.localtime(t))})' for n, s, t in rows) if rows else 'None yet.'
        elif operator and command in ('notice', 'net', 'nets') and rest:
            reply = self.edit(notices if command == 'notice' else nets, rest,
                              'notice' if command == 'notice' else 'net')
        elif operator and command == 'broadcast' and rest:
            recipients = [row[0] for row in self.store.rows('SELECT source FROM checkins') if row[0] != source]
            for recipient in recipients:
                self.send(recipient, rest)
            reply = f'Sent to {len(recipients)} who have checked in.'
        else:
            if now - self.last_help.get(source, 0) < HELP_GAP:
                return
            self.last_help[source] = now
            reply = HELP + (OPERATOR_HELP if operator else '')
        self.last_reply[source] = now
        self.send(source, reply)

    def operators(self):
        """
        List the LXMF addresses allowed operator commands, from operators.txt; read on each message.

        :return: set of hex addresses
        """
        found = set()
        for line in self.read(self.data / 'operators.txt').splitlines():
            address = line.split('#', 1)[0].strip().lower()
            if re.fullmatch(r'[0-9a-f]{32}', address):
                found.add(address)
        return found

    def position(self):
        """
        Find where the host is: the GPS fix, or the --position setting.

        :return: (latitude, longitude), or None
        """
        return gps_position() or self.args.position

    def lines(self, path):
        """
        Read a notices or nets file: one item per line.

        :param path: file
        :return: list of non-empty lines
        """
        return [line.strip() for line in self.read(path).splitlines() if line.strip()]

    def edit(self, path, rest, kind):
        """
        Add, remove or clear one notice or net, from an operator's message.

        :param path: notices.txt or nets.txt
        :param rest: the message after the command: text to add, remove <n>, or clear
        :param kind: notice or net, for the reply
        :return: reply text
        """
        items = self.lines(path)
        removing = re.fullmatch(r'remove\s+(\d+)', rest, re.IGNORECASE)
        if rest.lower() == 'clear':
            items = []
            reply = f'All {kind}s cleared.'
        elif removing:
            number = int(removing[1])
            if not 1 <= number <= len(items):
                return f'There is no {kind} {number}; there are {len(items)}.'
            reply = f'Removed {kind} {number}: {items.pop(number - 1)}'
        else:
            # Newest notice first; nets keep the order they were added in
            items = [rest] + items if kind == 'notice' else items + [rest]
            items = items[:MAX_LINES] if kind == 'notice' else items[-MAX_LINES:]
            reply = f'Added {kind} {1 if kind == "notice" else len(items)}. {kind.capitalize()}s: {len(items)}.'
        temporary = path.with_name('.' + path.name + '.tmp')
        temporary.write_text(''.join(item + '\n' for item in items), encoding='utf-8')
        os.replace(temporary, path)
        return reply

    @staticmethod
    def read(path):
        """
        Read an operator's text file.

        :param path: file
        :return: text, or an empty string
        """
        return path.read_text(encoding='utf-8').strip() if path.is_file() else ''

    def send(self, destination, text, since=None):
        """
        Send a message, directly or through the propagation node; wait for a path first if needed.

        :param destination: LXMF address, hex
        :param text: message
        :param since: when the first try was, for messages waiting for a path
        """
        destination_hash = bytes.fromhex(destination)
        identity = RNS.Identity.recall(destination_hash)
        if identity is None:
            RNS.Transport.request_path(destination_hash)
            with self.pending_lock:
                self.pending.append((destination, text, since or time.time()))
            return
        target = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, 'lxmf', 'delivery')
        message = LXMF.LXMessage(target, self.source, text, '', fields={BOT_FIELD: BOT_MARK},
                                 desired_method=LXMF.LXMessage.DIRECT)
        message.register_failed_callback(self.failed)
        self.router.handle_outbound(message)

    def failed(self, message):
        """
        Leave a message the recipient could not take directly on the propagation node.

        :param message: LXMF.LXMessage that failed
        """
        if message.desired_method == LXMF.LXMessage.DIRECT and self.router.get_outbound_propagation_node():
            retry = LXMF.LXMessage(message.get_destination(), self.source, message.content_as_string(), '',
                                   fields={BOT_FIELD: BOT_MARK}, desired_method=LXMF.LXMessage.PROPAGATED)
            self.router.handle_outbound(retry)

    def retry_pending(self):
        """Send messages that were waiting for a path, and drop ones waiting too long."""
        with self.pending_lock:
            waiting, self.pending = self.pending, []
        for destination, text, since in waiting:
            if time.time() - since < PENDING_FOR:
                self.send(destination, text, since)

    def paths(self):
        """
        Ask the shared instance which destinations it has paths to.

        :return: dict of hex hash to (hops, interface name)
        """
        try:
            table = self.reticulum.get_path_table() or []
        except Exception:
            return {}
        return {entry['hash'].hex(): (entry['hops'], re.sub(r'\[.*', '', entry['interface'])) for entry in table}

    def write_pages(self):
        """Write the contacts page for operators and the public notices page."""
        now, args = time.time(), self.args
        paths = self.paths()
        heard = {row[0]: row for row in self.store.rows('SELECT dest, identity, kind, name, first, last, count '
                                                         'FROM heard')}
        checkins = {row[0]: row for row in self.store.rows('SELECT source, name, status, time, count FROM checkins')}
        roster = []
        roster_file = self.data / 'roster.txt'
        for line in (roster_file.read_text(encoding='utf-8').splitlines() if roster_file.is_file() else []):
            address, _, name = line.split('#', 1)[0].strip().partition(' ')
            if re.fullmatch(r'[0-9a-fA-F]{32}', address):
                roster.append((address.lower(), name.strip() or address[:8]))

        def route(address):
            hops, interface = paths.get(address, (None, ''))
            if hops is None:
                return ''
            if hops == 0 or interface.startswith('LocalInterface'):
                return 'on this host'
            return html.escape(f'{hops} hop{"s" if hops != 1 else ""}, {interface}')

        def code(address):
            return f'<code class="addr">{address}</code>'

        ranked = []
        for address, name in roster:
            last_check = checkins.get(address, (None, None, '', None))[3]
            last_heard = heard.get(address, (None,) * 6)[5]
            last = max(t for t in (last_check, last_heard, 0) if t is not None)
            hours = (now - last) / 3600 if last else None
            rank, level, state = ((0, 'bad', 'not heard') if hours is None
                                  else (0, 'bad', 'overdue') if hours > args.red_hours
                                  else (1, 'warn', 'late') if hours > args.amber_hours else (2, 'ok', 'OK'))
            ranked.append((rank, name.lower(), (f'<span class="{level}">{state}</span>', html.escape(name),
                                                code(address), ago(last_check, now),
                                                html.escape(checkins.get(address, ('', '', ''))[2]),
                                                ago(last_heard, now), route(address))))
        roster_rows = [row for _, _, row in sorted(ranked)]
        roster_file_html = '<code>/var/lib/reticulum/offgrid/roster.txt</code>'
        if roster:
            counts = [sum(1 for rank, _, _ in ranked if rank == n) for n in (2, 1, 0)]
            others = sum(1 for source in checkins if source not in {address for address, _ in roster})
            summary = (f'Roster of {len(roster)}: {counts[0]} OK, {counts[1]} late, {counts[2]} overdue or not heard. '
                       f'Not on the roster: {others} checked in.')
            roster_html = [f'<h2>Roster</h2>\n<p>The people you expect to hear from, from {roster_file_html}. '
                           f'Late after {args.amber_hours:g} h and overdue after {args.red_hours:g} h without an '
                           'announce or check-in.</p>',
                           table(roster_rows, ('State', 'Name', 'Address', 'Last check-in', 'Status', 'Last heard',
                                               'Route'))]
        else:
            summary = f'{len(checkins)} checked in. No roster yet.'
            roster_html = [f'<h2>Roster</h2>\n<p>No roster yet. To track the people you expect to hear from, list '
                           f'them in {roster_file_html}, one per line: their LXMF address, a space, and their name. '
                           'This page then marks each one OK, late, overdue or not heard.</p>']
        on_roster = {address for address, _ in roster}
        rows = [(html.escape(name), code(source), ago(when, now), html.escape(status), str(count), route(source))
                for source, name, status, when, count in sorted(checkins.values(), key=lambda row: -row[3])
                if source not in on_roster]
        checkins_html = [f'<h2>{"Check-ins not on the roster" if roster else "Check-ins"}</h2>',
                         table(rows, ('Name', 'Address', 'Last check-in', 'Status', 'Check-ins', 'Route'))]
        # With a roster, the roster comes first; without one, the check-ins do
        body = [f'<p class="summary">{summary}</p>'] + (roster_html + checkins_html if roster
                                                          else checkins_html + roster_html)
        body.append('<h2>Heard on the network</h2>')
        # Git servers (rngit) announce their pages as an ordinary page node, with the identity of their repositories
        git_identities = {identity for _, identity, k, *_ in heard.values() if k == 'git.repositories'}

        def section(row):
            _, identity, k, *_ = row
            return 'git.pages' if k == 'nomadnetwork.node' and identity in git_identities else k

        for kind, label in list(KINDS.items()) + [('git.pages', 'Git pages'), ('', 'Other')]:
            rows = [(html.escape(name or ''), code(dest), ago(last, now), ago(first, now), str(count), route(dest))
                    for dest, identity, k, name, first, last, count in sorted(heard.values(), key=lambda row: -row[5])
                    if section((dest, identity, k)) == kind][:500]
            if rows:
                body += [f'<h3>{label}</h3>', table(rows, ('Name', 'Address', 'Last heard', 'First heard', 'Times',
                                                           'Route'))]
        write_page(Path(args.web) / 'contacts' / 'index.html', 'Contacts', '\n'.join(body))
        notices = self.lines(self.data / 'notices.txt')
        nets = [[html.escape(cell) for cell in net_cells(line)] for line in self.lines(self.data / 'nets.txt')]
        notices_html = ('<ol class="notices">\n' + '\n'.join(f'<li>{html.escape(line)}</li>' for line in notices) +
                        '\n</ol>') if notices else '<p>No notices.</p>'
        body = (f'<h2>Notices</h2>\n{notices_html}\n<h2>Nets</h2>\n'
                f'{table(nets, ("When", "Frequency", "Net")) if nets else "<p>No net schedule.</p>"}\n'
                f'{self.repeaters_html()}\n'
                f'<h2>How to check in</h2>\n<p>Send <code>checkin</code> and your status, such as '
                f'<code>checkin All OK at the school</code>, from Sideband, MeshChat or Columba to '
                f'<code class="addr">{self.source.hash.hex()}</code>. The bot replies to confirm. '
                'Check-ins are not shown on this page: only the operators see your name, status and the time.</p>')
        write_page(Path(args.web) / 'notices' / 'index.html', 'Notices', body)

    def repeaters_html(self):
        """
        Build the repeater section of the notices page, nearest first when the host knows where it is.

        :return: HTML, or an empty string without a repeater list
        """
        repeaters = read_repeaters(self.data / 'repeaters.csv')
        if not repeaters:
            return ''
        here = self.position()
        nearest = nearest_repeaters(repeaters, here)
        rows = [tuple(html.escape(value or '') for value in (
                    distance_text(distance), item['call'], item['output'],
                    item['input'], item['tone'], item['mode'], item['place'], item['notes']))
                for distance, item in nearest[:MAX_REPEATERS]]
        where = ('Nearest first, from the host\'s position.' if here and any(d is not None for d, _ in nearest)
                 else 'In the order of the list; the host does not know its position, or the list has none.')
        more = f' The first {MAX_REPEATERS} of {len(repeaters)}.' if len(repeaters) > MAX_REPEATERS else ''
        return (f'<h2>Repeaters</h2>\n<p>{where}{more} Check the details on the air: lists go out of date.</p>\n' +
                table(rows, ('Distance', 'Call', 'Output', 'Input', 'Tone', 'Mode', 'Place', 'Notes')))

    def run(self):
        """Announce, retry waiting messages and rewrite the pages, for ever."""
        next_announce = 0
        while True:
            if time.time() >= next_announce:
                self.router.announce(self.source.hash)
                next_announce = time.time() + self.args.announce_minutes * 60
            self.retry_pending()
            try:
                self.write_pages()
            except Exception as error:
                RNS.log(f'Could not write the pages: {error}', RNS.LOG_ERROR)
            time.sleep(60)


def main():
    """Parse the command line and run the bot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rnsconfig', required=True, help='shared Reticulum config folder')
    parser.add_argument('--data', required=True, help='folder for the identity, database and text files')
    parser.add_argument('--web', required=True, help='web folder holding contacts/ and notices/')
    parser.add_argument('--name', default='Check-in', help='name the bot announces')
    parser.add_argument('--propagation-identity', default=None, help="the host's propagation node identity file")
    parser.add_argument('--announce-minutes', type=int, default=30)
    parser.add_argument('--position', type=lambda text: tuple(float(part) for part in text.split(',')),
                        default=None, help='latitude,longitude to use without a GPS fix')
    parser.add_argument('--amber-hours', type=float, default=6)
    parser.add_argument('--red-hours', type=float, default=24)
    parser.add_argument('--stamp-cost', type=int, default=0, help='proof of work senders must add, 0 for none')
    Bot(parser.parse_args()).run()


if __name__ == '__main__':
    main()
