# ADR-001: SQLite as the default database

## Decision

Use SQLite with foreign keys, WAL mode, and a short busy timeout for the Windows local-first product.

## Reason

The first release is a single-user local workspace. SQLite avoids requiring PostgreSQL, Redis, or a separate service while still supporting transactions, migrations, full-text search later, and portable project backups.

## Constraint

All writes stay inside short transactions. Long-running indexing, review, and export work will use the persistent jobs table planned for a later phase. Multi-user collaboration and high write concurrency are outside the Windows 1.0 boundary.
