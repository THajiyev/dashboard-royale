# Does weather explain play? (competing-explanation check)

**Question.** Did summer heat cause the June decline, and should weather be a forecast input?

**Answer.**
- **Ordinary heat doesn't matter.** A day hotter than the days around it shows no change in play.
- **Extreme heat (40°C or higher) is linked to slightly lower play:** about −3.5% on the floor and −6% for locals. All 9 such days fall in late May–June, though, so heat can't be cleanly separated from that month's tourism slump. Even taken at face value, extreme heat explains only about 1 point of June's ~5% shortfall.
- **Rain lowers play clearly,** mostly among locals (about −18%), and it explains the forecast's worst ordinary-day misses in early May. There are only 4 rainy days in the data, however.
- **Neither can be used as an input to a forecast made weeks ahead.** Even a perfect weather forecast would have improved the headline model's May–Jun error by only about 5%.

**Data.** NOAA daily weather at the Las Vegas airport (`data/4_context/real_sources/weather_daily`, real data), Jan 1 – Jun 30, 2025. The analysis uses the 148 ordinary (non-event) days.

**Code and results**, in `experiments/iter5/`:
- `weather_check.py` → `weather_check.csv`, `weather_monthly.csv`
- `weather_robustness.py` → `weather_robustness.csv`

## Method

For each ordinary day, I measured how far play was above or below what was expected for that **weekday** and that **fortnight**:
- the log of theo,
- minus the weekday average,
- minus a centred 15-day rolling median.

This removes the weekly cycle and slow trends, which would otherwise be confused with the seasons.

I then regressed this daily residual on two weather measures:
- **Temperature:** the daily high minus its centred 15-day average, i.e. a day hotter or cooler than the days around it.
- **Rain day:** more than 1 mm of precipitation.

Standard errors are Newey-West with 7 lags. Floor total, locals and visitors (non-locals) are run separately.

## Main results

**Day-to-day effects**

| Series | Day 10°C hotter than recent days | 95% CI | Rain day | 95% CI |
|---|---:|---|---:|---|
| Floor total | **0.0%** (p = 0.96) | −1.7% to +1.8% | **−8.9%** | −12.0% to −5.7% |
| Locals | −0.9% (p = 0.39) | −2.9% to +1.2% | **−17.9%** | −20.5% to −15.2% |
| Visitors | +0.7% (p = 0.54) | −1.4% to +2.8% | −3.4% (p = 0.08) | −7.1% to +0.4% |

**Monthly view (ordinary days)**

| Month | Avg high | Rain days | Locals $/day | Visitors $/day | Floor $/day |
|---|---:|---:|---:|---:|---:|
| Jan | 13.6°C | 0 | 49.7K | 78.3K | 128.0K |
| Feb | 20.0°C | 1 | 47.8K | 73.6K | 121.4K |
| Mar | 21.0°C | 0 | 49.5K | 78.9K | 128.4K |
| Apr | 27.7°C | 0 | 50.3K | 81.5K | 131.9K |
| May | 32.3°C | 3 | 48.0K | 78.5K | 126.5K |
| Jun | 37.8°C | 0 | 48.7K | 74.2K | 122.9K |

## Robustness tests

**A. Rain placebo test.** Four rainy days is too few for a regression p-value to be trusted. Instead, I compared the observed rain effect with the same calculation on 4 days drawn at random, 10,000 times.

| Series | Observed rain effect | Placebo range (95%), 4 random days | Placebo range, 3 consecutive + 1 random day | Placebo p |
|---|---:|---|---|---:|
| Floor total | −9.0% | −3.6% to +2.9% | −3.9% to +3.2% | < 0.001 |
| Locals | −17.3% | −5.7% to +4.2% | −6.2% to +4.2% | < 0.001 |

The rain effect is far outside anything random days produce. That holds even for placebos that copy the real clustering (three rainy days in a row, May 4–6, plus one other day).

**B. Each rain episode on its own.** The rain effect shows up in both separate episodes. Each is only 1 or 3 days, so the regression CIs are not meaningful here.

| Episode | Floor total | Locals |
|---|---:|---:|
| Feb 13 alone | −12.9% | −20.5% |
| May 4–6 alone | −7.6% | −17.0% |

**C. Rain threshold.** Very light rain matters less. Every day with more than 1 mm of rain also had more than 5 mm.

