#!/usr/bin/env python3
"""Entry point. Examples:
    python run.py status --remote
    python run.py fetch-ens            # archive of Thursday runs since [ens] first_init
    python run.py fetch-obs            # ERA5 weeks + quintile boundaries (needs AIWQ_PASSWORD)
    python run.py fit                  # leave-one-out fit + backtest report
    python run.py weekly               # every Saturday/Sunday: fetch, fit, forecast, submit
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiwq.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
