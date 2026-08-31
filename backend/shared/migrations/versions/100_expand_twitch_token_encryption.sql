-- Expand Twitch credential storage for explicit, versioned application encryption.
--
-- This migration is intentionally schema-only. Existing rows remain version 0
-- plaintext until the separately deployed backfill tool encrypts them. A later
-- contract migration may require version 1 after every runtime has been upgraded.

ALTER TABLE tokens
    ADD COLUMN IF NOT EXISTS encryption_version SMALLINT NOT NULL DEFAULT 0;

ALTER TABLE tokens
    DROP CONSTRAINT IF EXISTS tokens_encryption_version_check;

ALTER TABLE tokens
    ADD CONSTRAINT tokens_encryption_version_check
    CHECK (encryption_version IN (0, 1));

-- Bot credential principals may exist without a Dashboard User/Identity.
ALTER TABLE tokens
    DROP CONSTRAINT IF EXISTS tokens_identity_id_fkey;

ALTER TABLE tokens
    ADD CONSTRAINT tokens_identity_id_fkey
    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE SET NULL;

COMMENT ON COLUMN tokens.encryption_version IS
    '0=legacy plaintext during bounded backfill; 1=v1 Fernet envelope';
