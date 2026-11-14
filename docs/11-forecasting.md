# 11. Forecasting (Projection): a probability cone for the path ahead

Code: `src/rinng/analysis/forecast.py`, the `forecast` lens in `src/rinng/web/lenses.py`.
Analysis only, not a trading recommendation.

## Why a cone and not a line

Short-term crypto prices are close to random. A single "price will go like this" line always looks more certain
than reality. What can be measured and validated is the **distribution**: the range price is likely to be in after
H bars, and the probability of touching each important price level.

## Method

1. **Volatility** sigma_t: EWMA of log returns (lambda 0.94). Every path is scaled by its own
   sigma, so high- and low-volatility periods in the past are comparable to the present.
2. **State** of each bar (8 features, using only data up to that bar): 1/5/20/60-bar returns in
   sigma units, volatility regime (sigma / 200-bar standard deviation), position within the 50-bar range, RSI 14,
   volume relative to the 50-bar average.
3. **Analog situations**: the K past bars closest to the current state (K ≈ pool/15, 100–600),
   only bars whose following H bars ended before now. Kernel weights by distance.
4. **Blend** 70% of the conditional distribution with 30% of the distribution of all past paths, so as not to over-trust
   a small group.
5. **Output**: 5/10/25/50/75/90/95% quantiles for each step 1..H (the cone), and the probability of touching a price
   level = the weighted share of paths whose high/low touches that level within H bars.

H per timeframe: 15m/1h: 48 bars, 4h: 42 (≈ 7 days), 1d: 30, 1w: 12. Path pool: at most 20,000 historical bars
of that timeframe. Recomputed when a bar of that timeframe closes (same realtime mechanism).

## Walk-forward validation

The exact same procedure is rerun at 250 points in the past, each seeing only data before it, and compared with the actual
price after H bars. The numbers are shown on the chart and dashboard. Results as of 2026-11-14 (Binance):

| Pair | Timeframe | 50% band coverage | 80% band coverage | 90% band coverage | Correct direction | Skill vs. unconditional |
|---|---|---|---|---|---|---|
| BTC | 1h (H=48) | 50% | 80% | 90% | 52% | 0.0% |
| BTC | 4h (H=42) | 51% | 83% | 90% | 49% | −0.3% |
| BTC | 1d (H=30) | 53% | 81% | 91% | 55% | +3.7% |
| ETH | 1h | 56% | 81% | 90% | 52% | +1.0% |
| ETH | 4h | 54% | 79% | 91% | 47% | −0.6% |
| ETH | 1d | 47% | 74% | 86% | 46% | −1.8% |

Reading the results:
- **The cone width is reliable**: the bands contain the actual outcome close to their nominal rates. ETH 1d alone
  is slightly narrow: the 80% band contains only 74%.
- **Direction is not predictable**: the median gets the direction right about 50% of the time, and skill versus the unconditional
  distribution is about 0. This is a real result, not a bug; the UI says plainly "not a direction call".
- What is usable: a reasonable range of movement and the probability of touching BSL/SSL/POC/VAH/VAL within H bars.

## Tests

`tests/analysis/test_forecast.py`: no look-ahead (a forecast on truncated data = the forecast on the full
data at the same point), quantiles are ordered and widen over time, touch probabilities are monotonic,
and on a random walk the bands are correctly calibrated while skill ≈ 0 (no "phantom skill").

## Possible improvements (each change must pass walk-forward before use)

- Add derivatives features (funding, OI change, CVD) to the state.
- Choose `blend` and K by walk-forward per timeframe (beware overfitting: separate the selection period from
  the scoring period).
- Recalibrate (conformal) when coverage is off, e.g. ETH 1d.
