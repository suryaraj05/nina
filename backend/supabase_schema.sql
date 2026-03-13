-- Supabase schema for Nina backend
-- Run this in your Supabase SQL Editor

-- Customers table
CREATE TABLE IF NOT EXISTS public.customers (
    id BIGSERIAL PRIMARY KEY,
    uid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sites table (for customer websites)
CREATE TABLE IF NOT EXISTS public.sites (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    base_url TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, domain)
);

-- Site memory pages (per-page cache: registry, content)
CREATE TABLE IF NOT EXISTS public.site_pages (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT,
    links JSONB,
    headings JSONB,
    buttons JSONB,
    products JSONB,
    fields JSONB,
    method TEXT DEFAULT 'GET',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, domain, url)
);

-- Sitemap tree: one row per website (customer_id + domain), JSON tree for fast retrieval
CREATE TABLE IF NOT EXISTS public.sitemap_tree (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    tree JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_sitemap_tree_customer_domain ON public.sitemap_tree(customer_id, domain);

-- User actions (for user memory)
CREATE TABLE IF NOT EXISTS public.user_actions (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    command TEXT NOT NULL,
    intent TEXT NOT NULL,
    page_url TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_customers_uid ON public.customers(uid);
CREATE INDEX IF NOT EXISTS idx_customers_api_key ON public.customers(api_key);
CREATE INDEX IF NOT EXISTS idx_sites_customer_id ON public.sites(customer_id);
CREATE INDEX IF NOT EXISTS idx_sites_domain ON public.sites(domain);
CREATE INDEX IF NOT EXISTS idx_site_pages_customer_domain ON public.site_pages(customer_id, domain);
CREATE INDEX IF NOT EXISTS idx_user_actions_customer_session ON public.user_actions(customer_id, session_id);

-- Enable Row Level Security (RLS) - adjust policies as needed
ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sitemap_tree ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_actions ENABLE ROW LEVEL SECURITY;

-- Create policies (allow all for now - adjust for production)
CREATE POLICY "Allow all operations on customers" ON public.customers
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations on sites" ON public.sites
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations on site_pages" ON public.site_pages
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations on sitemap_tree" ON public.sitemap_tree
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations on user_actions" ON public.user_actions
    FOR ALL USING (true) WITH CHECK (true);

