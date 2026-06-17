# 05 Acceptance Tests

## A. Data import acceptance

Given sample source files containing at least 5 SKUs, parameter rows, claim rows, comments, and market facts:
- data overview shows correct row counts
- missing and unknown values are counted as unknown, not false
- source evidence IDs are created

## B. Asset library acceptance

After running asset generation:
- parameter library has rows for screen size, mini_led_flag, refresh_rate_hz, brightness_nits, dimming_zones, hdmi_2_1_ports
- claim library has rows for Mini LED backlight, high brightness HDR, fine local dimming, high refresh rate, HDMI 2.1, eye comfort
- comment topic library includes picture quality, sport watching, game experience, elderly ease-of-use, installation service
- task library includes home cinema, premium picture, gaming, sports viewing, large-screen upgrade, elderly ease-of-use
- battlefield library includes premium picture, family viewing, gaming TV, large-screen upgrade, eye comfort

## C. SKU result acceptance

For TV00029115-like SKU:
- activated claims include Mini LED, high brightness, local dimming, high refresh rate, HDMI 2.1
- tasks include premium picture and family viewing
- battlefields include premium picture and family viewing
- claim value layers include at least one competitive performance and one potential premium-support claim
- evidence_ids are present for every output

## D. Competitor result acceptance

Given fixture SKUs:
- direct competitors are same category, similar price band, overlapping battlefield, and similar core claims
- benchmark competitors have stronger market/claim signals
- substitute competitors solve same task but differ in technology/price route
- output contains component scores and evidence cards

## E. Calibration report acceptance

Report must include:
- parameter coverage
- claim coverage
- PSI
- SSI
- CPI
- sample sufficiency
- review status summary
- release recommendation

## F. UI acceptance

User can navigate to:
- Data Overview
- Parameter Library
- Claim Library
- Comment Topic Library
- User Task Library
- Target Group Library
- Battlefield Library
- Mapping Workbench
- SKU Results
- SKU Detail
- Competitor Results
- Calibration Report
- Runtime Export Preview
