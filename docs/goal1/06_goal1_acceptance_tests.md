# Goal 1 Acceptance Tests

## Test categories
1. Rule DSL validation.
2. Rule DSL execution.
3. Feature extraction evidence completeness.
4. Claim/task/battlefield pipeline.
5. Competitor engine.
6. Gold Set evaluation and calibration.

## Required test cases
- Invalid DSL operator fails validation with a useful message.
- Changing claim rule threshold changes activation result.
- Missing boolean parameter returns unknown, not false.
- Target SKU `TV00029115` activates Mini LED, high brightness, dimming zones, high refresh, HDMI 2.1.
- `TV00029115` enters premium picture and family viewing battlefields.
- Competitor engine outputs at least one direct, one benchmark, and one substitute competitor from fixture.
- Every competitor relation includes non-empty evidence IDs and component scores.
- Gold Set import succeeds and evaluation report includes metrics.
- Calibration creates draft candidate changes but does not auto-release.
