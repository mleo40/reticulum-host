#!/bin/sh
# Build the Reticulum host live ISO. Run as root on Debian 13 with live-build installed.
# Usage: build.sh [output-dir] [host|offgrid]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
output=${1:-$here/..}
profile=${2:-host}
work=/var/tmp/reticulum-live
case "$profile" in
  host) playbook=site.yml ;;
  offgrid) playbook=offgrid.yml ;;
  *) echo "Unknown profile $profile; use host or offgrid" >&2; exit 1 ;;
esac
name=reticulum-$profile

if [ -d "$work" ]; then
  (cd "$work" && lb clean --purge)
  rm -rf "$work"
fi
mkdir -p "$work"
cd "$work"

lb config --distribution trixie --archive-areas "main non-free-firmware" --apt-recommends false \
  --debian-installer live --debian-installer-gui false --memtest none \
  --iso-volume RETICULUM_HOST --image-name "$name" \
  --bootappend-live "boot=live components hostname=reticulum-host username=rnsadmin persistence"
cp -a "$here/config/." config/
mkdir -p config/includes.chroot/opt/reticulum-host
cp -a "$here/../ansible" config/includes.chroot/opt/reticulum-host/
echo "$playbook" > config/includes.chroot/opt/reticulum-host/playbook

lb build

# Check the finished image, not only the build steps
iso=$name-amd64.hybrid.iso
ssh_keys='etc/ssh/ssh_host_[a-z0-9]+_key(\.pub)?'
reticulum='root/\.reticulum(/.*)?|var/lib/reticulum/.*(identity|\.pem)|var/lib/reticulum/rns/storage(/.*)?'
identifiers="^squashfs-root/($ssh_keys|$reticulum)\$"
found=$(unsquashfs -l binary/live/filesystem.squashfs | grep -E "$identifiers" || true)
machine_id=$(unsquashfs -cat binary/live/filesystem.squashfs etc/machine-id)
if [ -n "$found" ] || [ -n "$machine_id" ]; then
  echo "Image holds per-machine identifiers:" >&2
  echo "$found machine-id=$machine_id" >&2
  exit 1
fi

cp "$iso" "$output/"
echo "Built $output/$iso"
