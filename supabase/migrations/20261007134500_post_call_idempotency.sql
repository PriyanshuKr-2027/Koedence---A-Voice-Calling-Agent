-- Post-call processing idempotency controls
-- 1. Unique index on memory_episodic (call_id) where call_id is not null
CREATE UNIQUE INDEX IF NOT EXISTS memory_episodic_call_id_unique_idx
    ON public.memory_episodic (call_id)
    WHERE call_id IS NOT NULL;

-- 2. Add idempotency tracking columns to calls table
ALTER TABLE public.calls
    ADD COLUMN IF NOT EXISTS post_processed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS post_steps JSONB DEFAULT '{}'::jsonb;
