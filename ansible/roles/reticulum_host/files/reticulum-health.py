"""Write the host's health page: time, GPS, power, system, services and Reticulum interfaces."""
import argparse
import html
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Health {name}</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<h1>Host health</h1>
<p class="when">Host name {name}. Checked {when}; this page updates every minute.
<a href="/">Back to the host's page</a></p>
<p class="summary">{summary}</p>
{sections}
</body>
</html>
"""
# Raspberry Pi firmware throttling flags, from vcgencmd get_throttled
THROTTLE_NOW = {0: 'under-voltage now', 1: 'CPU speed capped now', 2: 'throttled now', 3: 'temperature limit now'}
THROTTLE_SINCE_BOOT = {16: 'under-voltage', 17: 'CPU speed capped', 18: 'throttling', 19: 'temperature limit'}
GPS_FIX = {0: 'unknown', 1: 'no fix', 2: '2D fix', 3: '3D fix'}


def run(command, user=None):
    """
    Run a command and return its output.

    :param command: argument list
    :param user: run as this user instead of root
    :return: standard output, or None if the command is missing or fails
    """
    if user:
        command = ['runuser', '-u', user, '--'] + command
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def span(level, text):
    """
    Colour a status word.

    :param level: ok, warn or bad
    :param text: text to show
    :return: HTML
    """
    return f'<span class="{level}">{html.escape(text)}</span>'


def table(rows, headings=None):
    """
    Build an HTML table. Cells are HTML already.

    :param rows: list of row tuples
    :param headings: optional heading tuple
    :return: HTML
    """
    head = '<tr>' + ''.join(f'<th>{h}</th>' for h in headings) + '</tr>\n' if headings else ''
    body = '\n'.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
    return f'<table>\n{head}{body}\n</table>'


def size(count):
    """
    Show a byte count in a short readable form.

    :param count: bytes
    :return: text such as 3.2 GB
    """
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if count < 1024 or unit == 'TB':
            return f'{count:.0f} {unit}' if unit == 'B' else f'{count:.1f} {unit}'
        count /= 1024


def duration(seconds):
    """
    Show a duration in days, hours and minutes.

    :param seconds: length of time
    :return: text such as 2 d 3 h 10 min
    """
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    parts = [f'{days} d'] if days else []
    if days or hours:
        parts.append(f'{hours} h')
    parts.append(f'{minutes} min')
    return ' '.join(parts)


def time_section(problems):
    """
    Report the clock and how it is kept right.

    :param problems: list to add problems to
    :return: HTML
    """
    rows = [('System time', html.escape(time.strftime('%Y-%m-%d %H:%M:%S %Z')))]
    tracking = run(['chronyc', '-c', 'tracking'])
    if tracking:
        fields = tracking.strip().split(',')
        source, stratum, offset, leap = fields[1], fields[2], float(fields[4]), fields[13]
        synced = leap != 'Not synchronised'
        rows.append(('Synchronised', span('ok', 'yes') if synced else span('bad', 'no')))
        if synced:
            rows.append(('Time source', html.escape(f'{source}, stratum {stratum}, offset {offset * 1000:+.1f} ms')))
        else:
            problems.append('the clock is not synchronised')
        sources = run(['chronyc', '-c', 'sources']) or ''
        for line in sources.splitlines():
            fields = line.split(',')
            if len(fields) > 2 and fields[2] == 'GPS':
                states = {'*': ('ok', 'in use'), '+': ('ok', 'usable'), '-': ('warn', 'not used'),
                          '?': ('warn', 'no data'), 'x': ('warn', 'disagrees with other sources'),
                          '~': ('warn', 'too variable')}
                level, text = states.get(fields[1], ('warn', fields[1]))
                rows.append(('GPS as time source', span(level, text)))
    else:
        synced = (run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value']) or '').strip() == 'yes'
        rows.append(('Synchronised', span('ok', 'yes') if synced else span('bad', 'no')))
        if not synced:
            problems.append('the clock is not synchronised')
    return '<h2>Time</h2>\n' + table(rows)


def read_gpsd(seconds=3.0):
    """
    Ask gpsd for its devices, position and satellites.

    :param seconds: how long to listen
    :return: dict with devices, tpv and sky, or None when gpsd does not answer
    """
    found = {'devices': [], 'tpv': None, 'sky': None}
    try:
        with socket.create_connection(('127.0.0.1', 2947), timeout=seconds) as connection:
            connection.sendall(b'?WATCH={"enable":true,"json":true};')
            deadline = time.monotonic() + seconds
            buffer = b''
            while time.monotonic() < deadline and not (found['tpv'] and found['sky']):
                connection.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buffer += chunk
                *lines, buffer = buffer.split(b'\n')
                for line in lines:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    kind = message.get('class')
                    if kind == 'DEVICES':
                        found['devices'] = [device.get('path', '') for device in message.get('devices', [])]
                    elif kind == 'TPV':
                        found['tpv'] = message
                    elif kind == 'SKY' and message.get('satellites') is not None:
                        found['sky'] = message
    except OSError:
        return None
    return found


def gps_section(show_position, problems):
    """
    Report the GPS receiver, fix and position.

    :param show_position: include latitude, longitude and altitude
    :param problems: list to add problems to
    :return: HTML, or an empty string when gpsd is not installed
    """
    if not shutil.which('gpsd'):
        return ''
    gps = read_gpsd()
    if gps is None:
        problems.append('gpsd is not answering')
        return '<h2>GPS</h2>\n' + table([('gpsd', span('bad', 'not answering'))])
    if not gps['devices']:
        return '<h2>GPS</h2>\n' + table([('Receiver', span('warn', 'none connected'))])
    rows = [('Receiver', html.escape(', '.join(gps['devices'])))]
    tpv = gps['tpv'] or {}
    mode = tpv.get('mode', 0)
    rows.append(('Fix', span('ok' if mode == 3 else 'warn', GPS_FIX.get(mode, str(mode)))))
    satellites = (gps['sky'] or {}).get('satellites') or []
    used = sum(1 for satellite in satellites if satellite.get('used'))
    rows.append(('Satellites', f'{used} used of {len(satellites)} seen'))
    if tpv.get('time'):
        rows.append(('GPS time', html.escape(tpv['time'])))
    if show_position and mode >= 2 and 'lat' in tpv:
        position = f"{tpv['lat']:.5f}, {tpv['lon']:.5f}"
        if mode == 3 and tpv.get('altHAE', tpv.get('alt')) is not None:
            position += f", {tpv.get('altHAE', tpv.get('alt')):.0f} m"
        rows.append(('Position', f'<code class="addr">{html.escape(position)}</code>'))
    return '<h2>GPS</h2>\n' + table(rows)


def power_section(problems):
    """
    Report Raspberry Pi power and temperature throttling.

    :param problems: list to add problems to
    :return: HTML, or an empty string on other computers
    """
    output = run(['vcgencmd', 'get_throttled'])
    if not output or '=' not in output:
        return ''
    flags = int(output.strip().split('=')[1], 16)
    now = [text for bit, text in THROTTLE_NOW.items() if flags & (1 << bit)]
    since = [text for bit, text in THROTTLE_SINCE_BOOT.items() if flags & (1 << bit)]
    rows = [('Now', span('bad', ', '.join(now)) if now else span('ok', 'normal')),
            ('Since boot', span('warn', ', '.join(since)) if since else span('ok', 'normal'))]
    if now:
        problems.append(f'power: {", ".join(now)}')
    elif since:
        problems.append(f'power since boot: {", ".join(since)}')
    return '<h2>Power</h2>\n' + table(rows)


def system_section(disks, problems):
    """
    Report uptime, load, temperature, memory and disk space.

    :param disks: folders whose file systems to report
    :param problems: list to add problems to
    :return: HTML
    """
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    load = ', '.join(f'{value:.2f}' for value in os.getloadavg())
    rows = [('Up for', duration(uptime)), ('Load (1, 5, 15 min)', f'{load} on {os.cpu_count()} CPUs')]
    thermal = Path('/sys/class/thermal/thermal_zone0/temp')
    if thermal.is_file():
        celsius = int(thermal.read_text()) / 1000
        level = 'ok' if celsius < 70 else 'warn' if celsius < 80 else 'bad'
        rows.append(('CPU temperature', span(level, f'{celsius:.0f} °C')))
        if level != 'ok':
            problems.append(f'CPU at {celsius:.0f} °C')
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    total = int(memory['MemTotal'].split()[0]) * 1024
    available = int(memory['MemAvailable'].split()[0]) * 1024
    rows.append(('Memory', f'{size(total - available)} used of {size(total)}'))
    seen = set()
    for folder in disks:
        if not os.path.isdir(folder) or os.stat(folder).st_dev in seen:
            continue
        seen.add(os.stat(folder).st_dev)
        usage = shutil.disk_usage(folder)
        percent = usage.used * 100 / usage.total
        level = 'ok' if percent < 80 else 'warn' if percent < 95 else 'bad'
        rows.append((f'Disk {html.escape(folder)}', span(level, f'{percent:.0f}% used') + f', {size(usage.free)} free'))
        if level != 'ok':
            problems.append(f'disk {folder} {percent:.0f}% full')
    return '<h2>System</h2>\n' + table(rows)


def services_section(units, optional, problems):
    """
    Report whether each service is running.

    :param units: systemd unit names
    :param optional: units that only run when something they need is there; stopped is not a problem
    :param problems: list to add problems to
    :return: HTML
    """
    rows = []
    for unit in units + [unit for unit in optional if unit not in units]:
        output = run(['systemctl', 'show', '-p', 'ActiveState,SubState,ActiveEnterTimestamp,Type,Result', unit]) or ''
        state = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        active, sub = state.get('ActiveState', 'unknown'), state.get('SubState', '')
        level = 'ok' if active == 'active' else 'warn' if active in ('activating', 'reloading') else 'bad'
        # A job that runs once, such as the login banner, is inactive after it has done its work
        if active == 'inactive' and state.get('Type') == 'oneshot' and state.get('Result') == 'success':
            level, sub = 'ok', 'done'
        if unit in optional and active == 'inactive':
            level, sub = 'warn', 'stopped until needed'
        if level == 'bad':
            problems.append(f'{unit} is {active}')
        rows.append((html.escape(unit), span(level, f'{active} ({sub})' if sub else active),
                     html.escape(state.get('ActiveEnterTimestamp', '') if active == 'active' else '')))
    return '<h2>Services</h2>\n' + table(rows, ('Unit', 'State', 'Since'))


def reticulum_section(venv, rnsconfig, user, problems):
    """
    Report Reticulum's interfaces and known paths.

    :param venv: Python environment holding rnstatus
    :param rnsconfig: the shared instance's config folder
    :param user: the user rnsd runs as
    :param problems: list to add problems to
    :return: HTML
    """
    output = run([f'{venv}/bin/rnstatus', '--config', rnsconfig, '-j'], user=user)
    try:
        status = json.loads(output) if output else None
    except ValueError:
        status = None
    if not status:
        problems.append('Reticulum is not answering')
        return '<h2>Reticulum</h2>\n' + table([('rnsd', span('bad', 'not answering'))])
    rows = [('Up for', duration(status.get('transport_uptime') or 0)), ('Known paths', str(status.get('tpcount', 0)))]
    programs = sum(1 for interface in status['interfaces'] if interface.get('type') == 'LocalClientInterface')
    rows.append(('Programs on this host', str(programs)))
    interfaces = []
    for interface in status['interfaces']:
        local = interface.get('type') in ('LocalClientInterface', 'LocalServerInterface')
        if local or interface.get('parent_interface_name'):
            continue
        up = interface.get('status')
        if not up:
            problems.append(f"interface {interface.get('short_name')} is down")
        signal = []
        if interface.get('rssi') is not None:
            signal.append(f"RSSI {interface['rssi']} dBm")
        if interface.get('snr') is not None:
            signal.append(f"SNR {interface['snr']} dB")
        clients = interface.get('clients')
        interfaces.append((html.escape(interface.get('short_name') or interface.get('name', '')),
                           span('ok', 'up') if up else span('bad', 'down'),
                           '' if clients is None else str(clients),
                           f"{size(interface.get('rxb', 0))} in, {size(interface.get('txb', 0))} out",
                           html.escape(', '.join(signal))))
    return ('<h2>Reticulum</h2>\n' + table(rows) + '\n'
            + table(interfaces, ('Interface', 'State', 'Clients', 'Traffic', 'Signal')))


def main():
    """Gather the checks and write the page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='page to write')
    parser.add_argument('--units', nargs='*', default=[], help='systemd units to report')
    parser.add_argument('--disks', nargs='*', default=['/'], help='folders whose disks to report')
    parser.add_argument('--venv', default='/opt/reticulum/venv', help='Python environment with rnstatus')
    parser.add_argument('--rnsconfig', default='/var/lib/reticulum/rns', help='shared Reticulum config folder')
    parser.add_argument('--user', default='reticulum', help='user rnsd runs as')
    parser.add_argument('--optional', nargs='*', default=[], help='units that may be stopped')
    parser.add_argument('--position', action='store_true', help='show the GPS position')
    args = parser.parse_args()

    problems = []
    sections = [services_section(args.units, args.optional, problems),
                reticulum_section(args.venv, args.rnsconfig, args.user, problems), time_section(problems),
                gps_section(args.position, problems), power_section(problems), system_section(args.disks, problems)]
    if problems:
        summary = span('bad', 'Needs attention: ') + html.escape('; '.join(problems))
    else:
        summary = span('ok', 'All checks pass')
    page = PAGE.format(name=html.escape(socket.gethostname()), when=html.escape(time.strftime('%Y-%m-%d %H:%M:%S %Z')),
                       summary=summary, sections='\n'.join(section for section in sections if section))
    temporary = args.out.with_name('.' + args.out.name + '.tmp')
    temporary.write_text(page, encoding='utf-8')
    temporary.chmod(0o644)
    os.replace(temporary, args.out)


if __name__ == '__main__':
    main()
