---
name: catforge-fact-sync
description: Read TV category definitions and authorized SKU facts into a versioned CatForge GBrain snapshot.
---

Run snapshot.py with the project, TV source batch, target SKU, private output path and a read-only psql transport. Use sync.py with the resulting snapshot directory, private state directory and dedicated GBrain home with the project pack installed. The receipt names the hash-verified native readback consumed by the scoring skills.

catforge_insight exposes SKU parameter and claim summaries, comment dimensions and market observations. The read-only SQL additionally supplies original claim keys, sentence atoms, polarity, matched and contradicted codes, weekly rows, evidence row hashes, exact module versions and complete market peers. The active serving comment batch, serving claim batch and fixed historical fact batch are selected separately. Inspect missing versions explicitly. Full review texts and processing history remain in CatForge. Definition loaders run only at snapshot creation. The domain skills have neither credentials nor a SQL path.

For store prices (#11), preserve store, channel, SKU/offer, price type, currency, observation time/time zone, effective period, source record and revision or withdrawal watermark. A weekly online weighted price and a timestamped store offer have different grains. When store observations are unavailable, report that coverage gap. Track changed SKU hashes and the two affected market pools in the private sync receipt.
