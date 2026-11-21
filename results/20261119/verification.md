# SeasonBlend dry run: initialisation 19 Nov 2026 (team UtabiriBora)

Automated run on Sat 21 Nov 2026 (02:00 to 06:00 UTC). Nothing submitted, uploaded, emailed, committed or pushed. The checkout was on `main`, clean, at d58a2b6 before and after the run.

## Verification summary

| Layer | Check | Result | Evidence |
|---|---|---|---|
| 0 | End-to-end test suite | PASS | `ALL 39 CHECKS PASSED`, exit 0 (dryrun_logs/e2e.log) |
| 0 | Remote status | PASS (late) | At 02:01Z dynamical.org's latest run was 2026-11-18. The 2026-11-19 run first appeared at 04:52Z (323 runs) |
| 1 | Weekly build `--no-submit` | PASS | Exit 0. Download took 129 s, plus 1 new ERA5 week per variable. Refit took 34.0 min (N=43/42). Six files written, ending with "Dry run only; nothing uploaded." |
| 1 | Cross-validated RPSS of the fit | info | tas +0.111/+0.092, mslp +0.194/+0.146, pr +0.082/+0.071 (p1/p2) |
| 2 | crosscheck.md | PASS | Dates (days 19-25 = 7-13 Dec, 26-32 = 14-20 Dec), all six files, sanity table: "Overall: all checks passed" |
| 2 | Cross-check reproducible | PASS | Second `run.py crosscheck` exit 0; report identical apart from the "Generated" timestamp |
| 2 | STATUS.txt | n/a | Not written for a dry run. Week 1's STATUS.txt only records the email submission |
| 3 | File names, 1 variable, dims 5x121x240, grid 90..-90 / 0..358.5 at 1.5 degrees | PASS (6/6) | independent_check.log |
| 3 | Finite, in [0,1], sum to 1 | PASS (6/6) | max abs(sum-1) = 4.4e-16 |
| 3 | Email file equals `<var>_pN.nc` | PASS (6/6) | max abs diff 0 |
| 3 | No probability > 0.95 | **FAIL (mslp p1)** | 787 points > 0.95, max 0.9937, about 4.2% of the globe, all in the tropical Pacific 21S-19.5N, 123E-280E (349 lowest-quintile in the east, 438 highest-quintile in the west). The other 5 files: max 0.90 or less. Week 1 (accepted) mslp p1 had 663 such points, max 0.9818, so this is not new |
| 4 | Structure vs week 1 (variable names, dims, coords, dtype float64, attributes) | PASS | Only description, expver, originating_centre (Utabra_01) and teamname changed, plus the dates |
| 4 | Overlap 7-13 Dec: tas | PASS | tilt corr 0.972, MAD 0.025 |
| 4 | Overlap 7-13 Dec: mslp | PASS | tilt corr 0.949, MAD 0.043 |
| 4 | Overlap 7-13 Dec: pr | PASS | tilt corr 0.903, MAD 0.031 |
| 5 | AI_WQ_package checks on the 6 written files | PASS | "written and passes the package checks" for each |
| 5 | Dry-run submission checks | PASS (6/6) | "array passes the package checks" for each window; "Inside the submission window" |
| 5 | check_registered_teamname | PASS | "UtabiriBora is registered... SeasonBlend is registered"; official list row `Utabra_01 UtabiriBora_01 UtabiriBora SeasonBlend`; config.toml teamname = "UtabiriBora" |
| Map | Physically sensible | PASS with warnings | See below |

## Map sanity

- El Niño fingerprint is clear and consistent: very warm tropics, strongest across the central and east Pacific and the Indian Ocean/Maritime Continent. MSLP is low over the east Pacific and high over the Indo-west Pacific (negative SOI). Precipitation is wet along the equatorial central-east Pacific, with a dry band just north of it and a drier Maritime Continent.
- Warning (artefact): straight edges at 30N and 30S in tas and mslp. The tilt jump between rows 31.5N/30N and 28.5S/30S is the largest on the map, about 2.5-3.5 times the median row-to-row jump. This matches the three-band calibration (a/c fitted per latitude band). The same edges are in week 1. It is cosmetic for the score only where the band edge falls on real gradients.
- pr: the Sahara/Arabia is blank (degenerate dry quintiles, as in week 1), and the field is speckled near the Andes and in the tropics (pr smooth=0). No stripes, missing regions or land-sea artefacts otherwise.

## Email files

Folder: `C:\Users\Stephen Nyaranga\Documents\AI-Weather-Quest\s2s-postprocessing-ecmwf\outputs\20261119\email`

| File | Bytes | SHA256 |
|---|---|---|
| tas_20261119_p1_UtabiriBora_SeasonBlend.nc | 1182123 | 124e3af7e295f97b93fafbbaa0269f04b59417b7d326dc6d48070b3f44fef74b |
| tas_20261119_p2_UtabiriBora_SeasonBlend.nc | 1182123 | 05e9987fc6a4b6a6eb2d2a7e474bae291dac5bcfb9a7360cb82e2a18ee610693 |
| mslp_20261119_p1_UtabiriBora_SeasonBlend.nc | 1182087 | 1dfd8113efbe838401ff41b875e689f2b98e4cc0b05d599394c7c19cfde7c0c0 |
| mslp_20261119_p2_UtabiriBora_SeasonBlend.nc | 1182087 | b0b4ccaae2adf18a5a27e461d4d23e43ef2453bba201e98be653c2d5e970b51d |
| pr_20261119_p1_UtabiriBora_SeasonBlend.nc | 1182081 | 7e20d1d39d57b58d7063485f2ba0959b823267431fc2eb815b64c1e37b5b4d22 |
| pr_20261119_p2_UtabiriBora_SeasonBlend.nc | 1182081 | e5945b3fd532e4d3225a6b84745a4a42b604838df89209f8b5a65e4422bb9750 |

Hashes were confirmed by two independent tools (Python hashlib and `sha256sum`).

Not submitted. Awaiting your approval to submit SeasonBlend (team UtabiriBora) for 19 Nov 2026 (deadline Sun 22 Nov 23:59 UTC).
