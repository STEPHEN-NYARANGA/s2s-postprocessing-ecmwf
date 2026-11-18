"""Command line interface:  python run.py <command> [options]"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

from .config import PASSWORD_ENV, VARIABLES, load_config, read_password
from .dates import latest_thursday, parse_date, submission_deadline, thursdays, utc_today


def _log(msg: str):
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}Z] {msg}", flush=True)


def _init_arg(args) -> dt.date:
    d = parse_date(args.init) if args.init else latest_thursday()
    if d.weekday() != 3:
        raise SystemExit(f"{d} is not a Thursday; initialisation dates must be Thursdays.")
    return d


def cmd_status(cfg, args):
    from .ens import cached_inits
    from .obs import available_weeks

    today = utc_today()
    init = latest_thursday(today)
    _log(f"Team {cfg.teamname}, model {cfg.modelname}")
    _log(f"Today (UTC) {today}; current initialisation {init}; submission closes "
         f"{submission_deadline(init):%a %d %b %H:%M} UTC")
    _log(f"Password variable {PASSWORD_ENV}: {'set' if read_password() else 'NOT set'}")
    inits = cached_inits(cfg)
    _log(f"ENS cache: {len(inits)} runs" + (f" ({inits[0]} to {inits[-1]})" if inits else ""))
    for v in VARIABLES:
        w = available_weeks(cfg, v)
        _log(f"ERA5 weeks cached for {v}: {len(w)}" + (f" ({w[0]} to {w[-1]})" if w else ""))
    _log(f"Fitted parameters: {'yes' if cfg.params_path.exists() else 'no'}")
    if args.remote:
        from .ens import open_remote, remote_inits

        from .ens import ENS_NAMES

        ds = open_remote(cfg)
        av = remote_inits(ds)
        _log(f"dynamical.org: {len(av)} runs, latest {max(av) if av else None}; "
             f"current Thursday run {'AVAILABLE' if init in av else 'not yet available'}")
        _log(f"Dimensions: {dict(ds.sizes)}")
        for v, name in ENS_NAMES.items():
            if name in ds:
                _log(f"  {v}: {name} {ds[name].dims} units={ds[name].attrs.get('units')}")
            else:
                _log(f"  {v}: {name} MISSING from the dataset (update ENS_NAMES in aiwq/ens.py)")


def cmd_fetch_ens(cfg, args):
    from .ens import fetch

    end = _init_arg(args)
    if args.only:
        inits = [end]
    else:
        start = parse_date(args.start) if args.start else parse_date(cfg.first_init)
        inits = thursdays(start, end)[:: max(1, args.stride)]
        if end not in inits:
            inits.append(end)
    res = fetch(cfg, inits, log=_log)
    if res["unavailable"]:
        _log(f"Not yet available: {', '.join(str(d) for d in res['unavailable'])}")
    return res


def cmd_fetch_obs(cfg, args):
    from .obs import backfill

    start = parse_date(args.start) if args.start else None
    stats = backfill(cfg, start=start, log=_log)
    _log(f"Done: {stats}")


def cmd_fit(cfg, args):
    from .fit import fit_all

    t0 = time.time()
    fit_all(cfg, log=_log)
    _log(f"Fit finished in {(time.time() - t0) / 60:.1f} min. Report: {cfg.output_dir / 'backtest' / 'backtest_report.md'}")


def cmd_forecast(cfg, args):
    from .fit import load_params
    from .forecast import make_forecast

    init = _init_arg(args)
    make_forecast(cfg, init, load_params(cfg), log=_log)
    _log(f"Forecast files in {cfg.output_dir / init.strftime('%Y%m%d')}")


def cmd_submit(cfg, args):
    from .submit import dry_run, submit

    if not args.dry_run:
        _operational_only(cfg, "submit")
    init = _init_arg(args)
    ok = dry_run(cfg, init, log=_log)
    if args.dry_run:
        _log("Dry run only; nothing uploaded." + ("" if ok else " Fix the problems above before submitting."))
        return
    if not ok and not args.force:
        raise SystemExit("Checks failed; nothing submitted. Use --force only if you understand the failure.")
    res = submit(cfg, init, log=_log)
    n_ok = sum(v == "submitted" for v in res.values())
    _log(f"Submitted {n_ok}/{len(res)} files for {init}.")


def cmd_export(cfg, args):
    from .submit import export_for_email

    _operational_only(cfg, "export")
    init = _init_arg(args)
    paths = export_for_email(cfg, init, log=_log)
    _log(f"{len(paths)} files for an email submission in {paths[0].parent}")


def cmd_crosscheck(cfg, args):
    from .crosscheck import crosscheck

    ok, text = crosscheck(cfg, _init_arg(args), log=_log)
    print(text)
    if not ok:
        raise SystemExit(1)


def cmd_results(cfg, args):
    from .results import publish

    _operational_only(cfg, "results")
    publish(cfg, _init_arg(args), log=_log)


def cmd_indices(cfg, args):
    from .ens import cached_inits
    from .indices import Indices, fetch, write_table

    fetch(cfg, log=_log)
    inits = cached_inits(cfg)
    init = _init_arg(args)
    if init not in inits:
        inits = sorted(set(inits) | {init})
    path = write_table(cfg, inits)
    s = Indices(cfg).state_at(init)
    _log(f"State at {init}: MJO phase {s.mjo_phase}, amplitude {s.mjo_amp} (RMM of {s.rmm_date}); "
         f"Nino 3.4 {s.nino34} K, {s.enso} (week of {s.nino34_date}); IOD {s.iod} K (week ending {s.iod_date})")
    _log(f"Index values known at each of {len(inits)} initialisations: {path}")


def cmd_compare(cfg, args):
    from .stats import compare, write_comparison

    names = args.models
    res = compare(cfg, names, reference=args.reference, key="rps_final" if args.in_sample else "rps_final_cv",
                  n_boot=args.samples, block=args.block)
    out = cfg.results_dir / "experiments" / ("comparison_" + "_vs_".join(names) + ".md")
    write_comparison(cfg, res, out)
    print(out.read_text(encoding="utf-8"))
    _log(f"Written to {out}")


def _operational_only(cfg, what: str):
    if not cfg.can_submit:
        raise SystemExit(f"'{what}' is not available for experiment '{cfg.experiment}': it would use the "
                         f"operational model name {cfg.modelname}. Give the experiment its own registered "
                         f"modelname in config.toml first.")


def cmd_weekly(cfg, args):
    _operational_only(cfg, "weekly")
    init = _init_arg(args)
    deadline = submission_deadline(init)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    _log(f"Weekly run for initialisation {init}; deadline {deadline:%a %d %b %H:%M} UTC")
    if now > deadline and not args.no_submit:
        raise SystemExit("The submission window for this initialisation has closed.")
    cfg.password  # fail early if the password is missing

    # 1. ECMWF ensemble (archive + this week's run)
    t_end = time.time() + 3600 * args.wait_hours
    from .ens import fetch

    recent = [init - dt.timedelta(days=7 * k) for k in range(8)]  # this week + newly verifiable runs
    while True:
        res = fetch(cfg, sorted(recent), log=_log)
        if init not in res["unavailable"]:
            break
        if time.time() > t_end:
            raise SystemExit(f"The ECMWF run for {init} is not on dynamical.org yet (usually ~48 h after "
                             f"00 UTC, i.e. Saturday). Run again later, or use --wait-hours 12.")
        _log("Waiting 30 minutes for the run to appear ...")
        time.sleep(1800)
    # 2. observations, and climate indices for the research models (never stops the run)
    cmd_fetch_obs(cfg, argparse.Namespace(start=None))
    try:
        cmd_indices(cfg, argparse.Namespace(init=init.isoformat()))
    except Exception as e:  # noqa: BLE001
        _log(f"(climate indices skipped: {e})")
    # 3. refit
    if not args.skip_fit or not cfg.params_path.exists():
        cmd_fit(cfg, args)
    # 4. forecast, the six files as they would be emailed, and independent checks
    ns = argparse.Namespace(init=init.isoformat())
    cmd_forecast(cfg, ns)
    cmd_export(cfg, ns)
    from .crosscheck import crosscheck

    ok, _ = crosscheck(cfg, init, log=_log)
    if not ok and not args.no_submit:
        raise SystemExit(f"Cross-check failed; nothing submitted. Read {cfg.output_dir / init.strftime('%Y%m%d')}"
                         f"/crosscheck.md, then use 'submit' yourself if the forecast is fine.")
    # 5. submit
    cmd_submit(cfg, argparse.Namespace(init=init.isoformat(), dry_run=args.no_submit, force=False))
    # 6. copy the week's results into results/ (tracked in Git)
    if not args.no_submit:
        cmd_results(cfg, ns)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="run.py", description="SeasonBlend pipeline for the ECMWF AI Weather Quest")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--experiment", "-x", metavar="NAME",
                    help="run as the experiment [experiments.NAME] in config.toml, with its own files "
                         "(fit and forecast only; SeasonBlend's files are not touched)")
    ap.add_argument("--obs-source", choices=["ecbox", "cds"],
                    help="override [obs] source: official ECBox files or ERA5 from Copernicus (aiwq/cds.py)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="show what is cached and what is due")
    s.add_argument("--remote", action="store_true", help="also query dynamical.org for the latest run")

    s = sub.add_parser("fetch-ens", help="download ECMWF ensemble runs (Thursdays) from dynamical.org")
    s.add_argument("--init", help="last Thursday to fetch (default: latest Thursday)")
    s.add_argument("--start", help="first Thursday (default: [ens] first_init)")
    s.add_argument("--stride", type=int, default=1, help="take every n-th Thursday for the archive")
    s.add_argument("--only", action="store_true", help="fetch only --init")

    s = sub.add_parser("fetch-obs", help="download ERA5 weekly obs and quintile boundaries (needs password)")
    s.add_argument("--start", help="first Monday (default: [obs] first_monday)")

    sub.add_parser("fit", help="leave-one-out fit and backtest report")

    s = sub.add_parser("forecast", help="make the quintile probabilities for one initialisation")
    s.add_argument("--init")

    s = sub.add_parser("submit", help="check and upload the saved forecast")
    s.add_argument("--init")
    s.add_argument("--dry-run", action="store_true", help="run the official checks without uploading")
    s.add_argument("--force", action="store_true")

    s = sub.add_parser("export", help="write the six files for an email submission (when ECBox upload fails)")
    s.add_argument("--init")

    s = sub.add_parser("crosscheck", help="independent sanity checks of the email files, as a Markdown report")
    s.add_argument("--init")

    s = sub.add_parser("results", help="copy this week's files, maps and checks into results/ (tracked in Git)")
    s.add_argument("--init")

    s = sub.add_parser("indices", help="download MJO, Nino 3.4 and IOD indices; values known at each initialisation")
    s.add_argument("--init")

    s = sub.add_parser("compare", help="compare fitted models with a paired block bootstrap")
    s.add_argument("models", nargs="+", help="'operational' and/or experiment names; the first is the reference")
    s.add_argument("--reference", help="reference model (default: the first)")
    s.add_argument("--samples", type=int, help="bootstrap samples (default [stats] bootstrap_samples)")
    s.add_argument("--block", type=int, help="block length in weeks (default [stats] bootstrap_block_weeks)")
    s.add_argument("--in-sample", action="store_true", help="use the in-sample scores instead of cross-validated")

    s = sub.add_parser("weekly", help="fetch, fit, forecast and submit for the current Thursday")
    s.add_argument("--init")
    s.add_argument("--no-submit", action="store_true", help="stop after the dry-run checks")
    s.add_argument("--skip-fit", action="store_true", help="reuse last week's fitted parameters")
    s.add_argument("--wait-hours", type=float, default=0.0, help="keep polling for the run for this many hours")

    args = ap.parse_args(argv)
    cfg = load_config(args.config, experiment=args.experiment)
    if args.obs_source:
        cfg.obs_source = args.obs_source
        cfg.obs_dir.mkdir(parents=True, exist_ok=True)
    handler = {"status": cmd_status, "fetch-ens": cmd_fetch_ens, "fetch-obs": cmd_fetch_obs, "fit": cmd_fit,
               "forecast": cmd_forecast, "submit": cmd_submit, "export": cmd_export, "crosscheck": cmd_crosscheck, "results": cmd_results, "indices": cmd_indices, "compare": cmd_compare,
               "weekly": cmd_weekly}[args.cmd]
    try:
        handler(cfg, args)
    except KeyboardInterrupt:
        _log("Interrupted; everything downloaded so far is kept in the cache.")
        sys.exit(130)
