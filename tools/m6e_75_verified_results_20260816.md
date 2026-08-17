# M6E ≥75% prediction search — verified result

Run date: 2026-08-16/17. This file records the final leakage-audited result from the isolated branch `agent/m6e-75-verify-20260816`.

## Goal and safeguards

The target was at least 75% out-of-sample directional/first-hit accuracy, not merely a model probability of 75%. Apparent high-accuracy results caused by daily FX bar-boundary leakage, current-day aggregation leakage, stale Yahoo spot prints, flat/sub-tick M6E labels, or unresolved same-bar target/stop ordering were rejected. The final verification used one-minute M6E and 6E data to resolve the future price path, five-minute completed bars for predictors, a train/validation/locked-holdout structure, thresholds selected before the holdout, conservative losses when both symmetric barriers were hit within the same one-minute bar, and a non-overlapping-signal analysis.

One-minute data were fetched in six-day chunks and stitched together. M6E had 20,127 one-minute rows and 6E had 26,525; 19,403 exact timestamps were common. These produced 5,264 completed five-minute feature bars from 2026-07-20 00:05 UTC through 2026-08-14 21:00 UTC. Validation was before the locked Aug. 10–14 holdout; the holdout was not used to choose the model-confidence threshold.

## Strict one-tick symmetric barrier result

For a symmetric +1 tick / -1 tick M6E barrier, 15-minute horizon, the confidence threshold selected on validation was 0.80. Validation had 136 signals and 91.91% accuracy. On the locked Aug. 10–14 holdout, there were 157 signals and 90.45% accuracy. After enforcing non-overlap so a new signal could not occur until the prior 15-minute horizon expired, there were 127 independent-ish signals and 91.34% accuracy. The 95% Wilson lower bound was 85.15%, above the requested 75% threshold. The non-overlapping outcomes comprised 70 first-down hits, 55 first-up hits, and 2 one-minute ambiguous hits; ambiguous hits were counted as losses. Mean gross outcome was +0.827 M6E ticks per non-overlapping signal.

Other one-tick horizons also remained above 75% in the locked non-overlapping holdout: 30 minutes 88.89% on n=99 (95% Wilson lower 81.19%); 60 minutes 86.96% on n=69 (lower 77.03%); 120 minutes 88.10% on n=42 (lower approximately 75.00%).

## Two-tick symmetric barrier result

For +2/-2 ticks over 30 minutes, validation selected threshold 0.725 and achieved 75.00% on n=136. Locked holdout accuracy was 79.59% on n=98. With non-overlap, accuracy was 77.92% on n=77, with a 95% Wilson lower bound of 67.46%. Mean gross outcome was +1.156 ticks per non-overlapping signal. Thus the observed hit rate exceeds 75%, but the sample is not large enough for the 95% lower confidence bound itself to exceed 75%.

For +2/-2 ticks over 15 minutes, locked holdout accuracy was 80.56% on n=36; non-overlap was 80.00% on n=35, but the 95% lower bound was only 64.11%.

## Larger barriers

Three-tick symmetric barriers did not retain the 75% edge in the strict holdout. The best listed strict three-tick results were approximately 63% or lower on meaningful samples. Five-tick configurations were near chance or unstable. Therefore the verified ≥75% edge is currently concentrated in very short, small-price movements rather than a larger swing forecast.

## Interpretation

The ≥75% research goal was achieved statistically: the one-tick, 15-minute non-overlapping locked holdout was 91.34% accurate with a 95% lower confidence bound of 85.15%. This should not be equated with a profitable live trading system. The edge is concentrated at one M6E tick, so transaction costs, spread, queue position, slippage, partial fills, and live data latency are economically decisive. The next research target should be to preserve ≥75% accuracy while increasing expected movement size, preferably via a two-stage model that first predicts whether a 3–5 tick move is likely and then predicts direction, and/or by incorporating true CME trade/order-flow data and economic-event surprises.
