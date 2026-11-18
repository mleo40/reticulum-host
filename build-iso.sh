#!/bin/sh
# Build the live ISO in the build VM and copy it to build/.
# Usage: build-iso.sh [vm-name]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
name=${1:-reticulum-build}
# The VM can hold an old DHCP lease too; use the address that answers SSH
target=""
for address in $(virsh -c qemu:///system domifaddr "$name" | awk '/ipv4/ {sub("/.*", "", $4); print $4}'); do
  if ssh -o BatchMode=yes -o ConnectTimeout=5 "build@$address" true 2> /dev/null; then
    target="build@$address"
    break
  fi
done
[ -n "$target" ] || { echo "Cannot reach VM $name over SSH; is it running?" >&2; exit 1; }

tar -C "$here" --exclude ./build --exclude ./.git --exclude ./.idea -czf - . | \
  ssh "$target" 'rm -rf reticulum-host && mkdir reticulum-host && tar -C reticulum-host -xzf -'
ssh "$target" 'sudo reticulum-host/live-build/build.sh /home/build && sudo chown build: /home/build/*.iso'
mkdir -p "$here/build"
scp "$target:reticulum-host-amd64.hybrid.iso" "$here/build/"
echo "Built $here/build/reticulum-host-amd64.hybrid.iso"
