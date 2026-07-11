-- =============================================================================
-- daveLinK — Database Cleanup
-- =============================================================================
-- Purpose: Remove unused Django admin tables and clear all application data.
--
-- Usage:
--   psql $DATABASE_URL -f backend/scripts/cleanup-db.sql
--
-- What this does:
--   1. DROP unused system tables (empty, no functional purpose for this app)
--   2. DELETE all rows from remaining data tables (keeps structure intact)
--   3. Reset sequences so new IDs start fresh
-- =============================================================================

-- ── Step 1: Drop unused tables ──────────────────────────────────────────────
-- These Django admin tables are empty and provide no value for this URL
-- shortener. No groups, no group permissions, no user-level permissions
-- assignments, and no admin action log entries exist.
-- Order matters: child tables (with FKs) before parent tables.

DROP TABLE IF EXISTS auth_group_permissions      CASCADE;
DROP TABLE IF EXISTS auth_user_groups            CASCADE;
DROP TABLE IF EXISTS auth_user_user_permissions  CASCADE;
DROP TABLE IF EXISTS auth_group                  CASCADE;
DROP TABLE IF EXISTS django_admin_log            CASCADE;

-- ── Step 2: Clear data from remaining tables ────────────────────────────────
-- Order matters: clear child tables before parent tables (FK constraints).

-- Clear analytics BEFORE links (analytics.link_id → links.id)
DELETE FROM analytics;

-- Now clear links
DELETE FROM links;

-- Clear auth_permission BEFORE django_content_type (auth_permission.content_type_id → django_content_type.id)
DELETE FROM auth_permission;

-- Now content types can be cleared safely
DELETE FROM django_content_type;

-- Clear admin user & sessions
DELETE FROM auth_user;
DELETE FROM django_session;

-- ── Step 3: Reset sequences ─────────────────────────────────────────────────
-- So the first new ID starts at 1 again

ALTER SEQUENCE IF EXISTS links_id_seq                 RESTART WITH 1;
ALTER SEQUENCE IF EXISTS analytics_id_seq             RESTART WITH 1;
ALTER SEQUENCE IF EXISTS auth_user_id_seq             RESTART WITH 1;
ALTER SEQUENCE IF EXISTS auth_permission_id_seq       RESTART WITH 1;
ALTER SEQUENCE IF EXISTS django_content_type_id_seq   RESTART WITH 1;
