# ADR 0010 · Migraciones en proceso aparte y `pk` asignados por la aplicación

Estado: aceptada · 20/10/2026

## Contexto

1. Importar Alembic (y Mako) cuesta memoria que, en un proceso de larga vida, no se libera. En la Pi Zero 2 W cada megabyte cuenta (ADR 0003).
2. El escritor por lotes (11.3) escribe cada 2 s. Las recepciones, posiciones y mensajes referencian el `pk` del paquete, y los eventos SSE de mensajes llevan su `pk` antes de que el lote llegue a la base.

## Decisión

1. `meshbox.store.migrate.pending()` consulta `alembic_version` solo con `sqlite3`. Si hay migraciones pendientes, el servicio ejecuta `python -m meshbox migrate` como subproceso (respaldo `-pre-<versión>`, `upgrade`, restauración si falla). En la Pi la unidad systemd además corre `meshbox migrate` en `ExecStartPre`.
2. Los `pk` de `packets`, `messages` y `alert_events` los asigna la aplicación con contadores que arrancan en el máximo de la base. Si un paquete ya estaba guardado (por ejemplo, un duplicado que llega tras un reinicio con la caché de deduplicación vacía), el escritor detecta `INSERT OR IGNORE` sin efecto, busca el `pk` existente y redirige las operaciones dependientes del mismo lote y de los siguientes. Al arrancar, además, la caché de deduplicación se carga con los paquetes de los últimos 30 minutos.
3. La migración 0001 agrega dos índices que el plan no lista, `ix_traceroutes_ts` e `ix_audit_log_ts`, necesarios para la retención y los listados por fecha.

## Consecuencias

- Alembic no queda en la memoria del servicio.
- Una prueba (`test_duplicate_after_restart_reuses_pk`) cubre el caso del duplicado tras reiniciar sin violar claves foráneas.
- Si en el futuro hubiera dos escritores, los contadores dejarían de ser seguros: el plan ya exige un único escritor (11.1).
