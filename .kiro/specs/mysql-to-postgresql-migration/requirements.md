# Requirements Document

## Introduction

This document specifies requirements for migrating the Navigo backend from MySQL to PostgreSQL to enable deployment on Render's free PostgreSQL tier. The migration involves replacing the aiomysql driver with asyncpg, converting SQL schemas and queries to PostgreSQL syntax, and ensuring all existing functionality is preserved without data loss.

## Glossary

- **Backend_System**: The FastAPI-based Navigo backend application that handles user authentication, community safety ratings, and route selection
- **Database_Driver**: The async database library used to connect to and query the database (currently aiomysql, target asyncpg)
- **Migration_Runner**: The component that executes SQL migration files to create and update database schemas
- **Connection_Pool**: The pool of database connections maintained for efficient query execution
- **Schema_Migration**: SQL file that defines database tables, indexes, and constraints
- **Query_Parameterization**: The method of safely binding values to SQL queries (MySQL uses %s, PostgreSQL uses $1, $2, etc.)
- **Render**: Cloud platform providing managed PostgreSQL database service
- **API_Contract**: The input/output interface of REST API endpoints that clients depend on

## Requirements

### Requirement 1: Replace Database Driver

**User Story:** As a backend developer, I want to replace aiomysql with asyncpg, so that the application can connect to PostgreSQL databases.

#### Acceptance Criteria

1. THE Backend_System SHALL use asyncpg version 0.29.0 or higher as the Database_Driver
2. THE Backend_System SHALL remove aiomysql and PyMySQL dependencies from requirements.txt
3. WHEN the Backend_System starts, THE Connection_Pool SHALL connect to PostgreSQL using asyncpg
4. THE Connection_Pool SHALL maintain between 1 and 10 concurrent connections
5. WHEN a database query is executed, THE Backend_System SHALL use asyncpg's connection acquisition and cursor API
6. THE Backend_System SHALL configure asyncpg connections with autocommit behavior equivalent to the current aiomysql setup

### Requirement 2: Update Database Configuration

**User Story:** As a backend developer, I want to update configuration for PostgreSQL, so that connection settings work with both local development and Render deployment.

#### Acceptance Criteria

1. THE Backend_System SHALL accept DATABASE_URL environment variable for PostgreSQL connection string
2. WHERE DATABASE_URL is not provided, THE Backend_System SHALL construct connection parameters from individual environment variables (host, port, user, password, database)
3. THE Backend_System SHALL use default PostgreSQL port 5432 when not specified
4. THE Backend_System SHALL replace MYSQL_* environment variable names with DATABASE_* or POSTGRES_* prefixes
5. WHEN connecting to Render PostgreSQL, THE Backend_System SHALL parse DATABASE_URL format: postgresql://user:password@host:port/database
6. THE Backend_System SHALL maintain backward compatibility by supporting both individual parameters and connection URL

### Requirement 3: Convert Schema Migrations to PostgreSQL Syntax

**User Story:** As a backend developer, I want PostgreSQL-compatible migration files, so that the database schema can be created correctly.

#### Acceptance Criteria

1. THE Migration_Runner SHALL convert BIGINT UNSIGNED to BIGINT with CHECK constraints for non-negative values
2. THE Migration_Runner SHALL replace AUTO_INCREMENT with SERIAL or BIGSERIAL for primary key columns
3. THE Migration_Runner SHALL remove ENGINE=InnoDB clauses from CREATE TABLE statements
4. THE Migration_Runner SHALL remove DEFAULT CHARSET=utf8mb4 clauses from CREATE TABLE statements
5. THE Migration_Runner SHALL replace ON DUPLICATE KEY UPDATE syntax with ON CONFLICT DO UPDATE for upsert operations
6. THE Migration_Runner SHALL convert TIMESTAMP DEFAULT CURRENT_TIMESTAMP to TIMESTAMP DEFAULT CURRENT_TIMESTAMP for created_at columns
7. THE Migration_Runner SHALL convert TIMESTAMP ON UPDATE CURRENT_TIMESTAMP to use triggers or application-level updates for updated_at columns
8. THE Migration_Runner SHALL preserve all column names, data types, constraints, indexes, and foreign key relationships
9. FOR ALL Schema_Migrations, applying migrations to PostgreSQL SHALL produce equivalent table structures to the original MySQL schema

