--Created By: Ananya Gupta
-- =============================================================================
-- VOCALL COMPLETE SUPABASE DATABASE SETUP SCRIPT
-- Run this script in the Supabase Dashboard SQL Editor to set up the database.
-- =============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "moddatetime" SCHEMA extensions;

-- 2. TABLES

-- ORGANIZATIONS
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    domain TEXT,
    logo_url TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- PROFILES
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    role TEXT DEFAULT 'member',
    name TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- SPACES
CREATE TABLE IF NOT EXISTS public.spaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AGENTS
CREATE TABLE IF NOT EXISTS public.agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id UUID REFERENCES public.spaces(id) ON DELETE SET NULL,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    system_prompt TEXT,
    voice_id TEXT,
    voice_provider TEXT,
    language VARCHAR(20) DEFAULT 'en',
    config JSONB DEFAULT '{}'::jsonb,
    published BOOLEAN DEFAULT false,
    enable_memory BOOLEAN DEFAULT false,
    enable_emotion BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- API KEYS
CREATE TABLE IF NOT EXISTS public.api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- PHONE NUMBERS
CREATE TABLE IF NOT EXISTS public.phone_numbers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES public.agents(id) ON DELETE SET NULL,
    number TEXT NOT NULL,
    provider TEXT,
    kyc_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CONTACTS
