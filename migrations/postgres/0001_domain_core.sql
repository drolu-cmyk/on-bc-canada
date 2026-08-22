-- migration_id: 0001_domain_core
-- Each section after the marker is executed as one Data API statement.

-- sozorock:statement
CREATE SCHEMA IF NOT EXISTS platform_meta

-- sozorock:statement
CREATE SCHEMA IF NOT EXISTS intelligence

-- sozorock:statement
CREATE SCHEMA IF NOT EXISTS learning

-- sozorock:statement
CREATE TABLE IF NOT EXISTS platform_meta.schema_migrations (
    migration_id text PRIMARY KEY,
    checksum_sha256 text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now(),
    applied_by text NOT NULL,
    CONSTRAINT schema_migrations_checksum_format CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$')
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS intelligence.work_entities (
    entity_id text PRIMARY KEY,
    entity_type text NOT NULL,
    canonical_name text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT work_entities_type CHECK (entity_type IN ('pathway','role','capability','technology')),
    CONSTRAINT work_entities_name_nonempty CHECK (length(btrim(canonical_name)) >= 1),
    UNIQUE (entity_type, canonical_name)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS work_entities_type_name_idx
    ON intelligence.work_entities (entity_type, lower(canonical_name))

-- sozorock:statement
CREATE TABLE IF NOT EXISTS intelligence.work_sources (
    execution_id text NOT NULL,
    source_id text NOT NULL,
    publisher text,
    title text,
    url text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (execution_id, source_id),
    CONSTRAINT work_sources_execution_nonempty CHECK (length(btrim(execution_id)) >= 1),
    CONSTRAINT work_sources_id_nonempty CHECK (length(btrim(source_id)) >= 1)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS work_sources_source_id_idx
    ON intelligence.work_sources (source_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS intelligence.work_relations (
    relation_id text PRIMARY KEY,
    source_entity_id text NOT NULL REFERENCES intelligence.work_entities(entity_id),
    relation_type text NOT NULL,
    target_entity_id text NOT NULL REFERENCES intelligence.work_entities(entity_id),
    confidence double precision NOT NULL,
    execution_id text NOT NULL,
    research_graph_version text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT work_relations_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT work_relations_status CHECK (status IN ('active','retired')),
    CONSTRAINT work_relations_not_self CHECK (source_entity_id <> target_entity_id),
    UNIQUE (relation_id, execution_id)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS work_relations_source_idx
    ON intelligence.work_relations (source_entity_id, relation_type, status)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS work_relations_target_idx
    ON intelligence.work_relations (target_entity_id, relation_type, status)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS work_relations_execution_idx
    ON intelligence.work_relations (execution_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS intelligence.relation_sources (
    relation_id text NOT NULL,
    execution_id text NOT NULL,
    source_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (relation_id, execution_id, source_id),
    FOREIGN KEY (relation_id, execution_id)
        REFERENCES intelligence.work_relations(relation_id, execution_id),
    FOREIGN KEY (execution_id, source_id)
        REFERENCES intelligence.work_sources(execution_id, source_id)
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS intelligence.research_ingests (
    execution_id text PRIMARY KEY,
    pathway_entity_id text NOT NULL REFERENCES intelligence.work_entities(entity_id),
    confidence double precision NOT NULL,
    relation_count integer NOT NULL,
    store_version text NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT research_ingests_confidence CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT research_ingests_relation_count CHECK (relation_count >= 0)
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.capabilities (
    capability_id text PRIMARY KEY,
    pathway_id text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    target_level text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    source_confidence double precision NOT NULL,
    store_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT capabilities_id_format CHECK (capability_id ~ '^[a-z0-9][a-z0-9.-]{2,79}$'),
    CONSTRAINT capabilities_level CHECK (target_level IN ('explain','apply','analyze','evaluate','design','defend')),
    CONSTRAINT capabilities_status CHECK (status IN ('draft','active','retired')),
    CONSTRAINT capabilities_confidence CHECK (source_confidence >= 0 AND source_confidence <= 1),
    CONSTRAINT capabilities_description_specific CHECK (length(btrim(description)) >= 20)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS capabilities_pathway_status_idx
    ON learning.capabilities (pathway_id, status, capability_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.capability_prerequisites (
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    prerequisite_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (capability_id, prerequisite_id),
    CONSTRAINT capability_prerequisite_not_self CHECK (capability_id <> prerequisite_id)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS capability_prerequisites_reverse_idx
    ON learning.capability_prerequisites (prerequisite_id, capability_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.capability_evidence_standards (
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    standard_id text NOT NULL,
    description text NOT NULL,
    artifact_types text[] NOT NULL,
    minimum_level text NOT NULL,
    requires_defense boolean NOT NULL DEFAULT false,
    requires_revision boolean NOT NULL DEFAULT true,
    requires_changed_scenario boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (capability_id, standard_id),
    CONSTRAINT capability_evidence_artifacts CHECK (cardinality(artifact_types) >= 1),
    CONSTRAINT capability_evidence_level CHECK (minimum_level IN ('explain','apply','analyze','evaluate','design','defend')),
    CONSTRAINT capability_evidence_description_specific CHECK (length(btrim(description)) >= 20)
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.capability_provenance (
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    execution_id text NOT NULL,
    relation_id text NOT NULL,
    confidence double precision NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (capability_id, execution_id, relation_id),
    FOREIGN KEY (relation_id, execution_id)
        REFERENCES intelligence.work_relations(relation_id, execution_id),
    CONSTRAINT capability_provenance_confidence CHECK (confidence >= 0 AND confidence <= 1)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS capability_provenance_relation_idx
    ON learning.capability_provenance (relation_id, execution_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.capability_decisions (
    decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    decision text NOT NULL,
    approver_id text NOT NULL,
    note text NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT capability_decisions_type CHECK (decision IN ('activate','retire')),
    CONSTRAINT capability_decisions_approver CHECK (length(btrim(approver_id)) >= 1)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS capability_decisions_capability_idx
    ON learning.capability_decisions (capability_id, decided_at)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_paths (
    pathway_id text NOT NULL,
    version text NOT NULL,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'candidate',
    store_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (pathway_id, version),
    CONSTRAINT learning_paths_status CHECK (status IN ('candidate','active','retired')),
    CONSTRAINT learning_paths_title CHECK (length(btrim(title)) >= 3)
)

-- sozorock:statement
CREATE UNIQUE INDEX IF NOT EXISTS learning_paths_one_active_per_pathway_idx
    ON learning.learning_paths (pathway_id)
    WHERE status = 'active'

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_units (
    pathway_id text NOT NULL,
    version text NOT NULL,
    unit_id text NOT NULL,
    kind text NOT NULL,
    title text NOT NULL,
    purpose text NOT NULL,
    source_module_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (pathway_id, version, unit_id),
    FOREIGN KEY (pathway_id, version)
        REFERENCES learning.learning_paths(pathway_id, version) ON DELETE CASCADE,
    CONSTRAINT learning_units_kind CHECK (kind IN ('sprint','lab','mission')),
    CONSTRAINT learning_units_id_format CHECK (unit_id ~ '^[a-z0-9][a-z0-9.-]{2,99}$'),
    CONSTRAINT learning_units_purpose_specific CHECK (length(btrim(purpose)) >= 20)
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_path_targets (
    pathway_id text NOT NULL,
    version text NOT NULL,
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    PRIMARY KEY (pathway_id, version, capability_id),
    FOREIGN KEY (pathway_id, version)
        REFERENCES learning.learning_paths(pathway_id, version) ON DELETE CASCADE
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_unit_capabilities (
    pathway_id text NOT NULL,
    version text NOT NULL,
    unit_id text NOT NULL,
    capability_id text NOT NULL REFERENCES learning.capabilities(capability_id),
    relation_type text NOT NULL,
    PRIMARY KEY (pathway_id, version, unit_id, capability_id, relation_type),
    FOREIGN KEY (pathway_id, version, unit_id)
        REFERENCES learning.learning_units(pathway_id, version, unit_id) ON DELETE CASCADE,
    CONSTRAINT learning_unit_capabilities_relation CHECK (relation_type IN ('develops','assesses'))
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS learning_unit_capabilities_capability_idx
    ON learning.learning_unit_capabilities (capability_id, relation_type)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_unit_prerequisites (
    pathway_id text NOT NULL,
    version text NOT NULL,
    unit_id text NOT NULL,
    prerequisite_unit_id text NOT NULL,
    PRIMARY KEY (pathway_id, version, unit_id, prerequisite_unit_id),
    FOREIGN KEY (pathway_id, version, unit_id)
        REFERENCES learning.learning_units(pathway_id, version, unit_id) ON DELETE CASCADE,
    FOREIGN KEY (pathway_id, version, prerequisite_unit_id)
        REFERENCES learning.learning_units(pathway_id, version, unit_id) ON DELETE CASCADE,
    CONSTRAINT learning_unit_prerequisite_not_self CHECK (unit_id <> prerequisite_unit_id)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS learning_unit_prerequisites_reverse_idx
    ON learning.learning_unit_prerequisites (pathway_id, version, prerequisite_unit_id)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_unit_evidence (
    pathway_id text NOT NULL,
    version text NOT NULL,
    unit_id text NOT NULL,
    capability_id text NOT NULL,
    standard_id text NOT NULL,
    PRIMARY KEY (pathway_id, version, unit_id, capability_id, standard_id),
    FOREIGN KEY (pathway_id, version, unit_id)
        REFERENCES learning.learning_units(pathway_id, version, unit_id) ON DELETE CASCADE,
    FOREIGN KEY (capability_id, standard_id)
        REFERENCES learning.capability_evidence_standards(capability_id, standard_id)
)

-- sozorock:statement
CREATE TABLE IF NOT EXISTS learning.learning_path_decisions (
    decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pathway_id text NOT NULL,
    version text NOT NULL,
    decision text NOT NULL,
    approver_id text NOT NULL,
    note text NOT NULL,
    decided_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (pathway_id, version)
        REFERENCES learning.learning_paths(pathway_id, version),
    CONSTRAINT learning_path_decisions_type CHECK (decision IN ('activate','retire')),
    CONSTRAINT learning_path_decisions_approver CHECK (length(btrim(approver_id)) >= 1),
    CONSTRAINT learning_path_decisions_note CHECK (length(btrim(note)) >= 1)
)

-- sozorock:statement
CREATE INDEX IF NOT EXISTS learning_path_decisions_path_idx
    ON learning.learning_path_decisions (pathway_id, version, decided_at)
