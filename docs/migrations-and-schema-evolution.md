# Migrations And Schema Evolution

This document explains how persistent model changes should move through the
RetainAI codebase.

The project uses SQLAlchemy models with Alembic migrations. Because many fields
surface all the way up to API contracts, UI views, exports, and evaluation
artifacts, schema changes are rarely isolated.

## Where Schema Logic Lives

Primary files:

- ORM models: `apps/api/app/models.py`
- Alembic config: `apps/api/alembic.ini`
- Alembic environment: `apps/api/alembic/env.py`
- Migration versions: `apps/api/alembic/versions/`

## Standard Change Sequence

When adding or changing persisted fields, follow this order:

1. update the SQLAlchemy model in `models.py`
2. add or edit the Alembic migration
3. update Pydantic schemas in `schemas.py` if the field is exposed by the API
4. update frontend types in `apps/web/src/types.ts` if the UI consumes it
5. update any affected service logic
6. update seed data if local demo coverage matters
7. update docs if the field changes visible product behavior

## Why This Matters More Here Than In A Typical App

RetainAI uses one datastore for:

- operational case data
- evaluation records
- job records
- governance artifacts
- model metadata

That means schema changes often have second-order effects:

- a new field may need to be masked in exports
- a renamed field may break evaluation persistence
- a deleted field may invalidate frontend assumptions or seed flows

## Categories Of Schema Change

### Operational workflow changes

Examples:

- intervention workflow fields
- assignment or escalation fields
- label-definition settings

Check:

- queue UI
- exports
- evaluation and shadow-run logic

### Governance and privacy changes

Examples:

- consent fields
- tokenization fields
- export policy flags

Check:

- governance services
- export endpoints
- audit logs

### Model and evaluation changes

Examples:

- new metrics
- new feature snapshots
- new bias-audit or drift fields

Check:

- model status payloads
- evaluation persistence
- frontend validation views

## Migration Discipline

The safest pattern is:

- keep migrations explicit
- avoid mixing unrelated schema changes into one revision
- update docs alongside changes that affect user-visible behavior

For major releases or handoff preparation, maintainers should verify:

- clean upgrade from the current baseline
- application startup after migration
- test suite still passes against the migrated schema

## Common Risks

- forgetting to update `schemas.py`
- forgetting to update `types.ts`
- forgetting seed defaults for new non-nullable fields
- changing a field used in exports without reviewing privacy implications
- changing evaluation-related tables without reviewing historical report
  compatibility

## Related Documents

- [Backend Code Reference](backend-code-reference.md)
- [Data Model Reference](data-model-reference.md)
- [Testing and Quality Reference](testing-and-quality-reference.md)