### Requirement 4: Update Query Parameterization

**User Story:** As a backend developer, I want queries to use PostgreSQL parameterization, so that SQL injection is prevented and queries execute correctly.

#### Acceptance Criteria

1. WHEN executing parameterized queries, THE Backend_System SHALL use PostgreSQL positional parameters ($1, $2, $3...) instead of %s placeholders
2. THE Backend_System SHALL convert all occurrences of %s in SQL query strings to sequential $N format
3. THE Backend_System SHALL maintain the same parameter order and tuple structure when passing values to asyncpg
4. FOR ALL database queries in auth_service.py and community_service.py, parameterization SHALL be PostgreSQL-compatible
5. WHEN using DictCursor equivalent, THE Backend_System SHALL use asyncpg's Record objects and access columns by name

### Requirement 5: Handle Auto-Increment ID Retrieval

**User Story:** As a backend developer, I want to retrieve inserted record IDs, so that the application can return newly created resources to clients.

#### Acceptance Criteria

1. WHEN inserting a record with SERIAL/BIGSERIAL primary key, THE Backend_System SHALL retrieve the generated ID using RETURNING id clause
2. THE Backend_System SHALL replace cursor.lastrowid access with explicit RETURNING clause results
3. FOR ALL INSERT operations that require the new ID (user signup, favorite place creation, comment creation), THE Backend_System SHALL successfully return the generated ID value
4. THE Backend_System SHALL maintain the same integer ID type in response schemas

### Requirement 6: Update MySQL-Specific SQL Functions

**User Story:** As a backend developer, I want queries to use PostgreSQL functions, so that aggregations and calculations execute correctly.

#### Acceptance Criteria

1. THE Backend_System SHALL replace COALESCE usage where MySQL-specific behavior differs with PostgreSQL equivalents
2. WHEN calculating average ratings, THE Backend_System SHALL use PostgreSQL's AVG() function with appropriate type casting
3. THE Backend_System SHALL verify that LIMIT, ORDER BY, and JOIN clauses function identically in PostgreSQL
4. WHERE dynamic placeholders are constructed (e.g., IN clause with variable parameters), THE Backend_System SHALL generate correct $N sequences

### Requirement 7: Preserve Database Initialization Logic

**User Story:** As a backend developer, I want database initialization to work on Render, so that the application can start without manual setup.

#### Acceptance Criteria

1. WHEN connecting to Render PostgreSQL, THE Backend_System SHALL NOT attempt to create the database (Render provides pre-created databases)
2. THE Backend_System SHALL remove the _ensure_database_exists method or make it conditional for local development only
3. THE Migration_Runner SHALL execute schema migrations on application startup
4. THE Migration_Runner SHALL create schema_migrations tracking table if it does not exist
5. FOR ALL Schema_Migrations, THE Migration_Runner SHALL execute unapplied migrations in version order
6. THE Migration_Runner SHALL record successful migration application in schema_migrations table

### Requirement 8: Maintain API Contract Compatibility

**User Story:** As a frontend developer, I want API responses to remain unchanged, so that the mobile app continues to work without modifications.

#### Acceptance Criteria

1. FOR ALL API endpoints, response schemas SHALL remain identical before and after migration
2. THE Backend_System SHALL return the same data types for user IDs, place IDs, comment IDs, and rating values
3. WHEN converting DECIMAL(10,7) coordinates to/from database, THE Backend_System SHALL preserve precision
4. THE Backend_System SHALL maintain the same date/time formatting for created_at and updated_at fields
5. WHEN authentication succeeds, THE Backend_System SHALL return tokens and user objects in the same format

