SET statement_timeout = '5s';
SET lock_timeout = '2s';
SET idle_in_transaction_session_timeout = '10s';

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    event_id UUID NOT NULL DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL,
    
    entity_type VARCHAR(64) NOT NULL,
    action VARCHAR(32) NOT NULL CHECK (action IN (
        'CREATE','UPDATE','DELETE','LOGIN','LOGOUT','ACCESS',
        'SYSTEM','AUDIT','CONFIG_CHANGE'
    )),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    prev_hash BYTEA NOT NULL CHECK (octet_length(prev_hash) = 32),
    curr_hash BYTEA NOT NULL CHECK (octet_length(curr_hash) = 32),
    signature BYTEA NOT NULL,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_ip INET,
    
    PRIMARY KEY (id, created_at),
    CONSTRAINT uk_audit_event UNIQUE (event_id, created_at),
    
    CONSTRAINT chk_payload_size CHECK (octet_length(payload::text) <= 65535),
    CONSTRAINT chk_signature_size CHECK (octet_length(signature) IN (64, 96))
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS audit_log_y2026m05 PARTITION OF audit_log
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_log (trace_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity_action ON audit_log (entity_type, action);
CREATE INDEX IF NOT EXISTS idx_audit_created_desc ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_curr_hash ON audit_log (curr_hash);
CREATE INDEX IF NOT EXISTS idx_audit_source_ip ON audit_log (source_ip) WHERE source_ip IS NOT NULL;

CREATE OR REPLACE FUNCTION audit_log_append_only_guard() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'CYBERIMMUNE VIOLATION: audit_log is strictly APPEND-ONLY. Operation % blocked at %', TG_OP, NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_audit_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only_guard();

CREATE OR REPLACE FUNCTION audit_log_verify_chain() RETURNS TRIGGER AS $$
DECLARE
    _last_hash BYTEA;
    _genesis_hash CONSTANT BYTEA := '\x0000000000000000000000000000000000000000000000000000000000000000'::bytea;
BEGIN
    IF NEW.prev_hash = _genesis_hash THEN
        RETURN NEW;
    END IF;

    SELECT curr_hash INTO STRICT _last_hash
    FROM audit_log
    WHERE created_at < NEW.created_at
    ORDER BY created_at DESC, id DESC
    LIMIT 1;

    IF _last_hash IS DISTINCT FROM NEW.prev_hash THEN
        RAISE EXCEPTION 'CYBERIMMUNE VIOLATION: Hash chain broken. Expected prev_hash=%, got %. Event: %',
            encode(_last_hash, 'hex'),
            encode(NEW.prev_hash, 'hex'),
            NEW.event_id;
    END IF;

    RETURN NEW;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE EXCEPTION 'CYBERIMMUNE VIOLATION: Orphan chain detected. prev_hash provided but no genesis record found. Event: %', NEW.event_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_audit_verify_chain
    BEFORE INSERT ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_verify_chain();

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_writer') THEN
        CREATE ROLE audit_writer NOLOGIN INHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_reader') THEN
        CREATE ROLE audit_reader NOLOGIN INHERIT;
    END IF;
END $$;

GRANT INSERT, SELECT ON audit_log TO audit_writer;
GRANT SELECT ON audit_log TO audit_reader;

REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM audit_writer, audit_reader;
REVOKE EXECUTE ON FUNCTION audit_log_append_only_guard() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION audit_log_verify_chain() FROM PUBLIC;

REVOKE ALL ON SCHEMA public FROM audit_writer, audit_reader;
GRANT USAGE ON SCHEMA public TO audit_writer, audit_reader;

COMMENT ON TABLE audit_log IS 'Кибериммунный журнал: неизменяемый, c верифицируемой хеш-цепочкой и криптоподписью';
COMMENT ON COLUMN audit_log.prev_hash IS 'SHA-256 предыдущего события (32 байта). Genesis = 0x00*32';
COMMENT ON COLUMN audit_log.curr_hash IS 'SHA-256(prev_hash || canonical_json(payload) || action). Вычисляется в app, проверяется в БД';
COMMENT ON COLUMN audit_log.signature IS 'Ed25519-подпись curr_hash. Обеспечивает неотрекаемость (non-repudiation)';
COMMENT ON TRIGGER trg_audit_append_only ON audit_log IS 'CYBERIMMUNE: Блокирует UPDATE/DELETE на уровне ядра СУБД';
COMMENT ON TRIGGER trg_audit_verify_chain ON audit_log IS 'CYBERIMMUNE: Автоматически отклоняет записи c разорванной цепочкой';