| Threshold | Rain days | Floor total | Locals |
|---|---:|---:|---:|
| > 0 mm (any trace) | 7 | −5.0% (p = 0.01) | −12.1% |
| > 1 mm | 4 | −8.9% | −17.9% |
| > 5 mm | 4 | −8.9% | −17.9% |

**D. Heat, measured several ways.** Each regression also controls for rain.

| Heat measure | Days | Floor total | Locals | Visitors |
|---|---:|---:|---:|---:|
| High vs recent days, per +10°C (baseline) | 148 | 0.0% (p = 0.96) | −0.9% (p = 0.39) | +0.7% (p = 0.54) |
| Overnight low vs recent days, per +10°C | 148 | +0.3% (p = 0.74) | −0.6% (p = 0.63) | +1.0% (p = 0.44) |
| Yesterday's high vs recent days, per +10°C | 147 | −0.3% (p = 0.68) | −1.7% (p = 0.04) | +0.5% (p = 0.54) |
| May–Jun only, high vs recent days, per +10°C | 51 | −1.1% (p = 0.39) | −2.5% (p = 0.35) | −0.9% (p = 0.16) |
| **Extreme heat day, high ≥ 40°C** | 9 | **−3.5%** (−4.5% to −2.6%) | **−5.7%** | −1.7% (p = 0.05) |
| Top-decile high, ≥ 37.8°C | 16 | −1.7% (p = 0.004) | −3.0% | −0.6% (p = 0.37) |

- **Ordinary day-to-day heat has no effect, however it's measured.** That includes using only the hot season.
- **Extreme heat goes with lower play,** mostly among locals, and all 9 days at 40°C or above had below-expected play.
- **But all 9 fall between May 31 and June 30,** the weeks of the tourism slump. They may be picking up part of that slump, even after removing the 15-day level.
- **Even taken at face value, the effect is small.** About 9 such days a month × −3.5% ≈ **−1% for June**. The June shortfall in the forecasts was about 5%, so extreme heat accounts for at most about a fifth of it.

**E. What a perfect weather forecast would be worth.**
- I fitted the rain and temperature effects on Jan–Apr only and applied them to EL's May–Jun forecast using the *actual* weather. This is an upper bound: no real forecast knows the weather weeks ahead.
- Note that Jan–Apr has only one rainy day, which gives a −12.7% rain effect.

| | MAE | RMSE |
|---|---:|---:|
| EL | $4,290 | $5,503 |
| EL × perfect-weather adjustment | $4,069 (**−5.1%**) | $5,244 |

Almost all of the gain comes from May 4–6, where the error falls from $10,061 to $5,351 a day.

## What it shows

1. **Weather does not explain the June decline.** Ordinary heat has no effect. Extreme heat accounts for about 1 point of a ~5% shortfall, at most. The decline came from visitors (Domestic −11%, Regional −6%, International −7% vs Mar–Apr), in a month when Las Vegas visitation was 11% below 2024.
2. **Rain is a real, short-lived effect on locals.**
   - It shows up in both rain episodes, and it passes a placebo test that random days never come close to.
   - It explains the forecast's two worst ordinary days: May 5 at +13% and May 6 at +11%.
3. **Weather isn't a useful input for this forecast.**
   - Normal weather for a date is the same every year, so it carries no information beyond the calendar.
   - Actual weather isn't known weeks in advance. The data notes say "do not use future actual weather as a forecast feature."
   - The best case, a perfect forecast, is worth about 5% on MAE.
   - In a weekly-refresh forecast, a live 7-day weather forecast could catch rain and extreme heat. That can't be tested honestly here, because the data has actual weather only, not past forecasts.

## Limitations

- **Six months, one city, one year.** There are 4 rainy days and 9 days at 40°C or above.
- **Extreme heat is confounded with the June tourism slump.** A full summer of data, or a second year, would separate them.
- **The perfect-weather test is an upper bound.** Its rain effect comes from a single Jan–Apr rainy day.

## For the report

> We tested whether weather explained the June decline. Ordinary heat didn't matter: a day 10°C hotter than the days around it showed no change in play (0.0%, 95% CI −1.7% to +1.8%). Days of 40°C or more had about 3.5% less play. But they all fell in June's tourism slump, and even taken at face value they account for about 1 point of the ~5% June shortfall. Rain was the clearest weather effect: locals played about 18% less on rainy days, well beyond what any random set of days produced in a placebo test. That explains our two worst ordinary-day misses (May 5–6). Even a perfect weather forecast would have improved our May–Jun error by only about 5%, so weather belongs on the dashboard as an alert, not in the forecast.
