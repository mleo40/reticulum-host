#!/bin/sh
# Build the Raspberry Pi image in the build VM and copy it to build/.
# Usage: build-pi-image.sh [vm-name]
set -eu

# Raspberry Pi OS Lite (64-bit) the image is built from
raspios=2026-10-06-raspios-trixie-arm64-lite.img.xz
raspios_url=https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-10-06/$raspios
raspios_sha256=483db18a48da399b5b7022ffae9a07bc6d99daab30e593aedac09b69ff422843

here=$(cd "$(dirname "$0")" && pwd)
name=${1:-reticulum-build}
mkdir -p "$here/build"

if [ ! -f "$here/build/$raspios" ]; then
  curl -fL -o "$here/build/$raspios.part" "$raspios_url"
  mv "$here/build/$raspios.part" "$here/build/$raspios"
fi
echo "$raspios_sha256  $here/build/$raspios" | sha256sum -c -

# The VM can hold an old DHCP lease too; use the address that answers SSH
target=""
for address in $(virsh -c qemu:///system domifaddr "$name" | awk '/ipv4/ {sub("/.*", "", $4); print $4}'); do
  if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "build@$address" true 2> /dev/null; then
    target="build@$address"
    break
  fi
done
[ -n "$target" ] || { echo "Cannot reach VM $name over SSH; is it running?" >&2; exit 1; }

tar -C "$here" --exclude ./build --exclude ./.git --exclude ./.idea -czf - . | \
  ssh "$target" 'rm -rf reticulum-host && mkdir reticulum-host && tar -C reticulum-host -xzf -'
scp "$here/build/$raspios" "$target:"
ssh "$target" "sudo reticulum-host/pi/build-image.sh $raspios /home/build && rm -f $raspios && sudo chown build: /home/build/*.img.xz"
rm -f "$here/build/reticulum-host-pi-arm64.img.xz"
scp "$target:reticulum-host-pi-arm64.img.xz" "$here/build/"
echo "Built $here/build/reticulum-host-pi-arm64.img.xz"