### Requirement 9: Support Transaction Rollback in Migrations

**User Story:** As a backend developer, I want migration failures to roll back, so that the database is not left in a partially migrated state.

#### Acceptance Criteria

1. WHEN applying a Schema_Migration, THE Migration_Runner SHALL execute all statements within a transaction
2. IF any statement in a Schema_Migration fails, THEN THE Migration_Runner SHALL roll back the entire migration
3. THE Migration_Runner SHALL NOT record a failed migration in schema_migrations table
4. WHEN migration rollback occurs, THE Backend_System SHALL log the error with sufficient detail for debugging
5. THE Migration_Runner SHALL use asyncpg's transaction API for transaction management

### Requirement 10: Provide Deployment Documentation

**User Story:** As a backend developer, I want deployment instructions for Render, so that I can configure and deploy the PostgreSQL backend.

#### Acceptance Criteria

1. THE deployment documentation SHALL specify how to create a PostgreSQL database on Render
2. THE deployment documentation SHALL list all required environment variables for Render deployment
3. THE deployment documentation SHALL provide the DATABASE_URL format and example values
4. THE deployment documentation SHALL document the migration execution process on first deployment
5. THE deployment documentation SHALL include verification steps to confirm successful migration
6. THE deployment documentation SHALL provide rollback instructions if deployment fails

### Requirement 11: Enable Local Development with PostgreSQL

**User Story:** As a backend developer, I want to run PostgreSQL locally, so that I can test the migration before deploying to Render.

#### Acceptance Criteria

1. THE deployment documentation SHALL provide instructions for installing PostgreSQL locally
2. THE deployment documentation SHALL provide docker-compose configuration for local PostgreSQL
3. WHEN running locally, THE Backend_System SHALL support environment variables from .env file
4. THE Backend_System SHALL create the local database if it does not exist (only in local development mode)
5. THE Backend_System SHALL execute migrations on local startup

### Requirement 12: Validate Data Type Conversions

**User Story:** As a backend developer, I want to verify data type mappings, so that no data loss occurs during migration.

#### Acceptance Criteria

1. THE Backend_System SHALL map VARCHAR(N) columns to VARCHAR(N) or TEXT in PostgreSQL
2. THE Backend_System SHALL map DECIMAL(10,7) columns to DECIMAL(10,7) or NUMERIC(10,7) in PostgreSQL
3. THE Backend_System SHALL map TINYINT UNSIGNED to SMALLINT with CHECK constraint (value >= 0 AND value <= 255)
4. THE Backend_System SHALL map INT UNSIGNED to INTEGER with CHECK constraint (value >= 0)
5. THE Backend_System SHALL map BIGINT UNSIGNED to BIGINT with CHECK constraint (value >= 0)
6. THE Backend_System SHALL map TEXT columns to TEXT in PostgreSQL
7. FOR ALL numeric columns, precision and scale SHALL be preserved in PostgreSQL schema

### Requirement 13: Test All Database Operations

**User Story:** As a backend developer, I want comprehensive testing, so that I can verify all database operations work correctly with PostgreSQL.

#### Acceptance Criteria

1. WHEN testing user signup, THE Backend_System SHALL successfully create users and return valid IDs
2. WHEN testing user login, THE Backend_System SHALL successfully authenticate users with correct credentials
3. WHEN testing favorite place operations, THE Backend_System SHALL successfully create, list, and delete favorites
4. WHEN testing place ratings, THE Backend_System SHALL successfully record ratings and calculate safety summaries
5. WHEN testing road segment ratings, THE Backend_System SHALL successfully record ratings, update aggregated scores, and calculate summaries
6. WHEN testing comment operations, THE Backend_System SHALL successfully create comments and retrieve by target type, user, and location
7. FOR ALL test cases, results SHALL match the behavior of the MySQL implementation
