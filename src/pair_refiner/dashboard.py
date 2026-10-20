"""Seam 7: the dashboard's server (BUILD.md, "Dashboard"). Pages made on the server, served on 127.0.0.1 only.

Start it with: uv run pair-refiner"""

import csv
import json
import threading
import time
import tomllib
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request

from pair_refiner import cache as cache_module
from pair_refiner import estimate
from pair_refiner.cache import CachedConnection
from pair_refiner.connection import GOOGLE_TRANSLATE, Connection, Model
from pair_refiner.dataset import read_dataset, read_settings
from pair_refiner.run import RunSettings, run

PORT = 8765


def create_app(root: Path, connection: Connection, cache: Path) -> Flask:
    """The dashboard for the repo folder `root` (datasets\\, runs\\, defaults.toml), calling models through
    `connection` with the shared answer cache at `cache`."""
    app = Flask(__name__)
    runs_dir = root / "runs"
    balance = _Balance(connection)
    prices = _Prices(connection)
    jobs: dict[str, threading.Thread] = {}  # runs started by this dashboard

    @app.context_processor
    def money():
        """Shown on every page: the OpenRouter balance and Google's spend this month, as counted by the tool."""
        return {"money": {"balance": balance.get(), "google": cache_module.month_spend(cache, GOOGLE_TRANSLATE)}}

    @app.get("/")
    def front():
        return redirect("/runs")

    @app.get("/runs")
    def runs():
        return render_template("runs.html", runs=_past_runs(runs_dir))

    @app.get("/new")
    def new():
        return _new_page(request.args.get("dataset"))

    @app.post("/new")
    def new_action():
        form = request.form
        path, dataset = read_settings(root / "datasets" / f"{form['dataset']}.toml")
        settings = _settings_from(form)
        rows = read_dataset(path, dataset)
        if form.get("action") == "estimate":
            estimator = estimate.from_cache(list(prices.get().values()), cache)
            report = run(rows, dataset, settings, None, runs_dir / form["name"], estimator, dry_run=True)
            return _new_page(form["dataset"], form, report.estimate, estimator.measured)
        estimator = estimate.from_cache(list(prices.get().values()), cache)
        folder = runs_dir / form["name"]
        job = threading.Thread(target=run, daemon=True, name=form["name"],
                               args=(rows, dataset, settings, CachedConnection(connection, cache), folder, estimator))
        jobs[form["name"]] = job
        job.start()
        return redirect(f"/runs/{form['name']}", code=303)

    @app.get("/runs/<name>")
    def one_run(name: str):
        folder = runs_dir / name
        if not (folder / "run.json").exists():
            if name in jobs and jobs[name].is_alive():  # just started: its files are on their way
                return render_template("run.html", name=name, record=None, refresh=True)
            abort(404)
        record = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        running = record["status"] == "running"
        if running and not (name in jobs and jobs[name].is_alive()):
            record["status"] = "stopped before it finished (start it again with the same name to resume)"
            running = False
        return render_template("run.html", name=name, record=record, refresh=running,
                               flags=_csv(folder / "flags.csv"), sentences=_winners(folder / "candidates.csv"))

    @app.get("/runs/<name>/sentences/<int:n>")
    def sentence(name: str, n: int):
        folder = runs_dir / name
        sentences = _sentences(folder / "candidates.csv")
        if not 0 <= n < len(sentences):
            abort(404)
        rows = sentences[n]
        winner = next(r for r in rows if r["winner"] == "yes")
        judges = [column[: -len(" meaning")] for column in rows[0] if column.endswith(" meaning")
                  and column != "panel meaning"]
        flags = [f["flag"] for f in _csv(folder / "flags.csv")
                 if (f["id"], f["register"]) == (winner["id"], winner["register"])]
        return render_template("sentence.html", name=name, n=n, count=len(sentences), rows=rows, winner=winner,
                               judges=judges, flags=flags)

    def _new_page(chosen: str | None, form=None, estimate_usd: float | None = None, measured: bool = False):
        names = sorted(p.stem for p in (root / "datasets").glob("*.toml"))
        chosen = chosen if chosen in names else (names[0] if names else None)
        defaults = _defaults(root)
        direction, register, picked = None, "written", {}
        if chosen:
            _, dataset = read_settings(root / "datasets" / f"{chosen}.toml")
            direction, register = f"{dataset.source_lang}-{dataset.target_lang}", dataset.register
            picked = defaults.get("directions", {}).get(direction, {})
        if form:  # an estimate: show the form as it was sent
            picked = {"translators": form.getlist("translators"), "judges": form.getlist("judges"),
                      "top_judge": form["top_judge"], "back_translation": "back_translation" in form,
                      "chrf_threshold": float(form["chrf_threshold"]), "shortlist_size": int(form["shortlist_size"])}
            register = form["register"]
        offered = list(dict.fromkeys(m for section in [*defaults.get("directions", {}).values(),
                                                       defaults.get("panel", {})]
                                     for kind in ("translators", "judges") for m in section.get(kind, [])))
        return render_template(
            "new.html", datasets=names, chosen=chosen, direction=direction, register=register, picked=picked,
            offered=offered, google=GOOGLE_TRANSLATE, form=form or {}, estimate=estimate_usd, measured=measured,
            name=form["name"] if form else f"{chosen}-{datetime.now():%Y%m%d-%H%M}")

    @app.get("/models")
    def models():
        defaults = _defaults(root)
        scores_file = runs_dir / "test-run" / "scores.json"
        scores = json.loads(scores_file.read_text(encoding="utf-8")) if scores_file.exists() else {}
        return render_template("models.html", directions=defaults.get("directions", {}),
                               panel=defaults.get("panel"), prices=prices.get(), scores=scores,
                               google=GOOGLE_TRANSLATE)

    return app


