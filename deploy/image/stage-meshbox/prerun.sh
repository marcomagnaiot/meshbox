#!/bin/bash -e
# Stage de pi-gen de meshbox (24.1): parte del rootfs del stage anterior (stage2, Lite).

if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
