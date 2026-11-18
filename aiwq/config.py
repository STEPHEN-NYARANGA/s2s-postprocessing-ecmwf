"""Configuration: read config.toml and the submission password from the environment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PASSWORD_ENV = "AIWQ_PASSWORD"
VARIABLES = ("tas", "mslp", "pr")
WINDOWS = (1, 2)


def read_password() -> str:
    """The submission password from the environment. On Windows, a user variable saved with
    [Environment]::SetEnvironmentVariable(..., "User") is also read from the registry, so
    programs started before it was set (an open terminal, an app) still find it."""
    pw = os.environ.get(PASSWORD_ENV, "")
    if not pw.strip() and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                pw = str(winreg.QueryValueEx(key, PASSWORD_ENV)[0])
        except OSError:
            pw = ""
    return pw.strip()


@dataclass
class Config:
    teamname: str
    modelname: str
    data_dir: Path
    output_dir: Path
    results_dir: Path = Path("results")  # copies kept in Git (aiwq/results.py)
    # ensemble source
    dataset_id: str = "ecmwf-ifs-ens-forecast-46-day-daily-1-5-degree"
    first_init: str = "2026-01-01"
    # observations
    obs_first_monday: str = "2024-01-15"
    obs_latency_days: int = 6
    obs_source: str = "ecbox"  # "ecbox" (official files) or "cds" (ERA5 from Copernicus, see aiwq/cds.py)
    # method
    season_sigma_days: float = 45.0
    season_floor: float = 0.15
    exclude_days: int = 21
    bias_smooth_sigma: float = 1.0
    prior_smooth_sigma: float = 1.5
    lambdas: list = field(default_factory=lambda: [0.0, 0.5, 0.75, 1.0])
    spreads: list = field(default_factory=lambda: [1.0, 1.25, 1.5, 1.75, 2.0])
    prob_smooth_sigmas: list = field(default_factory=lambda: [0.0, 1.0, 2.0])
    blend_bands: list = field(default_factory=lambda: [[90.0, 30.0], [30.0, -30.0], [-30.0, -90.0]])
    min_train: int = 8

    @property
    def password(self) -> str:
        pw = read_password()
        if not pw:
            raise SystemExit(
                f"The AI Weather Quest password is not set. Set the environment variable "
                f"{PASSWORD_ENV} (see README, step 3) and run again."
            )
        return pw

    @property
    def ens_dir(self) -> Path:
        return self.data_dir / "ens"

    @property
    def obs_dir(self) -> Path:
        # Copernicus stand-in files live apart so they never shadow the official ECBox files
        return self.data_dir / ("obs_cds" if self.obs_source == "cds" else "obs")

    @property
    def params_path(self) -> Path:
        return self.data_dir / ("params_cds.json" if self.obs_source == "cds" else "params.json")


def load_config(path: str | os.PathLike = "config.toml") -> Config:
    path = Path(path).resolve()
    if not path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    base = path.parent
    team = raw.get("team", {})
    paths = raw.get("paths", {})
    kwargs = dict(
        teamname=str(team.get("teamname", "")).strip(),
        modelname=str(team.get("modelname", "")).strip(),
        data_dir=(base / paths.get("data_dir", "data")).resolve(),
        output_dir=(base / paths.get("output_dir", "outputs")).resolve(),
        results_dir=(base / paths.get("results_dir", "results")).resolve(),
    )
    for section in ("ens", "obs", "method"):
        for k, v in raw.get(section, {}).items():
            key = {"first_monday": "obs_first_monday", "latency_days": "obs_latency_days",
                   "source": "obs_source"}.get(k, k)
            if key not in Config.__dataclass_fields__:
                raise SystemExit(f"Unknown setting [{section}] {k} in {path.name}")
            kwargs[key] = v
    cfg = Config(**kwargs)
    for name in ("teamname", "modelname"):
        val = getattr(cfg, name)
        if not val or not val.isalnum():
            raise SystemExit(f"{name} in config.toml must be letters and digits only (got {val!r}).")
    for d in (cfg.data_dir, cfg.output_dir, cfg.ens_dir, cfg.obs_dir):
        d.mkdir(parents=True, exist_ok=True)
    # make sure the "no calibration" settings are always part of the search grid
    if 0.0 not in cfg.lambdas:
        cfg.lambdas = [0.0] + list(cfg.lambdas)
    if 1.0 not in cfg.lambdas:
        cfg.lambdas = list(cfg.lambdas) + [1.0]
    if 1.0 not in cfg.spreads:
        cfg.spreads = [1.0] + list(cfg.spreads)
    if 0.0 not in cfg.prob_smooth_sigmas:
        cfg.prob_smooth_sigmas = [0.0] + list(cfg.prob_smooth_sigmas)
    return cfg