class _Balance:
    """The OpenRouter balance, asked for at most once a minute; None when it can't be read (no management key)."""

    def __init__(self, connection: Connection):
        self.connection, self.value, self.at = connection, None, -1e9

    def get(self) -> float | None:
        if time.monotonic() - self.at > 60:
            try:
                self.value = self.connection.balance()
            except Exception:  # no management key, or the service is down: the page still works
                self.value = None
            self.at = time.monotonic()
        return self.value


class _Prices:
    """OpenRouter's models by id, read at most every ten minutes (the list is free but slow)."""

    def __init__(self, connection: Connection):
        self.connection, self.value, self.at = connection, {}, -1e9

    def get(self) -> dict[str, Model]:
        if time.monotonic() - self.at > 600:
            try:
                self.value = {m.id: m for m in self.connection.list_models()}
            except Exception:  # offline: the pages still work, without prices
                pass
            self.at = time.monotonic()
        return self.value


def main() -> None:
    """`uv run pair-refiner`: start the dashboard on this computer only (127.0.0.1) and open it in the browser."""
    import webbrowser

    from pair_refiner.live import LiveConnection, load_keys

    root = Path(__file__).parents[2]
    app = create_app(root, LiveConnection(load_keys(root / "keys.toml")), root / "cache" / "answers.sqlite")
    url = f"http://127.0.0.1:{PORT}/"
    print(f"pair-refiner dashboard: {url}  (only reachable from this computer; close this window to stop it)")
    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)


def _settings_from(form) -> RunSettings:
    """The run settings sent by the New run form."""
    def number(name: str, kind=float):
        return kind(form[name]) if form.get(name, "").strip() else None
    return RunSettings(
        translators=form.getlist("translators"), judges=form.getlist("judges"), top_judge=form["top_judge"],
        shortlist_size=number("shortlist_size", int) or 3, back_translation="back_translation" in form,
        chrf_threshold=number("chrf_threshold") or 40.0, register=form["register"],
        sentence_limit=number("sentence_limit", int), spending_limit=number("spending_limit"))


def _csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _sentences(candidates_csv: Path) -> list[list[dict]]:
    """candidates.csv's rows grouped by sentence (id and register), in the run's order."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in _csv(candidates_csv):
        grouped.setdefault((row["id"], row["register"]), []).append(row)
    return list(grouped.values())


def _winners(candidates_csv: Path) -> list[dict]:
    """One row per sentence (its winner's row), numbered for the sentence pages."""
    return [{**next(r for r in rows if r["winner"] == "yes"), "n": n}
            for n, rows in enumerate(_sentences(candidates_csv))]


def _defaults(root: Path) -> dict:
    with open(root / "defaults.toml", "rb") as f:
        return tomllib.load(f)


def _past_runs(runs_dir: Path) -> list[dict]:
    """Every run folder with a run.json, newest first."""
    found = []
    for record_file in runs_dir.glob("*/run.json"):
        record = json.loads(record_file.read_text(encoding="utf-8"))
        found.append({"name": record_file.parent.name, **record})
    return sorted(found, key=lambda r: r.get("started", ""), reverse=True)
