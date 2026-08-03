# Implementation Plan: MySQL to PostgreSQL Migration

## Overview

This plan implements the migration from MySQL to PostgreSQL for the Navigo backend. The migration replaces aiomysql with asyncpg, converts all SQL schemas and queries to PostgreSQL syntax, and ensures complete functional compatibility. The implementation follows a systematic approach: dependencies, configuration, connection management, migrations, service layer updates, and deployment.

## Tasks

- [ ] 1. Update project dependencies and configuration
  - [ ] 1.1 Update requirements.txt to use asyncpg
    - Remove aiomysql and PyMySQL dependencies
    - Add asyncpg==0.29.0 or higher
    - _Requirements: 1.1, 1.2_
  
  - [ ] 1.2 Update configuration to support PostgreSQL connection parameters
    - Add database_url field for Render's DATABASE_URL environment variable
    - Add postgres_* fields (host, port, user, password, database) with defaults
    - Add environment field to control database creation behavior
    - Implement db_config computed property for URL parsing
    - Parse postgresql://user:password@host:port/database format
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 2. Checkpoint - Verify configuration changes
  - Ensure configuration loads correctly with both DATABASE_URL and individual parameters, ask the user if questions arise.

- [ ] 3. Update database connection management
  - [ ] 3.1 Replace aiomysql with asyncpg in Database class
    - Replace aiomysql imports with asyncpg
    - Update connect() method to use asyncpg.create_pool()
    - Update pool parameter names (minsize → min_size, maxsize → max_size)
    - Add conditional database creation for local development only
    - Implement _ensure_database_exists_local() method
    - Update disconnect() method for asyncpg
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 7.1, 7.2_

- [ ] 4. Update migration runner for PostgreSQL
  - [ ] 4.1 Convert MigrationRunner to use asyncpg transaction API
    - Replace aiomysql imports with asyncpg
    - Update parameterization from %s to $1, $2 format
    - Use connection.transaction() context manager
    - Replace cursor-based API with connection-based API
    - Update _ensure_migrations_table() to remove MySQL clauses
    - Update _apply_migration() to use asyncpg patterns
    - _Requirements: 4.1, 4.2, 7.3, 7.4, 7.5, 7.6, 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 5. Checkpoint - Verify database connection and migration runner
  - Test database connection with local PostgreSQL, verify migrations table creation, ask the user if questions arise.

- [ ] 6. Convert schema migration files to PostgreSQL syntax
  - [ ] 6.1 Convert 001_create_users_table.sql to PostgreSQL
    - Replace BIGINT UNSIGNED AUTO_INCREMENT with BIGSERIAL
    - Remove ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 clauses
    - Verify column types and constraints are PostgreSQL-compatible
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.8, 3.9, 12.1, 12.2_
  
  - [ ] 6.2 Convert 002_add_community_safety_tables.sql to PostgreSQL
    - Replace BIGINT UNSIGNED AUTO_INCREMENT with BIGSERIAL for all tables
    - Replace TINYINT UNSIGNED with SMALLINT and CHECK constraints
    - Replace INT UNSIGNED with INTEGER and CHECK constraints
    - Convert ON DUPLICATE KEY UPDATE to ON CONFLICT DO UPDATE
    - Add trigger function for ON UPDATE CURRENT_TIMESTAMP behavior
    - Remove all ENGINE and CHARSET clauses
    - Verify all indexes and foreign keys are preserved
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 12.3, 12.4, 12.5, 12.7_

- [ ] 7. Checkpoint - Verify schema migrations
  - Apply migrations to local PostgreSQL, verify all tables created correctly, ask the user if questions arise.

- [ ] 8. Update AuthService queries for PostgreSQL
  - [ ] 8.1 Update user signup to use PostgreSQL patterns
    - Remove DictCursor import
    - Update parameterization from %s to $1, $2, $3
    - Add RETURNING id clause to INSERT statement
    - Use connection.fetchval() for ID retrieval instead of cursor.lastrowid
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 5.1, 5.2, 5.3, 8.2_
  
  - [ ] 8.2 Update user authentication and lookup queries
    - Update login() method parameterization to use $1
    - Update get_user_by_id() to use $1 and connection.fetchrow()
    - Update _get_user_by_email() to use $1 and connection.fetchrow()
    - Replace DictCursor usage with asyncpg Record objects
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ]* 8.3 Write unit tests for AuthService
  - Test user signup with valid data returns user ID and token
  - Test user signup with duplicate email raises error
  - Test user login with correct credentials returns token
  - Test user login with incorrect password raises error
  - _Requirements: 13.1, 13.2, 13.7_

