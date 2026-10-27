# ADR 0006 · Límite de memoria sin controlador de cgroup

Estado: aceptada · 20/10/2026

## Contexto

El plan limita el servicio con `MemoryHigh=200M` y `MemoryMax=280M` (5.5, 13.4). En la Raspberry Pi Zero 2 W el firmware arranca el kernel con `cgroup_disable=memory` (no figura en `cmdline.txt`: lo agrega el cargador). Sin el controlador de memoria, systemd acepta esas líneas pero no las aplica. Además, la RAM visible es 415 MiB, no 512 MB, porque `gpu_mem=64`.

## Decisión

1. Las unidades conservan `MemoryHigh` y `MemoryMax` (se aplican si el controlador está activo).
2. La aplicación tiene su propia guardia: mide su RSS cada 10 s; si supera `[limits] rss_soft_mb` (200) emite una alerta de sistema y vacía cachés; si supera `rss_hard_mb` (280) registra el motivo y sale con código distinto de cero, y systemd la reinicia (`Restart=always`).
3. Se documenta, como recomendación opcional y con reinicio, agregar `cgroup_enable=memory` a `/boot/firmware/cmdline.txt` y `gpu_mem=16` a `/boot/firmware/config.txt` (recupera unos 48 MB en un equipo sin pantalla). El instalador no lo hace solo: en un equipo compartido reiniciar corta los demás servicios.

## Consecuencias

El límite duro queda garantizado por la propia aplicación aunque el kernel no tenga el controlador; con el controlador activo hay doble protección.
