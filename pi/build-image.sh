#!/bin/sh
# Build a Reticulum host SD card image for 64-bit Raspberry Pi from Raspberry Pi OS Lite.
# Run as root on Debian 13 (any CPU); arm64 programs in the image run through qemu-user-static.
# Usage: build-image.sh <raspios-lite-arm64.img.xz> [output-dir]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
source_image=$1
output=${2:-$here/..}
work=/var/tmp/reticulum-pi
image=$work/reticulum-host-pi-arm64.img
mnt=$work/mnt
grow=3G

[ "$(id -u)" = 0 ] || { echo "Run as root" >&2; exit 1; }

missing=""
for tool in qemu-aarch64-static:qemu-user-static parted:parted resize2fs:e2fsprogs xz:xz-utils; do
  command -v "${tool%%:*}" > /dev/null || missing="$missing ${tool#*:}"
done
if [ -n "$missing" ]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y $missing
fi
[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || systemctl restart systemd-binfmt
[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ] || { echo "arm64 emulation is not registered" >&2; exit 1; }

loop=""
cleanup() {
  for path in dev/pts dev/shm dev proc sys boot/firmware ""; do
    mountpoint -q "$mnt/$path" 2> /dev/null && umount -l "$mnt/$path"
  done
  [ -n "$loop" ] && losetup -d "$loop" 2> /dev/null
  return 0
}
trap cleanup EXIT

rm -rf "$work"
mkdir -p "$mnt"
echo "Unpacking $source_image"
xz -dc "$source_image" > "$image"

# Room for the software; Raspberry Pi OS grows the root file system to the whole card on first boot
truncate -s "+$grow" "$image"
parted -s "$image" resizepart 2 100%
loop=$(losetup -P --show -f "$image")
e2fsck -fy "${loop}p2" > /dev/null || [ $? -le 1 ]
resize2fs "${loop}p2"

mount "${loop}p2" "$mnt"
mount "${loop}p1" "$mnt/boot/firmware"
mount --bind /dev "$mnt/dev"
mount --bind /dev/pts "$mnt/dev/pts"
mount -t tmpfs tmpfs "$mnt/dev/shm"
mount -t proc proc "$mnt/proc"
mount -t sysfs sys "$mnt/sys"

# Name resolution for apt and pip, and no services starting inside the build
cp -P "$mnt/etc/resolv.conf" "$work/resolv.conf.orig"
rm -f "$mnt/etc/resolv.conf"
cp /etc/resolv.conf "$mnt/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$mnt/usr/sbin/policy-rc.d"
chmod 755 "$mnt/usr/sbin/policy-rc.d"

mkdir -p "$mnt/opt/reticulum-host"
cp -a "$here/../ansible" "$mnt/opt/reticulum-host/"
cp "$here/../live-build/config/includes.chroot/etc/systemd/system/ssh-hostkeys.service" "$mnt/etc/systemd/system/"
cp "$here/../live-build/config/hooks/normal/9990-purge-identifiers.hook.chroot" "$mnt/tmp/purge-identifiers"

chroot "$mnt" /bin/sh -eu -c '
  export DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
  apt-get update
  apt-get install -y ansible
  cd /opt/reticulum-host/ansible
  ansible-playbook -i localhost, -c local site.yml -e "{\"reticulum_host_image_build\": true}"
  systemctl enable ssh-hostkeys.service
  apt-get clean
  rm -rf /var/lib/apt/lists/* /root/.cache /root/.ansible
  sh /tmp/purge-identifiers
  rm -f /tmp/purge-identifiers
'

rm -f "$mnt/usr/sbin/policy-rc.d" "$mnt/etc/resolv.conf"
cp -P "$work/resolv.conf.orig" "$mnt/etc/resolv.conf"

# Check the finished file system, not only the build steps
found=$(cd "$mnt" && find etc/ssh root var/lib/reticulum -regextype posix-extended \
  -regex 'etc/ssh/ssh_host_[a-z0-9]+_key(\.pub)?|root/\.reticulum(/.*)?|var/lib/reticulum/.*(identity|\.pem|/storage(/.*)?)' \
  -print 2> /dev/null || true)
machine_id=$(cat "$mnt/etc/machine-id" 2> /dev/null || true)
if [ -n "$found" ] || { [ -n "$machine_id" ] && [ "$machine_id" != uninitialized ]; }; then
  echo "Image holds per-machine identifiers:" >&2
  echo "$found machine-id=$machine_id" >&2
  exit 1
fi

cleanup
loop=""
echo "Compressing"
xz -T0 -f "$image"
cp "$image.xz" "$output/"
echo "Built $output/$(basename "$image").xz"
