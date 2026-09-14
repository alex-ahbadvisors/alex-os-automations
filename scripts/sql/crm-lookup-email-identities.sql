-- Reviewable migration: read-only exact email/merge lookup for capture.
-- No deployment in the implementation task. Requires existing service_role.
BEGIN;
CREATE OR REPLACE FUNCTION public.crm_lookup_email_identities(p_emails text[])
RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path = pg_catalog, public
AS $lookup$
DECLARE result jsonb;
BEGIN
  IF p_emails IS NULL OR cardinality(p_emails) > 1000 OR EXISTS (
    SELECT 1 FROM unnest(p_emails) e
    WHERE e IS NULL OR btrim(e, E' \t\n\r\f\013' || U&'\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF') = '' OR length(e) > 320
  ) THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'crm_identity_lookup_invalid_input';
  END IF;
  -- Trim the ECMAScript whitespace set used by Participants (including VT,
  -- NBSP and BOM); never use PostgreSQL E-string \v, which means letter v.
  -- Return one scalar JSON envelope, not SETOF contacts: PostgREST's row cap
  -- must never hide another owner and turn ambiguity into an apparent match.
  WITH RECURSIVE requested AS (
    SELECT DISTINCT lower(btrim(e, E' \t\n\r\f\013' || U&'\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF')) AS email
    FROM unnest(p_emails) e
  ), walk AS (
    SELECT r.email, c.id AS owner_id, c.id, c.merged_into,
      c.review_status::text AS review_status, c.relationship_tier,
      c.updated_at, ARRAY[c.id] AS path, false AS cycle,
      false AS missing, 1 AS depth
    FROM requested r JOIN public.contacts c ON EXISTS (
      SELECT 1 FROM unnest(c.emails) stored
      WHERE lower(btrim(stored, E' \t\n\r\f\013' || U&'\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF')) = r.email
    )
    UNION ALL
    SELECT w.email, w.owner_id, c.id, c.merged_into,
      c.review_status::text, c.relationship_tier, c.updated_at,
      w.path || w.merged_into, w.merged_into = ANY(w.path),
      c.id IS NULL, w.depth + 1
    FROM walk w LEFT JOIN public.contacts c ON c.id = w.merged_into
    WHERE w.merged_into IS NOT NULL AND NOT w.cycle AND NOT w.missing
      AND w.depth < 100
  ), terminals AS (
    SELECT *, CASE
      WHEN cycle THEN 'cycle'
      WHEN missing THEN 'missing_target'
      WHEN merged_into IS NOT NULL THEN 'depth_limit'
      WHEN review_status = 'merged' THEN 'merged_without_target'
      ELSE 'ok' END AS resolution
    FROM walk
    WHERE merged_into IS NULL OR cycle OR missing OR depth = 100
  )
  SELECT jsonb_build_object('schema_version', 1, 'identities',
    COALESCE(jsonb_agg(jsonb_build_object('email', r.email, 'owners', (
      SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'owner_id', t.owner_id,
        'canonical_id', CASE WHEN t.resolution = 'ok' THEN t.id ELSE NULL END,
        'resolution', t.resolution, 'path', t.path,
        'review_status', t.review_status,
        'relationship_tier', t.relationship_tier, 'updated_at', t.updated_at
      ) ORDER BY t.owner_id), '[]'::jsonb)
      FROM terminals t WHERE t.email = r.email
    )) ORDER BY r.email), '[]'::jsonb)) INTO result
  FROM requested r;
  RETURN result;
END;
$lookup$;
REVOKE ALL ON FUNCTION public.crm_lookup_email_identities(text[]) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.crm_lookup_email_identities(text[]) TO service_role;
COMMIT;
-- Supervised rollback: DROP FUNCTION public.crm_lookup_email_identities(text[]);
-- This function changes no contacts, table grants, RLS policies, or review state.