- [ ] 9. Update CommunityService queries for PostgreSQL
  - [ ] 9.1 Update favorite places operations
    - Update add_favorite_place() to use $N parameterization
    - Convert ON DUPLICATE KEY UPDATE to ON CONFLICT DO UPDATE
    - Update list_favorite_places() to use connection.fetch()
    - Update get_favorite_place() to use connection.fetchrow()
    - Update remove_favorite_place() parameterization
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 3.5_
  
  - [ ] 9.2 Update place rating operations
    - Update add_place_rating() parameterization to $N format
    - Update get_place_safety_summary() parameterization
    - Use connection.fetch() for result retrieval
    - Verify AVG() calculations preserve precision
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.2, 8.3_
  
  - [ ] 9.3 Update road segment rating operations
    - Update add_road_rating() parameterization to $N format
    - Add connection.transaction() context manager
    - Update _refresh_segment_scores() parameterization
    - Use connection.fetchrow() for aggregate queries
    - Convert upsert to ON CONFLICT DO UPDATE with updated_at
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 3.5, 9.1, 9.2_
  
  - [ ] 9.4 Update road safety summary with dynamic IN clause
    - Fix get_road_safety_summary() placeholder generation
    - Generate PostgreSQL placeholders: $1, $2, $3, ... for dynamic segment_keys list
    - Pass parameters as *segment_keys instead of tuple
    - Use connection.fetch() for result retrieval
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.4_
  
  - [ ] 9.5 Update comment operations
    - Update add_comment() to use $N parameterization
    - Add RETURNING id clause and use connection.fetchval()
    - Update list_comments() parameterization and use connection.fetch()
    - Update list_user_comments() parameterization
    - Update list_nearby_comments() parameterization
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3_

- [ ]* 9.6 Write unit tests for CommunityService
  - Test adding favorite place returns place ID
  - Test adding duplicate favorite updates existing record
  - Test listing favorites returns correct order
  - Test adding place rating updates safety summary
  - Test adding road rating updates segment scores
  - Test adding comment returns comment ID
  - _Requirements: 13.3, 13.4, 13.5, 13.6, 13.7_

- [ ] 10. Checkpoint - Verify all service layer updates
  - Run local tests, verify all database operations work correctly, ask the user if questions arise.

- [ ]* 11. Integration and API contract testing
  - [ ]* 11.1 Write integration tests
    - Test complete signup → login → add favorite workflow
    - Test foreign key cascade (delete user → favorites deleted)
    - Test unique constraint enforcement
    - Test transaction rollback on error
    - _Requirements: 13.7_
  
  - [ ]* 11.2 Write API contract tests
    - Compare signup response schema against expected format
    - Compare login response schema
    - Compare favorites list response schema
    - Compare safety summary response schema
    - Compare comments list response schema
    - Verify all data types match (user IDs, coordinates, timestamps)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  
  - [ ]* 11.3 Write data precision tests
    - Test coordinate precision preserved (DECIMAL(10,7))
    - Test rating calculations produce correct normalized_score
    - Test timestamp formatting matches expected format
    - _Requirements: 8.3, 12.2, 12.7_

- [ ] 12. Create deployment documentation
  - [ ] 12.1 Document local PostgreSQL setup
    - Provide Docker Compose configuration for local PostgreSQL
    - Document native PostgreSQL installation options
    - Document .env file configuration for local development
    - Include verification steps for local setup
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  
  - [ ] 12.2 Document Render deployment process
    - Document how to create PostgreSQL database on Render
    - List all required environment variables for Render
    - Provide DATABASE_URL format and example values
    - Document migration execution on first deployment
    - Include verification steps for successful deployment
    - Provide rollback instructions if deployment fails
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 13. Final checkpoint - End-to-end verification
  - Deploy to Render staging, test all API endpoints, verify migrations applied, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional testing tasks and can be skipped for faster delivery
- Each task references specific requirements from requirements.md for traceability
- Checkpoints ensure incremental validation at key milestones
- The migration maintains complete API compatibility with existing frontend
- PostgreSQL-specific patterns (RETURNING, ON CONFLICT, $N parameters) are used throughout
- Transaction handling ensures data consistency during migrations and multi-step operations
- Documentation enables both local development and production deployment on Render

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["3.1", "4.1"] },
    { "id": 2, "tasks": ["6.1", "6.2"] },
    { "id": 3, "tasks": ["8.1", "8.2"] },
    { "id": 4, "tasks": ["8.3", "9.1", "9.2"] },
    { "id": 5, "tasks": ["9.3", "9.4", "9.5"] },
    { "id": 6, "tasks": ["9.6"] },
    { "id": 7, "tasks": ["11.1", "11.2", "11.3", "12.1", "12.2"] }
  ]
}
```
