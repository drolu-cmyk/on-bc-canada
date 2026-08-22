# PostgreSQL Domain Data Plane

The PostgreSQL Domain Data Plane is the relational system of record for stable workforce intelligence and reviewed learning definitions.

It complements the DynamoDB execution plane rather than replacing it.

```text
DynamoDB
workflow execution, checkpoints, approvals, leases and work delivery

PostgreSQL
research provenance, work relationships, capability definitions and learning structure
```

The separation matters. An execution can be temporary while the evidence and capability relationships it produces remain durable and queryable across many executions.

## First data boundary

The first PostgreSQL schema contains two data domains.

### `intelligence`

Stores:

- work entities
- pathway records
- technical roles
- capabilities detected in research
- technology signals
- research sources
- evidence-backed relations
- relation-to-source provenance
- reviewed research ingestion records

### `learning`

Stores:

- reviewed capability definitions
- capability prerequisites
- accepted evidence standards
- Work Intelligence provenance
- human activation and retirement decisions
- learning paths
- sprints, labs and missions
- learning-unit prerequisites
- capability development relations
- mission evidence requirements
- human learning-path decisions

Learner-private records are not part of this first schema. They remain on the existing bounded store until the database access model is exercised with non-identity domain data.

## Database-enforced provenance

The relational schema strengthens the existing application checks.

A capability provenance record contains both the Work Intelligence relation ID and the research execution that produced that relation. PostgreSQL enforces that the pair exists in `intelligence.work_relations`.

A mission evidence requirement contains both the capability and evidence-standard identifier. PostgreSQL enforces that the standard exists in `learning.capability_evidence_standards`.

Learning-path targets and learning-unit capability relations also reference reviewed capability records.

These foreign keys make it harder for a later service or migration to create unsupported capability claims accidentally.

## Typed relationships

Flexible metadata uses `jsonb`, but the following are first-class relational fields rather than JSON documents:

- entity type
- relation type
- source and target entities
- confidence
- research execution ID
- relation status
- capability status and proficiency level
- prerequisites
- evidence standards
- evidence flags
- learning-path status and version
- learning-unit type
- mission evidence requirements
- human decisions

Indexes follow the current access paths, including entity lookup, source/target relation traversal, pathway capability listing, reverse prerequisite lookup and capability-to-learning-unit lookup.

No vector column or `pgvector` extension is enabled in this version. Aurora PostgreSQL supports vector extensions, but the platform will add embeddings only when a concrete retrieval workload and evaluation standard justify them.

## AWS reference infrastructure

The source reference uses Aurora PostgreSQL Serverless v2 in `ca-central-1`.

Reference settings:

- Aurora PostgreSQL 16.8 LTS
- one `db.serverless` writer
- minimum capacity `0` ACU
- maximum capacity `2` ACUs
- automatic pause after 900 idle seconds
- RDS Data API enabled
- no public database instance
- dedicated private VPC and two private subnets
- no internet gateway
- no NAT gateway
- no database security-group ingress
- customer-managed KMS encryption
- RDS-managed master credential in Secrets Manager
- seven-day automated backup retention
- deletion protection
- retained cluster, writer and KMS key on stack replacement or removal
- RDS Extended Support enrollment disabled

Scaling to zero removes serverless instance capacity charges while an eligible instance is paused. Aurora storage, backup, Secrets Manager, KMS, I/O and other applicable service charges still remain.

## Why Data API

The first pilot workload is bursty and does not need a permanently open database connection pool.

RDS Data API provides an HTTPS interface to the private Aurora cluster and uses database credentials stored in Secrets Manager. The source therefore does not need a public database endpoint or NAT gateway merely to execute reviewed SQL.

`runtime/rds_data_api.py` supports:

- single SQL statements
- typed named parameters
- JSON parameters
- JSON-formatted query rows
- begin, commit and rollback
- an explicit transaction context

The adapter receives a secret ARN. It does not retrieve or expose the password itself.

## Database runtime roles

CloudFormation creates two generated Secrets Manager credentials:

```text
sozorock_intelligence_rw
sozorock_learning_rw
```

The database roles themselves are created by the reviewed migration command after infrastructure creation.

### Intelligence role

Receives:

- connect to the domain database
- usage on `intelligence`
- select, insert and update on intelligence tables

It receives no learning-schema write permission.

### Learning role

Receives:

- connect to the domain database
- read access to `intelligence`
- usage and reviewed write access to `learning`
- sequence access required for append-only decision IDs

Update and delete are explicitly revoked from capability and learning-path decision tables.

Neither role is a database administrator.

## IAM separation

The CloudFormation stack creates three AWS managed policies.

### Migration policy

Allows the reviewed migration operator to:

- invoke RDS Data API on the domain cluster
- read the RDS-managed master secret
- read the two generated runtime secrets
- decrypt those secrets with the domain KMS key

### Intelligence Data API policy

Allows Data API calls on the domain cluster using only the intelligence runtime secret.

### Learning Data API policy

Allows Data API calls on the domain cluster using only the learning runtime secret.

The runtime policies do not grant Secrets Manager wildcard access or KMS administration.

## Migration integrity

Migration files live under:

```text
migrations/postgres/
```

Every file has:

- a stable migration ID
- explicit Data API statement boundaries
- a SHA-256 checksum

`platform_meta.schema_migrations` stores the migration ID, checksum, accountable operator and application time.

If an already-applied migration file changes, the migration command fails instead of silently treating the modified file as equivalent.

Schema changes are applied inside a PostgreSQL transaction. DDL statements use Data API's continue-after-timeout setting so an API timeout does not intentionally interrupt a running DDL operation.

## Runtime credentials

The migration command reads the generated runtime secrets from Secrets Manager, creates or rotates the corresponding PostgreSQL roles, and applies reviewed grants.

Secret values are not printed in command output or committed to source control.

The command reports only:

- database name
- AWS region
- migration IDs applied during that invocation
- runtime role names
- confirmation that secret values were not exposed

## Deployment boundary

The domain data deployment workflow is manual-only.

Infrastructure deployment requires:

```text
DOMAIN_DATA_DEPLOYMENT_ENABLED=true
DOMAIN_DATA_DEPLOY_ROLE_ARN=<dedicated GitHub OIDC role>
```

Schema migration is a separate optional job and also requires:

```text
DOMAIN_DATA_MIGRATIONS_ENABLED=true
DOMAIN_DATA_MIGRATION_ROLE_ARN=<dedicated GitHub OIDC migration role>
```

A repository merge cannot create the Aurora cluster or apply the SQL migration.

The infrastructure deployment script never invokes the migration command.

## Current application boundary

The current SQLite implementations remain the active domain stores after this source merge.

The next adapter slice maps the existing Work Intelligence, Capability Graph and Learning Graph store interfaces to RDS Data API while preserving their tests and human authority rules. Only after those adapters pass repository validation can an operator choose PostgreSQL as the domain-store backend.

Research persistence and learner-private persistence remain separate migration scopes because their data and authority requirements differ.

## Validation

Run:

```bash
python scripts/validate_domain_data.py
bash -n scripts/deploy_domain_data.sh
python -m unittest runtime.test_domain_data_api runtime.test_domain_migrations -v
```

The normal repository validation workflow runs these checks before the complete graph and runtime suite.
