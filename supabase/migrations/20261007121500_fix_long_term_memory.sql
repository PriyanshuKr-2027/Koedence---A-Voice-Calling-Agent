-- Migration: 20261007121500_fix_long_term_memory.sql
-- Fix long-term memory schema: 1024-dim BAAI/bge-m3 embeddings, HNSW index, call_id foreign key,
-- and cosine similarity threshold matching function.

drop index if exists public.memory_long_term_embedding_idx;

update public.memory_long_term set embedding = null;

alter table public.memory_long_term alter column embedding type vector(1024);

alter table public.memory_long_term add column if not exists call_id uuid references public.calls(id) on delete set null;

create index if not exists memory_long_term_contact_created_idx on public.memory_long_term (contact_id, created_at desc);

create index if not exists memory_long_term_call_id_idx on public.memory_long_term (call_id);

create index if not exists memory_long_term_embedding_hnsw on public.memory_long_term using hnsw (embedding vector_cosine_ops);

create or replace function public.match_long_term_memories(
    query_embedding vector(1024),
    match_threshold float,
    match_count int,
    p_contact_id uuid,
    p_org_id uuid)
returns table (id uuid, content text, emotion_state jsonb, created_at timestamptz, similarity float)
language sql stable as $$
  select m.id, m.content, m.emotion_state, m.created_at,
         1 - (m.embedding <=> query_embedding) as similarity
  from public.memory_long_term m
  where m.contact_id = p_contact_id and m.org_id = p_org_id and m.embedding is not null
    and 1 - (m.embedding <=> query_embedding) >= match_threshold
  order by m.embedding <=> query_embedding
  limit match_count;
$$;
