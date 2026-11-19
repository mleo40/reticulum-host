# Using a Reticulum host

For people who connect to a Reticulum host with a phone or computer: how to reach it, and which app to use for each
service. You never log in to the host itself. The person who runs it is called the operator below.

## The host's addresses

On the same network as the host, open its web page in a browser: <http://reticulum-host.local/>. It lists the host's
addresses, written when it last started, followed by this guide. If that name does not open, use the host's IP
address instead, such as `http://192.168.1.20/`; the operator can read it from the host's login banner or the
router's list of connected devices.

Each service on the host has its own address, 32 characters long, such as `0e4118a2242aef7d92e41be8c57aa3b8`. Copy
them exactly.

| Line | What it is | App |
|---|---|---|
| TCP interface | The host's IP address and port, for connecting over a network | Any Reticulum app |
| Web page | This page and the shared files | Any web browser |
| LXMF propagation | Holds your messages while you are offline | Sideband, MeshChat, Columba |
| RetiBBS | Bulletin board and chat rooms | RetiBBS client |
| Partyline voice | Voice rooms | Partyline |
| Nomad Network pages | Text pages, when the operator has turned them on | MeshChat, Nomad Network |
| Git repositories | Git repositories | `git` with Reticulum installed |

The transport identity and git node pages lines are for operators.

A host started from a USB stick without installing ("live") gets new addresses every time it starts. Open the page
again after a restart.

## Reach the host

**On the same Wi-Fi or wired network as the host**, apps find it by themselves. If an app has its own network
settings, as Sideband and MeshChat do, check that its local network interface (also called AutoInterface) is on.

**Over another network or the internet**, or when the local network keeps devices apart (common on guest Wi-Fi), add a
TCP client connection to the host's TCP interface line, such as `192.168.1.20` port `4242`, in the app's network
settings.

The Python programs below (the RetiBBS client, Partyline, Nomad Network and `git`) share one Reticulum config,
`~/.reticulum/config`, created the first time one of them runs. To connect them over TCP, add this under
`[interfaces]` and start the program again:

```ini
  [[Reticulum host]]
    type = TCPClientInterface
    enabled = yes
    target_host = 192.168.1.20
    target_port = 4242
```

**Over radio**, when the host has a LoRa radio, you need a radio (an RNode) set to the same frequency and settings.
Ask the operator for them.

## Messages

Use [Sideband](https://github.com/markqvist/Sideband) (Android, Linux, Windows, macOS),
[MeshChat](https://github.com/liamcottle/reticulum-meshchat) (Windows, macOS, Linux) or
[Columba](https://github.com/torlando-tech/columba) (Android).

In the app's settings, set the propagation node to the host's LXMF propagation address. Messages sent to you while
you are offline then wait on the host, and arrive when you next connect. Messages are encrypted end to end; the host
cannot read them.

## Bulletin board

Install the [RetiBBS client](https://github.com/mleo40/retibbs_client) (Linux, Windows, macOS); its README has the
steps.

1. Open it and choose Server > Connect.
2. Paste the RetiBBS address, or pick the board under Heard on the network.
3. The first time, pick a display name. The board keeps your account under your client's identity.

To hear about new posts on boards you follow, put your messaging app's LXMF address in Settings > Board alerts, then
right click a board and turn on alerts. Alerts arrive as messages in that app.

## Voice rooms

Install [Partyline](https://github.com/RFnexus/partyline), which needs Python 3.11 or newer:

```bash
pipx install partyline
partyline
```

Choose Connect, add the server by its Partyline voice address, and double click a room. Lobby uses more bandwidth
and sounds better; Low bandwidth works over slow links such as radio.

## Shared files

On the host's web page, choose Shared files, or open <http://reticulum-host.local/files/>, and download what you need.
Everything there is public; you cannot upload.

## More on the web page

- **Host health** shows whether the host and its services are working.
- **Offline library**, on hosts that have one, holds offline copies of Wikipedia, medical and repair guides and
  more, searchable in the browser.
- **Time:** when there is no internet, a laptop can set its clock from the host. Set its time (NTP) server to
  `reticulum-host.local`.

## Pages

When the operator has turned them on, open the Nomad Network pages address in MeshChat or
[Nomad Network](https://github.com/markqvist/NomadNet). Pages and files load more slowly over radio than over Wi-Fi.

## Git repositories

With Reticulum installed (`pipx install rns`), clone with the Git repositories address and the repository's path,
which the operator gives you:

```bash
git clone rns://<Git repositories address>/public/myproject
```

## When something does not work

- **The app finds nothing:** check you are on the host's network, or that the TCP connection names the right IP
  address and port 4242. Guest and hotel Wi-Fi often keeps devices apart; use TCP there.
- **An address is not found:** right after the host or your app starts, give it a minute, then try again. Check the
  address for typos.
- **The web page does not open:** `.local` names work on most phones and computers, but not all; use the host's IP
  address instead. A second host on the same network answers to `reticulum-host-2.local`.
- **It worked yesterday:** a live host has new addresses after each restart. Open the web page again.
