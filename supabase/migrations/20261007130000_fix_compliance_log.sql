-- Migration: 20261007130000_fix_compliance_log.sql
-- Description: Adds contact_hash, org_id, and tier_details to compliance_log, makes contact_id nullable, and hashes legacy rows without raw PII.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

ALTER TABLE public.compliance_log ADD COLUMN IF NOT EXISTS contact_hash TEXT;
ALTER TABLE public.compliance_log ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE public.compliance_log ADD COLUMN IF NOT EXISTS tier_details JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.compliance_log ALTER COLUMN contact_id DROP NOT NULL;

-- Hash existing rows using SHA-256 and null out raw contact_id to protect PII
UPDATE public.compliance_log
SET contact_hash = encode(digest(contact_id::text, 'sha256'), 'hex'),
    contact_id = NULL
WHERE contact_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_compliance_log_contact_hash ON public.compliance_log(contact_hash);
CREATE INDEX IF NOT EXISTS idx_compliance_log_org_id ON public.compliance_log(org_id);
