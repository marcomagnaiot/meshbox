#!/bin/bash -e
# Instala meshbox en la imagen (24.1): copia al rootfs el paquete firmado del release (que
# release.yml deja en files/ junto con SHA256SUMS y SHA256SUMS.sig) y ejecuta
# install.sh --image --appliance dentro del chroot. La firma se verifica igual que en la Pi.

shopt -s nullglob
tarballs=(files/meshbox-*-linux-aarch64.tar.gz)
if [ "${#tarballs[@]}" -ne 1 ]; then
	echo "stage-meshbox: se esperaba exactamente un paquete meshbox-*-linux-aarch64.tar.gz en files/" >&2
	exit 1
fi
for required in files/SHA256SUMS files/SHA256SUMS.sig; do
	if [ ! -f "${required}" ]; then
		echo "stage-meshbox: falta ${required}" >&2
		exit 1
	fi
done

tarball=$(basename "${tarballs[0]}")
version=${tarball#meshbox-}
version=${version%-linux-aarch64.tar.gz}
staging=/opt/meshbox/.staging/image

install -d -m 0700 "${ROOTFS_DIR}${staging}"
install -m 0644 "files/${tarball}" files/SHA256SUMS files/SHA256SUMS.sig "${ROOTFS_DIR}${staging}/"
tar -xzf "files/${tarball}" -C "${ROOTFS_DIR}${staging}" "meshbox-${version}/install.sh"

on_chroot <<EOF
set -e
bash ${staging}/meshbox-${version}/install.sh --image --appliance --from ${staging}/${tarball}
EOF

rm -rf "${ROOTFS_DIR}${staging}"
