# EUR/USD multifactor forecasting backtest — temporary research result

Run 2026-08-17 UTC on isolated branch `agent/cot-eurusd-backtest-20260813`. Historical daily EUR/USD and macro series span 2006-01-03 through the latest FRED H.10 observation available to the run, 2026-08-07. CFTC Traders in Financial Futures data were included through the 2026-08-11 report. Features included EUR/USD momentum and moving-average distance, realized volatility, U.S. 2Y/10Y yields and changes, Fed-vs-ECB policy-rate spread, broad dollar momentum, Brent oil, VIX, and Asset Manager/Leveraged Fund/Dealer CFTC net positioning as a fraction of open interest. The model was an ensemble of standardized logistic regression (60%) and histogram gradient boosting (40%), evaluated with expanding walk-forward yearly training from 2014 onward so future years were not used to train prior-year predictions.

## Always-on out-of-sample results

Daily 1-trading-day direction: n=3,148, accuracy 51.33%, AUC 0.531, versus 48.35% always-up frequency. Wednesday-only 1-day: n=646, accuracy 51.86%, AUC 0.571. Daily 5-day direction: n=3,144, accuracy 50.70%, AUC 0.512; Wednesday-only 5-day: n=645, accuracy 52.09%, AUC 0.531. Daily 10-day direction: n=3,139, accuracy 47.63%, AUC 0.480; the 10-day version had no useful out-of-sample skill.

Simple standalone rules were also close to chance. For example, at 10 trading days, 20-day momentum was 50.73% accurate, price relative to the 50-day average 50.58%, falling U.S. 2-year yield over five days 51.50%, policy-spread direction 50.99%, and the six-factor composite 50.46%. At 1 and 5 days most single-factor rules were around 48–51%.

## Selective-confidence result

The useful result was to abstain when the 1-day ensemble was not confident. With model probability at least 52.5% or at most 47.5%, accuracy was 52.33% on 2,293 forecasts (72.8% coverage). At >=55% / <=45%, accuracy was 53.70% on 1,501 forecasts (47.7% coverage). At >=57.5% / <=42.5%, accuracy was 55.76% on 825 forecasts (26.2% coverage). At >=60% / <=40%, accuracy was 57.37% on 448 forecasts (14.2% coverage). Confidence filtering did not materially improve the 5-day or 10-day models.

## Current-like historical regime

A regime approximating the live setup was tested: EUR/USD within 0.5% of its rolling 60-day high, U.S. 2-year yield down over the prior five trading days, Asset Managers net long EUR futures, and Leveraged Funds net short. Observations were spaced by at least five business days to reduce clustering. n=55 independent-ish observations: EUR/USD was higher 47.27% after 1 day, 45.45% after 5 days, and 49.09% after 10 days. Median returns were approximately 0.00%, -0.144%, and 0.00%. This broad regime had no dependable continuation edge.

Adding Brent oil up at least 5% over the prior 20 trading days reduced the sample to n=19. In those cases EUR/USD was higher 42.11% after 1 day, 31.58% after 5 days, and 47.37% after 10 days. Median returns were -0.145%, -0.439%, and -0.083%, respectively. This suggests that when EUR was already near a recent high and U.S. front-end yields were falling, a sharp oil rise historically increased short-term pullback risk, but n=19 is too small for a strong probability claim.

For the broader near-high + falling-2Y + COT-divergence regime, the next-five-day median maximum favorable EUR/USD excursion was +0.385% and the median maximum adverse excursion was -0.339%; the 75th-percentile maximum upside was +0.884% and 25th-percentile downside excursion was -0.891%. Applied mechanically to M6EU6 around 1.1595, those percentages correspond approximately to 1.1640 median upside excursion, 1.1556 median downside excursion, 1.1698 upper excursion, and 1.1492 lower excursion. These are historical excursion translations, not price targets.

## Current-model caveat

The downloaded FRED daily feature set stopped at 2026-08-07, before the important August 14 U.S. retail-sales and sentiment releases, although the August 11 CFTC report was injected. Therefore the model's raw current probabilities (53.65% up at 1 day, 52.71% at 5 days, 44.54% at 10 days) should not be treated as live forecasts. The validation results and regime tests are useful; current inference should be updated with live market and macro reactions.

## Research conclusion

There was no robust always-on EUR/USD direction rule in this feature set. The strongest result was a selective one-day ensemble that traded only high-confidence forecasts, reaching 55.76% accuracy at roughly 26% coverage and 57.37% at roughly 14% coverage in expanding walk-forward tests. Five- and ten-day point-direction models were too weak to justify trading without additional information. The next improvement should combine the macro/regime model with real-time CME order flow (aggressive buy/sell volume, cumulative delta, depth imbalance, replenishment/absorption, cancellations/additions, VWAP response) and event-surprise data (actual minus consensus for CPI, payrolls, retail sales, PMIs, central-bank decisions), while retaining walk-forward testing and a no-trade zone.