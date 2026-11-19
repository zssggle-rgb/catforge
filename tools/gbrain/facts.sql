\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = public, pg_catalog;

-- Each output line is a (family, SKU, input record) tuple. Only source facts are accessible here.
WITH scope AS (
  SELECT sku_code FROM core3_sku_param_profile
  WHERE project_id = :'project' AND batch_id = :'batch' AND category_code = 'TV'
    AND rule_version = 'm03b_tv_param_profile_v0.2' AND sku_code LIKE 'TV%'
), comments AS (
  SELECT DISTINCT ON (p.sku_code) p.*
  FROM core3_sku_comment_fact_profile p JOIN scope USING (sku_code)
  JOIN core3_source_batch b ON b.batch_id = p.batch_id
  WHERE p.project_id = :'project' AND p.category_code = 'TV' AND p.product_category = 'TV'
    AND p.is_current AND p.rule_version = 'm05c_tv_comment_fact_profile_v0.2'
  ORDER BY p.sku_code, b.scan_started_at DESC NULLS FIRST, p.batch_id DESC, p.updated_at DESC, p.comment_profile_id DESC
), serving_claim AS (
  SELECT DISTINCT ON (p.sku_code) p.sku_code,p.batch_id FROM core3_sku_claim_fact_profile p
  JOIN scope USING (sku_code) JOIN core3_source_batch b ON b.batch_id=p.batch_id
  WHERE p.project_id=:'project' AND p.category_code='TV' AND p.product_category='TV'
    AND p.rule_version='m04c_tv_claim_fact_profile_v0.2' AND p.is_current
  ORDER BY p.sku_code,b.scan_started_at DESC NULLS FIRST,p.batch_id DESC,p.updated_at DESC
), facts(family,sku_code,payload) AS (
  SELECT 'sku',s.sku_code,to_jsonb(s) FROM (
    SELECT sku_code,brand_name,model_name,clean_sku_id,clean_hash,field_conflicts_json,quality_status
    FROM core3_clean_sku JOIN scope USING(sku_code)
    WHERE project_id=:'project' AND category_code='TV' AND batch_id=:'batch') s
  UNION ALL SELECT 'parameter',p.sku_code,to_jsonb(p) FROM (
    SELECT sku_code,model_name,param_values_json,profile_hash,rule_version,seed_version,evidence_ids
    FROM core3_sku_param_profile JOIN scope USING(sku_code)
    WHERE project_id=:'project' AND category_code='TV' AND batch_id=:'batch' AND rule_version='m03b_tv_param_profile_v0.2') p
  UNION ALL SELECT 'claim_profile',p.sku_code,to_jsonb(p) FROM (
    SELECT p.sku_code,p.batch_id,p.brand_name,p.fact_claim_codes,p.profile_hash,p.rule_version,p.taxonomy_version
    FROM core3_sku_claim_fact_profile p JOIN scope USING(sku_code)
    WHERE p.project_id=:'project' AND p.category_code='TV' AND p.is_current
      AND (p.batch_id=:'batch' OR (p.sku_code,p.batch_id) IN (SELECT * FROM serving_claim))
      AND p.rule_version IN ('m04c_tv_claim_fact_profile_v0.1','m04c_tv_claim_fact_profile_v0.2')) p
  UNION ALL SELECT 'claim',c.sku_code,to_jsonb(c) FROM (
    SELECT c.sku_code,c.batch_id,c.claim_fact_id,c.source_claim_key,c.raw_claim_text,c.clean_claim_text,c.claim_code,
      c.claim_name,c.fact_claim_flag,c.claim_kind,c.service_separate_flag,c.param_support_status,c.supporting_param_codes,
      c.claim_dimension,c.claim_subtype,c.match_score,c.claim_seq,c.supporting_param_snapshot_json,
      c.param_support_level,c.param_support_specificity,c.primary_supporting_param_codes,c.generic_support_param_codes,
      c.source_claim_group_id,c.same_source_param_group_id,c.canonical_claim_code,c.canonical_claim_name,c.wtp_input_guard,
      c.evidence_ids,c.confidence,c.rule_version,c.taxonomy_version,c.fact_hash
    FROM core3_sku_claim_fact c JOIN scope USING(sku_code)
    WHERE c.project_id=:'project' AND c.category_code='TV' AND c.is_current
      AND (c.batch_id=:'batch' OR (c.sku_code,c.batch_id) IN (SELECT * FROM serving_claim))
      AND c.rule_version IN ('m04c_tv_claim_fact_profile_v0.1','m04c_tv_claim_fact_profile_v0.2')) c
  UNION ALL SELECT 'serving_claim',s.sku_code,to_jsonb(s) FROM serving_claim s
  UNION ALL SELECT 'comment_profile',p.sku_code,to_jsonb(p)-ARRAY['created_at','updated_at','evidence_examples_json'] FROM comments p
  UNION ALL SELECT 'comment_counts',c.sku_code,jsonb_build_object('clean_rows',count(*),
      'distinct_comment_ids',count(DISTINCT c.comment_id),'rows_without_comment_id',count(*) FILTER (WHERE c.comment_id IS NULL))
    FROM core3_clean_comment c JOIN comments p USING(sku_code,batch_id)
    WHERE c.project_id=:'project' AND c.category_code='TV' GROUP BY c.sku_code
  UNION ALL SELECT 'comment',c.sku_code,to_jsonb(c) FROM (
    SELECT a.sku_code,a.batch_id,a.comment_fact_id,a.source_comment_id,a.source_comment_key,a.sentence_seq,a.clean_comment_text,
      a.dimension_type,a.dimension_code,a.subdimension_code,a.polarity,a.support_relation,a.evidence_strength,
      a.supported_param_codes,a.contradicted_param_codes,a.supported_claim_codes,a.contradicted_claim_codes,
      a.evidence_ids,a.confidence,a.fact_hash
    FROM core3_comment_fact_atom a JOIN comments p USING(sku_code,batch_id,rule_version)
    WHERE a.project_id=:'project' AND a.category_code='TV' AND a.is_current) c
  UNION ALL SELECT 'market',m.sku_code,to_jsonb(m)-ARRAY['created_at','updated_at'] FROM core3_sku_market_profile m JOIN scope USING(sku_code)
    WHERE m.project_id=:'project' AND m.category_code='TV' AND m.batch_id=:'batch' AND m.is_current
      AND m.rule_version='m07_market_profile_v2' AND m.analysis_window='full_observed_window'
  UNION ALL SELECT 'week',w.sku_code,to_jsonb(w) FROM (
    SELECT sku_code,clean_market_id,clean_hash,source_row_id,period_week_index,channel_type,platform_type,sales_volume,sales_amount,avg_price
    FROM core3_clean_market_weekly JOIN scope USING(sku_code)
    WHERE project_id=:'project' AND category_code='TV' AND batch_id=:'batch' AND period_week_index IS NOT NULL
      AND record_status='active' AND quality_status='ok') w
  UNION ALL SELECT 'evidence',e.sku_code,to_jsonb(e) FROM (
    SELECT sku_code,batch_id,evidence_id,evidence_type,evidence_field,source_table,source_pk,source_row_id,
      source_row_hash,clean_record_key,clean_hash,raw_field,quality_status
    FROM core3_evidence_atom WHERE project_id=:'project' AND category_code='TV' AND sku_code=:'target'
      AND (batch_id=:'batch' OR batch_id IN (SELECT batch_id FROM comments WHERE sku_code=:'target')
      OR batch_id IN (SELECT batch_id FROM serving_claim WHERE sku_code=:'target'))) e
)
SELECT json_build_array(family,sku_code,payload) FROM facts;
COMMIT;
