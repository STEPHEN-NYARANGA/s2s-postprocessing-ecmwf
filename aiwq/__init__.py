"""SeasonBlend: calibrated ECMWF extended-range ensemble for the ECMWF AI Weather Quest.

Pipeline
--------
1. ens.py      Download ECMWF IFS ENS 46-day forecasts (dynamical.org, 1.5 deg, 101 members)
               and reduce them to weekly aggregates for days 19-25 and 26-32.
2. obs.py      Download ERA5 weekly observations, 20-year quintile boundaries and the
               land-sea mask through the official AI-WQ-package.
3. calib.py    Core maths: quintile counting with the official tie rules, seasonal bias
               correction, spread scaling, observed-frequency prior and RPS bookkeeping.
4. fit.py      Leave-one-out fit of the calibration settings and blend weights, with a
               backtest report (raw ensemble versus calibrated forecast).
5. forecast.py Build the quintile probabilities for one Thursday initialisation.
6. submit.py   Hand the probabilities to the AI-WQ-package submission functions.
"""

__version__ = "1.0.0"
