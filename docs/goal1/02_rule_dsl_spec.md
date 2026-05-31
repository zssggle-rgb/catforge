# Configurable Rule DSL Specification

## Purpose
Move business logic out of Python/TypeScript conditionals into validated YAML/JSON rules.

## Rule set fields
- `rule_set_id`: unique ID.
- `category`: e.g. `TV`.
- `rule_type`: one of `claim_activation`, `task_score`, `battlefield_score`, `competitor_score`, `review_trigger`.
- `version`: semantic version.
- `status`: `draft`, `active`, `deprecated`.
- `rules`: list of rule definitions.

## Supported condition operators
- `eq`, `neq`
- `gt`, `gte`, `lt`, `lte`
- `in`, `not_in`
- `exists`, `missing`
- `regex`, `contains`
- `range`
- `any`, `all`, `not`

## Feature namespace
- `param.<code>`: normalized parameter feature, e.g. `param.mini_led_flag`.
- `claim_text`: raw or normalized claim text.
- `comment_topic.<code>`: aggregated comment topic score/count.
- `market.<code>`: market fact feature, e.g. `market.avg_price`, `market.sales_volume`.
- `derived.<code>`: computed features such as `derived.price_band`.
- `claim.<code>`: activated standard claim score.
- `task.<code>`: task score.
- `battlefield.<code>`: battlefield score.

## Score model
Each rule can define weighted score components. The engine must return:
- `score`: normalized 0-100.
- `confidence`: `high`, `medium`, `low`, `insufficient_sample`.
- `evidence_ids`: list of evidence IDs that triggered the rule.
- `review_status`: `auto_pass`, `needs_review`, or `blocked`.

## Example
See `examples/rules/tv_claim_activation.yaml`.

## Validation
Rule files must be validated against `schemas/rule_dsl.schema.json` before use. Invalid rule files must fail fast with actionable errors.
