--
-- PostgreSQL database dump
--

\restrict FeGD4O2uDApdumldMxv1Y2sYPyqZllXgtyDsNNMh2EeQwQqXvPWaXXuO8gzTddN

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: adoptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.adoptions (
    id integer NOT NULL,
    evaluation_id integer,
    decision character varying(30),
    note text,
    status character varying(20)
);


--
-- Name: adoptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.adoptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: adoptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.adoptions_id_seq OWNED BY public.adoptions.id;


--
-- Name: audits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audits (
    id integer NOT NULL,
    actor character varying(100),
    action character varying(200),
    created character varying(40)
);


--
-- Name: audits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audits_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audits_id_seq OWNED BY public.audits.id;


--
-- Name: evaluations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.evaluations (
    id integer NOT NULL,
    name character varying(100),
    team character varying(40),
    state character varying(20),
    result json,
    error text
);


--
-- Name: evaluations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.evaluations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: evaluations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.evaluations_id_seq OWNED BY public.evaluations.id;


--
-- Name: pairs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pairs (
    id integer NOT NULL,
    code character varying(60) NOT NULL,
    team character varying(40),
    before double precision,
    after double precision,
    note text
);


--
-- Name: pairs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pairs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pairs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pairs_id_seq OWNED BY public.pairs.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(100) NOT NULL,
    password character varying(200),
    role character varying(20)
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: adoptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adoptions ALTER COLUMN id SET DEFAULT nextval('public.adoptions_id_seq'::regclass);


--
-- Name: audits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits ALTER COLUMN id SET DEFAULT nextval('public.audits_id_seq'::regclass);


--
-- Name: evaluations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations ALTER COLUMN id SET DEFAULT nextval('public.evaluations_id_seq'::regclass);


--
-- Name: pairs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pairs ALTER COLUMN id SET DEFAULT nextval('public.pairs_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: adoptions adoptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adoptions
    ADD CONSTRAINT adoptions_pkey PRIMARY KEY (id);


--
-- Name: audits audits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audits
    ADD CONSTRAINT audits_pkey PRIMARY KEY (id);


--
-- Name: evaluations evaluations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.evaluations
    ADD CONSTRAINT evaluations_pkey PRIMARY KEY (id);


--
-- Name: pairs pairs_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pairs
    ADD CONSTRAINT pairs_code_key UNIQUE (code);


--
-- Name: pairs pairs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pairs
    ADD CONSTRAINT pairs_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: adoptions adoptions_evaluation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.adoptions
    ADD CONSTRAINT adoptions_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.evaluations(id);


--
-- Name: anon_releases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.anon_releases (
    id integer NOT NULL,
    evaluation_id integer NOT NULL,
    name character varying(120) DEFAULT ''::character varying,
    state character varying(20) NOT NULL DEFAULT 'pending'::character varying,
    roster json NOT NULL,
    lower double precision NOT NULL,
    upper double precision NOT NULL,
    epsilon double precision NOT NULL,
    artifact_path character varying(300) DEFAULT ''::character varying,
    result json,
    error text DEFAULT ''::text,
    attempts integer DEFAULT 0,
    created character varying(40),
    updated character varying(40)
);


CREATE SEQUENCE public.anon_releases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.anon_releases_id_seq OWNED BY public.anon_releases.id;


--
-- Name: privacy_budgets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.privacy_budgets (
    id integer NOT NULL,
    consultant_code character varying(60) NOT NULL,
    total_epsilon double precision NOT NULL,
    spent_epsilon double precision NOT NULL DEFAULT 0.0
);


CREATE SEQUENCE public.privacy_budgets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.privacy_budgets_id_seq OWNED BY public.privacy_budgets.id;


--
-- Name: privacy_ledger; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.privacy_ledger (
    id integer NOT NULL,
    release_id integer NOT NULL,
    consultant_code character varying(60) NOT NULL,
    epsilon double precision NOT NULL,
    created character varying(40)
);


CREATE SEQUENCE public.privacy_ledger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.privacy_ledger_id_seq OWNED BY public.privacy_ledger.id;


ALTER TABLE ONLY public.anon_releases ALTER COLUMN id SET DEFAULT nextval('public.anon_releases_id_seq'::regclass);
ALTER TABLE ONLY public.privacy_budgets ALTER COLUMN id SET DEFAULT nextval('public.privacy_budgets_id_seq'::regclass);
ALTER TABLE ONLY public.privacy_ledger ALTER COLUMN id SET DEFAULT nextval('public.privacy_ledger_id_seq'::regclass);


ALTER TABLE ONLY public.anon_releases
    ADD CONSTRAINT anon_releases_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.anon_releases
    ADD CONSTRAINT anon_releases_evaluation_id_fkey FOREIGN KEY (evaluation_id) REFERENCES public.evaluations(id);
ALTER TABLE ONLY public.privacy_budgets
    ADD CONSTRAINT privacy_budgets_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.privacy_budgets
    ADD CONSTRAINT privacy_budgets_consultant_code_key UNIQUE (consultant_code);
ALTER TABLE ONLY public.privacy_ledger
    ADD CONSTRAINT privacy_ledger_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.privacy_ledger
    ADD CONSTRAINT uq_ledger_release_consultant UNIQUE (release_id, consultant_code);
ALTER TABLE ONLY public.privacy_ledger
    ADD CONSTRAINT privacy_ledger_release_id_fkey FOREIGN KEY (release_id) REFERENCES public.anon_releases(id);


--
-- PostgreSQL database dump complete
--

\unrestrict FeGD4O2uDApdumldMxv1Y2sYPyqZllXgtyDsNNMh2EeQwQqXvPWaXXuO8gzTddN

