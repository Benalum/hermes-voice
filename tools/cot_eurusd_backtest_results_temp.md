# EUR COT disagreement backtest — final conservative run

Date run: 2026-08-13/14. Data: CFTC Traders in Financial Futures (Euro FX, market code 099741) and Federal Reserve H.10/FRED DEXUSEU EUR/USD. CFTC history: 2006-06-13 through 2026-08-04. 1,052 CFTC weekly rows; 1,036 rows retained after excluding the abnormal 2025 shutdown/catch-up report block. Entries use the first available EUR/USD observation on/after Wednesday of the week following the CFTC Tuesday position date (Tuesday + 8 calendar days), a conservative anti-lookahead assumption.

## Current Aug. 4, 2026 positioning

Open interest 799,909. Asset Manager long 445,903, short 226,641, net +219,262 (+27.41% of OI). Leveraged Funds long 95,389, short 147,594, net -52,205 (-6.53% of OI). Dealer/Intermediary long 51,250, short 255,728, net -204,478 (-25.56% of OI).

Leveraged net/OI is at the 39.64th percentile of the full 2006–2026 history, but at only the 5.77th percentile of the most recent 156 reports. Raw leveraged net is at the 2.56th percentile of the last 156 reports. Asset-manager net/OI is at the 8.33rd percentile of the last 156 reports (raw net 14.10th percentile). Thus leveraged funds are unusually bearish relative to the recent three-year window, but not historically extreme on a 20-year open-interest-normalized basis.

## Asset Managers net long AND Leveraged Funds net short

418 valid signal weeks, 38 contiguous independent episodes. Weekly positive-EUR/USD rates: 1w 48.32%, 2w 48.43%, 4w 47.70%, 8w 49.14%, 13w 43.28%. Median returns: 1w -0.035%, 2w -0.034%, 4w -0.123%, 8w -0.068%, 13w -0.514%. At 13 weeks, EUR/USD was lower 56.48% of observations versus higher 43.28%; the bullish hit rate was 5.84 percentage points below the unconditional historical up rate.

At the START of each independent disagreement episode: positive-EUR/USD rates were 47.37% at 1w, 52.63% at 2w, 57.89% at 4w, 59.46% at 8w, and 48.65% at 13w. Median returns were -0.047%, +0.165%, +0.951%, +0.139%, and -0.059%. Confidence intervals are wide because there are only 37–38 independent episodes.

## Exact three-way condition: Asset Managers +, Leveraged Funds -, Dealers -

297 valid weeks, 35 independent episodes. Weekly positive-EUR/USD rates: 1w 48.47%, 2w 50.00%, 4w 47.95%, 8w 45.83%, 13w 40.63%. Weekly negative rates: 50.85%, 49.66%, 51.37%, 54.17%, 59.03%. Median returns: -0.019%, +0.004%, -0.080%, -0.337%, -0.622%.

At independent three-way episode starts: positive-EUR/USD rates were 45.71% at 1w, 60.00% at 2w, 62.86% at 4w, 58.82% at 8w, and 44.12% at 13w. Median returns: -0.095%, +0.431%, +1.095%, +0.362%, -0.506%. This suggests early/mid-horizon reversal tendency at episode onset, but no persistent 13-week bullish edge.

## Exact three-way condition PLUS prior 4-week EUR/USD decline

170 valid weeks and 47 bearish-trend regime episodes. Weekly positive-EUR/USD rates: 48.82% at 1w, 50.59% at 2w, 46.15% at 4w, 44.85% at 8w, 39.39% at 13w. Weekly negative rates: 50.59%, 49.41%, 53.25%, 55.15%, 60.61%.

At independent bearish-trend regime starts: positive-EUR/USD rates were 40.43% at 1w, 46.81% at 2w, 46.81% at 4w, 43.48% at 8w, and 34.78% at 13w. Negative rates were 57.45%, 53.19%, 53.19%, 56.52%, and 65.22%. Median returns: -0.158%, -0.114%, -0.055%, -0.777%, -0.991%. This is the broad historical sample most directly matching “institutions bullish, leveraged funds/dealers bearish, price already trending down,” and it favors bearish continuation, especially at 8–13 weeks.

## Truly extreme leveraged-short cases (full-history net/OI percentile)

When Asset Managers were long, Leveraged Funds short, and leveraged net/OI was in the bottom 5% of the full 20-year history (n=14): EUR/USD was lower 64.29% after 1 week, 78.57% after 2 weeks, 64.29% after 4 weeks, 42.86% after 8 weeks, and 57.14% after 13 weeks. Median returns were -0.507%, -0.954%, -1.116%, +0.060%, -0.887%. The small n means uncertainty is large, but historically extreme leveraged shorts were not an automatic squeeze signal; they often correctly anticipated further weakness over the following 1–4 weeks. Current Aug. 4 positioning does NOT qualify as a bottom-5%, bottom-10%, or bottom-25% full-history net/OI extreme.

## Nearest independent current-like three-way episode analogues

The 10 nearest independent three-way episode starts by normalized Asset Manager/Leveraged Fund/Dealer net position as a fraction of open interest had positive-EUR/USD rates of 40% at 1w, 70% at 2w, 70% at 4w, 70% at 8w, and 50% at 13w. Median returns were -0.047%, +0.599%, +1.564%, +1.870%, +1.266%. With only 10 analogues, this is descriptive rather than statistically decisive.

When those analogues are additionally restricted to cases where EUR/USD had already fallen during the prior four weeks, the 10 nearest independent analogues were positive only 30% at 1w, 40% at 2w, 50% at 4w, 40% at 8w, and 30% at 13w. Negative rates were 70%, 60%, 50%, 60%, and 70%. Median returns were -0.415%, -0.241%, -0.122%, -0.812%, and -1.184%. These closest trend-matched analogues therefore favor near-term and medium-term bearish continuation rather than an immediate squeeze.

## Interpretation

Dealer/Intermediary net shorts should not be read as a pure bank directional forecast because the CFTC Dealer category is sell-side and often reflects client accommodation and risk intermediation. The most meaningful directional disagreement is Asset Managers versus Leveraged Funds. Broad history does not show that Asset Managers simply “win” whenever they are long and Leveraged Funds are short. At the onset of a new disagreement regime, Asset Managers have historically had a modest 2–8 week reversal tendency; once EUR/USD is already in a four-week downtrend and Dealers are also net short, the continuation side has historically won more often, especially at 8–13 weeks. Current leveraged positioning is unusually bearish compared with the last ~3 years, but not exceptionally bearish compared with the full 20-year history normalized for open interest.