CREATE TABLE IF NOT EXISTS public.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name TEXT,
    phone TEXT,
    email TEXT,
    tags TEXT[] DEFAULT '{}'::text[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CONNECTORS
CREATE TABLE IF NOT EXISTS public.connectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES public.agents(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    trigger_type TEXT,
    config JSONB DEFAULT '{}'::jsonb,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CONNECTOR CONFIGS
CREATE TABLE IF NOT EXISTS public.connector_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES public.agents(id) ON DELETE CASCADE,
    connector_type TEXT NOT NULL CHECK (
        connector_type IN (
            'google_calendar',
            'hubspot',
            'salesforce',
            'supabase',
            'postgres',
            'slack',
            'whatsapp',
            'zapier',
            'custom_webhook'
        )
    ),
    is_enabled BOOLEAN DEFAULT false,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT connector_configs_org_agent_connector_type_key UNIQUE NULLS NOT DISTINCT (org_id, agent_id, connector_type)
);

-- CALLS
CREATE TABLE IF NOT EXISTS public.calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES public.agents(id) ON DELETE SET NULL,
    contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    direction VARCHAR(10),
    from_number TEXT,
    to_number TEXT,
    status VARCHAR(20),
    duration_seconds INTEGER,
    transcript TEXT,
    is_test BOOLEAN DEFAULT false,
    emotion_score DOUBLE PRECISION,
    analysis JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- MEMORY LONG TERM (Vector Embeddings)
CREATE TABLE IF NOT EXISTS public.memory_long_term (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES public.agents(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),
    emotion_state JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- MEMORY EPISODIC
CREATE TABLE IF NOT EXISTS public.memory_episodic (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
    call_id UUID REFERENCES public.calls(id) ON DELETE SET NULL,
    org_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    summary TEXT,
    key_facts JSONB DEFAULT '{}'::jsonb,
    emotion_arc JSONB DEFAULT '{}'::jsonb,
    entities JSONB DEFAULT '{}'::jsonb,
    topics JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- EMOTION EVENTS
CREATE TABLE IF NOT EXISTS public.emotion_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
    timestamp_ms BIGINT,
    valence DOUBLE PRECISION,
    arousal DOUBLE PRECISION,
    dominant VARCHAR(50),
    confidence DOUBLE PRECISION,
    signal_source VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- INTENT EVENTS
CREATE TABLE IF NOT EXISTS public.intent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL REFERENCES public.calls(id) ON DELETE CASCADE,
    contact_id UUID REFERENCES public.contacts(id) ON DELETE SET NULL,
    turn_index INT DEFAULT 0,
    intent TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.0,
    entities TEXT[] DEFAULT '{}',
    slot_data JSONB DEFAULT '{}'::jsonb,
    connector_used TEXT,
    connector_result JSONB DEFAULT '{}'::jsonb,
    emotion_state_at_detection JSONB DEFAULT '{}'::jsonb,
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- COMPLIANCE LOG
CREATE TABLE IF NOT EXISTS public.compliance_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action TEXT NOT NULL,
    contact_id UUID NOT NULL,
    tiers_cleared TEXT[] DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. INDEXES
CREATE INDEX IF NOT EXISTS memory_long_term_embedding_idx ON public.memory_long_term USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS connector_configs_org_id_idx ON public.connector_configs(org_id);
CREATE INDEX IF NOT EXISTS connector_configs_agent_id_idx ON public.connector_configs(agent_id);
CREATE INDEX IF NOT EXISTS idx_intent_events_call ON public.intent_events(call_id);
CREATE INDEX IF NOT EXISTS idx_intent_events_contact ON public.intent_events(contact_id);
CREATE INDEX IF NOT EXISTS idx_compliance_log_contact ON public.compliance_log(contact_id);

-- 4. HELPER FUNCTIONS & TRIGGERS
CREATE OR REPLACE FUNCTION public.get_user_org_id()
RETURNS UUID AS $$
    SELECT org_id FROM public.profiles WHERE id = auth.uid();
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Automatic profile & organization creation on auth signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    new_org_id UUID;
BEGIN
    INSERT INTO public.organizations (name)
    VALUES (COALESCE(new.raw_user_meta_data->>'org_name', new.email || '''s Org'))
    RETURNING id INTO new_org_id;

    INSERT INTO public.profiles (id, org_id, name, avatar_url, role)
    VALUES (
        new.id,
        new_org_id,
        COALESCE(new.raw_user_meta_data->>'full_name', new.email),
        new.raw_user_meta_data->>'avatar_url',
        'owner'
    );

    INSERT INTO public.spaces (org_id, name)
    VALUES (new_org_id, 'Default Space');

    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- Auto-update updated_at timestamp triggers
DROP TRIGGER IF EXISTS handle_connector_configs_updated_at ON public.connector_configs;
CREATE TRIGGER handle_connector_configs_updated_at
    BEFORE UPDATE ON public.connector_configs
    FOR EACH ROW
    EXECUTE PROCEDURE extensions.moddatetime(updated_at);

DROP TRIGGER IF EXISTS handle_agents_updated_at ON public.agents;
CREATE TRIGGER handle_agents_updated_at
    BEFORE UPDATE ON public.agents
    FOR EACH ROW
    EXECUTE PROCEDURE extensions.moddatetime(updated_at);

DROP TRIGGER IF EXISTS handle_calls_updated_at ON public.calls;
CREATE TRIGGER handle_calls_updated_at
    BEFORE UPDATE ON public.calls
    FOR EACH ROW
    EXECUTE PROCEDURE extensions.moddatetime(updated_at);

-- 5. ROW LEVEL SECURITY (RLS)
-- 5. ROW LEVEL SECURITY (RLS) & PRIVILEGE HARDENING
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations FORCE ROW LEVEL SECURITY;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles FORCE ROW LEVEL SECURITY;

ALTER TABLE public.spaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spaces FORCE ROW LEVEL SECURITY;

ALTER TABLE public.agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agents FORCE ROW LEVEL SECURITY;

ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_keys FORCE ROW LEVEL SECURITY;

ALTER TABLE public.phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.phone_numbers FORCE ROW LEVEL SECURITY;

ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts FORCE ROW LEVEL SECURITY;

ALTER TABLE public.connectors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.connectors FORCE ROW LEVEL SECURITY;

ALTER TABLE public.connector_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.connector_configs FORCE ROW LEVEL SECURITY;

ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls FORCE ROW LEVEL SECURITY;

ALTER TABLE public.memory_long_term ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_long_term FORCE ROW LEVEL SECURITY;

ALTER TABLE public.memory_episodic ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_episodic FORCE ROW LEVEL SECURITY;

ALTER TABLE public.emotion_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emotion_events FORCE ROW LEVEL SECURITY;

ALTER TABLE public.intent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intent_events FORCE ROW LEVEL SECURITY;

ALTER TABLE public.compliance_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.compliance_log FORCE ROW LEVEL SECURITY;

-- POLICIES
DROP POLICY IF EXISTS "Users can view their organization" ON public.organizations;
DROP POLICY IF EXISTS "Users can update their organization" ON public.organizations;
DROP POLICY IF EXISTS "Org members can view organization" ON public.organizations;
DROP POLICY IF EXISTS "Org members can update organization" ON public.organizations;
CREATE POLICY "Org members can view organization" ON public.organizations FOR SELECT TO authenticated USING (id = public.get_user_org_id());
CREATE POLICY "Org members can update organization" ON public.organizations FOR UPDATE TO authenticated USING (id = public.get_user_org_id()) WITH CHECK (id = public.get_user_org_id());

DROP POLICY IF EXISTS "Users can view profiles in their organization" ON public.profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;
CREATE POLICY "Users can view profiles in their organization" ON public.profiles FOR SELECT TO authenticated USING (id = auth.uid() OR org_id = public.get_user_org_id());
CREATE POLICY "Users can insert own profile" ON public.profiles FOR INSERT TO authenticated WITH CHECK (id = auth.uid());
CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE TO authenticated USING (id = auth.uid()) WITH CHECK (id = auth.uid());

DROP POLICY IF EXISTS "Org members can view spaces" ON public.spaces;
DROP POLICY IF EXISTS "Org members can manage spaces" ON public.spaces;
CREATE POLICY "Org members can manage spaces" ON public.spaces FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view agents" ON public.agents;
DROP POLICY IF EXISTS "Org members can manage agents" ON public.agents;
CREATE POLICY "Org members can manage agents" ON public.agents FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view phone_numbers" ON public.phone_numbers;
DROP POLICY IF EXISTS "Org members can manage phone_numbers" ON public.phone_numbers;
CREATE POLICY "Org members can manage phone_numbers" ON public.phone_numbers FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view contacts" ON public.contacts;
DROP POLICY IF EXISTS "Org members can manage contacts" ON public.contacts;
CREATE POLICY "Org members can manage contacts" ON public.contacts FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view connectors" ON public.connectors;
DROP POLICY IF EXISTS "Org members can manage connectors" ON public.connectors;
CREATE POLICY "Org members can manage connectors" ON public.connectors FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can access their connector_configs" ON public.connector_configs;
CREATE POLICY "Org members can manage connector_configs" ON public.connector_configs FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view calls" ON public.calls;
DROP POLICY IF EXISTS "Org members can manage calls" ON public.calls;
CREATE POLICY "Org members can manage calls" ON public.calls FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view long term memory" ON public.memory_long_term;
DROP POLICY IF EXISTS "Org members can manage long term memory" ON public.memory_long_term;
CREATE POLICY "Org members can manage long term memory" ON public.memory_long_term FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view episodic memory" ON public.memory_episodic;
DROP POLICY IF EXISTS "Org members can manage episodic memory" ON public.memory_episodic;
CREATE POLICY "Org members can manage episodic memory" ON public.memory_episodic FOR ALL TO authenticated USING (org_id = public.get_user_org_id()) WITH CHECK (org_id = public.get_user_org_id());

DROP POLICY IF EXISTS "Org members can view emotion events" ON public.emotion_events;
DROP POLICY IF EXISTS "Org members can manage emotion events" ON public.emotion_events;
CREATE POLICY "Org members can manage emotion events" ON public.emotion_events FOR ALL TO authenticated USING (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id())) WITH CHECK (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()));

DROP POLICY IF EXISTS "Org members can view intent events" ON public.intent_events;
DROP POLICY IF EXISTS "Org members can manage intent events" ON public.intent_events;
CREATE POLICY "Org members can manage intent events" ON public.intent_events FOR ALL TO authenticated USING (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id())) WITH CHECK (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()));

-- API_KEYS & COMPLIANCE_LOG: NO POLICIES FOR ANON OR AUTHENTICATED (SERVICE ROLE ONLY)
DROP POLICY IF EXISTS "Org members can view api_keys" ON public.api_keys;
DROP POLICY IF EXISTS "Org members can manage api_keys" ON public.api_keys;
DROP POLICY IF EXISTS "Org members can view compliance logs" ON public.compliance_log;
DROP POLICY IF EXISTS "Org members can insert compliance logs" ON public.compliance_log;

-- 6. PRIVILEGE REVOCATIONS FOR ANON & AUTHENTICATED
REVOKE ALL ON TABLE public.api_keys FROM anon, authenticated;
REVOKE ALL ON TABLE public.compliance_log FROM anon, authenticated;

REVOKE ALL ON TABLE public.agents FROM anon;
REVOKE ALL ON TABLE public.phone_numbers FROM anon;
REVOKE ALL ON TABLE public.connector_configs FROM anon;
REVOKE ALL ON TABLE public.connectors FROM anon;
REVOKE ALL ON TABLE public.contacts FROM anon;
REVOKE ALL ON TABLE public.calls FROM anon;
REVOKE ALL ON TABLE public.memory_long_term FROM anon;
REVOKE ALL ON TABLE public.memory_episodic FROM anon;
REVOKE ALL ON TABLE public.emotion_events FROM anon;
REVOKE ALL ON TABLE public.intent_events FROM anon;
REVOKE ALL ON TABLE public.organizations FROM anon;
REVOKE ALL ON TABLE public.profiles FROM anon;
REVOKE ALL ON TABLE public.spaces FROM anon;
