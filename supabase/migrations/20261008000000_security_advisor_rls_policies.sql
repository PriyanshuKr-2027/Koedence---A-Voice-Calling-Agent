-- Migration: 20261008000000_security_advisor_rls_policies.sql
-- Description: Enables RLS on all public tables, enforces org-scoped policies with USING and WITH CHECK,
-- removes public/anon/authenticated access to api_keys and compliance_log (service role only),
-- and revokes direct table privileges from anon/authenticated roles.

-- 1. ENABLE AND FORCE ROW LEVEL SECURITY ON ALL PUBLIC TABLES
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

-- 2. HELPER FUNCTION
CREATE OR REPLACE FUNCTION public.get_user_org_id()
RETURNS UUID AS $$
    SELECT org_id FROM public.profiles WHERE id = auth.uid();
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- 3. DROP LEGACY POLICIES
DROP POLICY IF EXISTS "Users can view their organization" ON public.organizations;
DROP POLICY IF EXISTS "Users can update their organization" ON public.organizations;
DROP POLICY IF EXISTS "Users can view profiles in their organization" ON public.profiles;
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;
DROP POLICY IF EXISTS "Org members can view spaces" ON public.spaces;
DROP POLICY IF EXISTS "Org members can manage spaces" ON public.spaces;
DROP POLICY IF EXISTS "Org members can view agents" ON public.agents;
DROP POLICY IF EXISTS "Org members can manage agents" ON public.agents;
DROP POLICY IF EXISTS "Org members can view api_keys" ON public.api_keys;
DROP POLICY IF EXISTS "Org members can manage api_keys" ON public.api_keys;
DROP POLICY IF EXISTS "Org members can view phone_numbers" ON public.phone_numbers;
DROP POLICY IF EXISTS "Org members can manage phone_numbers" ON public.phone_numbers;
DROP POLICY IF EXISTS "Org members can view contacts" ON public.contacts;
DROP POLICY IF EXISTS "Org members can manage contacts" ON public.contacts;
DROP POLICY IF EXISTS "Org members can view connectors" ON public.connectors;
DROP POLICY IF EXISTS "Org members can manage connectors" ON public.connectors;
DROP POLICY IF EXISTS "Org members can access their connector_configs" ON public.connector_configs;
DROP POLICY IF EXISTS "Org members can view calls" ON public.calls;
DROP POLICY IF EXISTS "Org members can manage calls" ON public.calls;
DROP POLICY IF EXISTS "Org members can view long term memory" ON public.memory_long_term;
DROP POLICY IF EXISTS "Org members can manage long term memory" ON public.memory_long_term;
DROP POLICY IF EXISTS "Org members can view episodic memory" ON public.memory_episodic;
DROP POLICY IF EXISTS "Org members can manage episodic memory" ON public.memory_episodic;
DROP POLICY IF EXISTS "Org members can view emotion events" ON public.emotion_events;
DROP POLICY IF EXISTS "Org members can manage emotion events" ON public.emotion_events;
DROP POLICY IF EXISTS "Org members can view intent events" ON public.intent_events;
DROP POLICY IF EXISTS "Org members can manage intent events" ON public.intent_events;
DROP POLICY IF EXISTS "Org members can view compliance logs" ON public.compliance_log;
DROP POLICY IF EXISTS "Org members can insert compliance logs" ON public.compliance_log;

-- 4. ORG-SCOPED POLICIES WITH BOTH USING AND WITH CHECK

-- ORGANIZATIONS
CREATE POLICY "Org members can view organization" ON public.organizations
    FOR SELECT TO authenticated
    USING (id = public.get_user_org_id());

CREATE POLICY "Org members can update organization" ON public.organizations
    FOR UPDATE TO authenticated
    USING (id = public.get_user_org_id())
    WITH CHECK (id = public.get_user_org_id());

-- PROFILES
CREATE POLICY "Users can view profiles in their organization" ON public.profiles
    FOR SELECT TO authenticated
    USING (id = auth.uid() OR org_id = public.get_user_org_id());

CREATE POLICY "Users can insert own profile" ON public.profiles
    FOR INSERT TO authenticated
    WITH CHECK (id = auth.uid());

CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE TO authenticated
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

-- SPACES
CREATE POLICY "Org members can manage spaces" ON public.spaces
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- AGENTS
CREATE POLICY "Org members can manage agents" ON public.agents
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- PHONE NUMBERS
CREATE POLICY "Org members can manage phone_numbers" ON public.phone_numbers
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- CONTACTS
CREATE POLICY "Org members can manage contacts" ON public.contacts
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- CONNECTORS
CREATE POLICY "Org members can manage connectors" ON public.connectors
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- CONNECTOR CONFIGS
CREATE POLICY "Org members can manage connector_configs" ON public.connector_configs
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- CALLS
CREATE POLICY "Org members can manage calls" ON public.calls
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- MEMORY LONG TERM
CREATE POLICY "Org members can manage long term memory" ON public.memory_long_term
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- MEMORY EPISODIC
CREATE POLICY "Org members can manage episodic memory" ON public.memory_episodic
    FOR ALL TO authenticated
    USING (org_id = public.get_user_org_id())
    WITH CHECK (org_id = public.get_user_org_id());

-- EMOTION EVENTS
CREATE POLICY "Org members can manage emotion events" ON public.emotion_events
    FOR ALL TO authenticated
    USING (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()))
    WITH CHECK (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()));

-- INTENT EVENTS
CREATE POLICY "Org members can manage intent events" ON public.intent_events
    FOR ALL TO authenticated
    USING (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()))
    WITH CHECK (call_id IN (SELECT id FROM public.calls WHERE org_id = public.get_user_org_id()));

-- API_KEYS & COMPLIANCE_LOG: NO POLICIES FOR ANON OR AUTHENTICATED (SERVICE ROLE ONLY)
-- (With RLS enabled and zero policies, only the service_role key bypasses RLS and can access these tables.)

-- 5. REVOKE DIRECT PRIVILEGES ON SENSITIVE / BACKEND TABLES
-- Revoke all direct privileges on api_keys and compliance_log from anon and authenticated
REVOKE ALL ON TABLE public.api_keys FROM anon, authenticated;
REVOKE ALL ON TABLE public.compliance_log FROM anon, authenticated;

-- Revoke all table privileges from anon role on all public tables
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
