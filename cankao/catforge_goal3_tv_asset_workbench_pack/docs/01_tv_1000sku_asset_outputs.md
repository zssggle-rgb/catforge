# 01 TV 1000-SKU Asset Outputs

CatForge must produce two different things:

1. TV Category Asset Libraries
2. TV SKU-Level Analysis Results

## A. TV Category Asset Libraries

These are reusable TV category assets.

### A1. Standard Parameter Library

Purpose:
Define normalized TV parameters, aliases, units, type, levels, and business meaning.

Generated from:
- Raw SKU parameter fields
- Raw SKU parameter values
- Derived parameters extracted from promotional claims
- Field coverage statistics
- Expert review decisions

Not generated from:
- Price/sales directly, except for parameter importance and review priority.

Required fields:
- param_code
- param_name
- param_group
- data_type
- unit
- raw_aliases
- normalize_rule
- level_rule
- business_meaning
- mapped_claim_codes
- field_coverage_rate
- value_unknown_rate
- example_raw_fields
- example_raw_values
- evidence_ids
- generation_method
- confidence
- review_status
- asset_version

### A2. Standard Claim Library

Purpose:
Define normalized TV standard claims such as Mini LED backlight, high brightness HDR, fine local dimming, high refresh rate, HDMI 2.1 game connectivity, eye comfort, voice ease-of-use.

Generated from:
- Raw promotional claim text
- Derived parameters extracted from promotional text
- Normalized parameters
- Comment topics
- Claim coverage statistics
- Market support metrics: coverage, PSI, SSI, CPI
- Expert review decisions

Required fields:
- claim_code
- claim_name
- claim_group
- definition
- activation_rule
- raw_keywords
- supporting_param_codes
- comment_topic_codes
- mapped_task_codes
- mapped_battlefield_codes
- default_value_layer_hint
- coverage_rate
- psi_price_support
- ssi_sales_support
- cpi_comment_perception
- sample_sufficiency
- example_raw_claims
- evidence_ids
- generation_method
- confidence
- review_status
- asset_version

### A3. Comment Topic Library

Generated from:
- Raw user comments
- Comment sentence splitting
- Sentiment classification
- Product/service experience classification
- Mapping to claims and tasks
- Expert review

Required fields:
- topic_code
- topic_name
- topic_group
- product_or_service
- sentiment_scope
- raw_keywords
- example_sentences
- mapped_claim_codes
- mapped_task_codes
- mention_rate
- positive_rate
- negative_rate
- confidence
- review_status

### A4. User Task Library

Generated from:
- Standard claims
- Normalized parameters
- Comment topics
- Market facts by price band/channel
- Seed ontology
- Expert review

Required fields:
- task_code
- task_name
- definition
- positive_claim_codes
- positive_param_codes
- positive_comment_topic_codes
- negative_or_weak_signals
- mapped_target_group_codes
- mapped_battlefield_codes
- scoring_rule_id
- example_skus
- evidence_ids
- confidence
- review_status

### A5. Target Group Library

Generated from:
- User tasks
- Price bands
- Channel behavior
- Comment language
- Market performance
- Expert review

Required fields:
- target_group_code
- target_group_name
- definition
- source_task_codes
- price_band_signals
- channel_signals
- comment_topic_signals
- example_skus
- confidence
- review_status

### A6. Value Battlefield Library

Generated from:
- User tasks
- Standard claim bundles
- Target groups
- Price band/channel/sales patterns
- Competitor density
- Expert review

Required fields:
- battlefield_code
- battlefield_name
- definition
- core_task_codes
- core_claim_codes
- core_param_codes
- target_group_codes
- entry_rule
- main_threshold
- secondary_threshold
- opportunity_threshold
- weak_threshold
- example_skus
- market_density
- confidence
- review_status

### A7. Mapping Rules

Mappings are not decorative. They are the engine's semantic graph.

Required mappings:
- param -> claim
- claim -> task
- comment_topic -> claim
- comment_topic -> task
- task -> target_group
- task -> battlefield
- claim -> battlefield
- battlefield -> competitor_rule

Each mapping must include:
- source_code
- target_code
- relation_type
- weight
- condition
- evidence_basis
- confidence
- review_status
- asset_version

## B. TV SKU-Level Analysis Results

Generated after the released asset libraries are applied to the 1000-SKU dataset.

Required outputs:
- sku_signal_card
- normalized_parameters per SKU
- activated_standard_claims per SKU
- comment_topic_evidence per SKU
- user_task_scores per SKU
- target_group_scores per SKU
- battlefield_scores per SKU
- claim_value_layers per SKU
- competitor_relationships per SKU and battlefield
- evidence_cards
- review_flags

These outputs are the actual production deliverables, not just pipeline logs.
