#!/bin/sh
# Build the live ISO in the build VM and copy it to build/.
# Usage: build-iso.sh [host|offgrid] [vm-name]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
profile=${1:-host}
name=${2:-reticulum-build}
case "$profile" in host | offgrid) ;; *) echo "Unknown profile $profile; use host or offgrid" >&2; exit 1 ;; esac
iso=reticulum-$profile-amd64.hybrid.iso
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
ssh "$target" "sudo reticulum-host/live-build/build.sh /home/build $profile && sudo chown build: /home/build/*.iso"
mkdir -p "$here/build"
# A VM that booted the previous ISO leaves it owned by libvirt; replace rather than overwrite
rm -f "$here/build/$iso"
scp "$target:$iso" "$here/build/"
echo "Built $here/build/$iso"
