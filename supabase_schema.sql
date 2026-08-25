-- Invoice Generator — Supabase schema
-- Run this once in the Supabase SQL Editor (Dashboard > SQL Editor > New query > Run)

create extension if not exists pgcrypto;

create table if not exists profile (
    id integer primary key default 1,
    name text default '',
    email text default '',
    address text default '',
    tax_number text default '',
    logo_path text,
    signature_path text,
    constraint single_row check (id = 1)
);

create table if not exists clients (
    id text primary key default gen_random_uuid()::text,
    name text not null default '',
    company text default '',
    email text default '',
    address text default ''
);

create table if not exists item_templates (
    id text primary key default gen_random_uuid()::text,
    description text not null default '',
    quantity numeric default 1,
    unit_price numeric default 0
);

create table if not exists recurring_templates (
    id text primary key default gen_random_uuid()::text,
    name text not null default '',
    doc_type text default 'Invoice',
    client_name text default '',
    client_company text default '',
    client_email text default '',
    client_address text default '',
    currency text default '₺',
    theme text default 'blue',
    tax_percent numeric default 0,
    tax_inclusive boolean default false,
    discount_amount numeric default 0,
    advance_paid numeric default 0,
    notes text default '',
    items jsonb default '[]'::jsonb
);

create table if not exists documents (
    id text primary key default gen_random_uuid()::text,
    doc_type text not null,
    doc_number text not null,
    client_name text default '',
    grand_total numeric default 0,
    balance_due numeric default 0,
    currency text default '₺',
    issue_date text default '',
    due_date_iso date,
    created_at timestamptz not null default now(),
    file_name text default '',
    status text default 'unpaid',
    pdf_path text
);

create table if not exists counters (
    doc_type text primary key,
    value integer not null default 0
);

-- Storage buckets for generated PDFs and profile logo/signature images.
insert into storage.buckets (id, name, public)
values ('documents', 'documents', true)
on conflict (id) do nothing;

insert into storage.buckets (id, name, public)
values ('assets', 'assets', true)
on conflict (id) do nothing;

-- This is a private single-user tool (not multi-tenant), so Row Level
-- Security stays off on these tables — the anon key already only reaches
-- this project, and no public-facing signup/auth exists that could let a
-- stranger read another tenant's rows. Newer Supabase projects enable RLS
-- by default on every new table, so turn it off explicitly here.
alter table profile disable row level security;
alter table clients disable row level security;
alter table item_templates disable row level security;
alter table recurring_templates disable row level security;
alter table documents disable row level security;
alter table counters disable row level security;

-- Supabase Storage enables RLS on storage.objects by default, so uploads
-- fail with "new row violates row-level security policy" until we grant
-- access explicitly. Same reasoning as above: single-user tool, so allow
-- full read/write on these two buckets rather than modeling per-user rules.
drop policy if exists "assets bucket - full access" on storage.objects;
create policy "assets bucket - full access"
on storage.objects for all
using (bucket_id = 'assets')
with check (bucket_id = 'assets');

drop policy if exists "documents bucket - full access" on storage.objects;
create policy "documents bucket - full access"
on storage.objects for all
using (bucket_id = 'documents')
with check (bucket_id = 'documents');
