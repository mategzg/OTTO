# Domain: external_ingest

## Purpose

Hub ruteable para conocimiento asimilado del dominio `external_ingest`.

## Use when

- Existe un source pendiente recomendado para este dominio.
- Necesitas navegar cards y nodos derivados sin leer el crudo.

## Avoid when

- No hay fuentes asimiladas para este dominio.
- Necesitas acceso literal al crudo (usar vault/inbox_raw/_processed).

## Routing

- Entrar por este hub, luego abrir `sources/*_index.md` y cards asociadas.
- Para operacion general OpenClaw: `brain/domains/openclaw_ops/00_INDEX.md`.

## Maintenance

- Actualizar por plan/apply del ingest router.

## Links

- `brain/domains/ingest/00_INDEX.md`
- `brain/cards/`
