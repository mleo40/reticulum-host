#!/bin/sh
# Create the minimal Debian 13 libvirt VM that builds the ISO.
# Usage: build-vm.sh <debian-13-netinst.iso> [vm-name]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
iso=$(realpath "$1")
name=${2:-reticulum-build}
work="$here/../build/vm-$name"
rm -rf "$work" && mkdir -p "$work"

# Public keys allowed to log in as the build user
cat ${SSH_PUBKEYS:-"$HOME"/.ssh/*.pub} > "$work/authorized_keys"
cp "$here/preseed.cfg.in" "$work/preseed.cfg"

virt-install --connect qemu:///system --name "$name" --memory 4096 --vcpus 4 --osinfo debian13 \
  --disk size=30,format=qcow2 --network network=default --graphics none --noautoconsole --wait -1 \
  --location "$iso" --initrd-inject "$work/preseed.cfg" --initrd-inject "$work/authorized_keys" \
  --extra-args "auto=true priority=critical preseed/file=/preseed.cfg console=ttyS0,115200n8"
