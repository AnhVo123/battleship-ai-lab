"""Loopback-only local analysis API. Strategy execution uses the Phase 2 worker."""
import base64
import binascii
from copy import deepcopy
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid
import secrets
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt

from .benchmark import benchmark
from .opponents import Opponent, opponent_loadout
from .simulation import Battle, RoundConfig
from .strategies import StrategyProcess, import_strategy
from .diagnostics import EvidenceRecorder, diagnose, replay_frame, compare_pools, export_report, improvement_prompt
from .validation import TEMPLATE, validate_source


class Upload(BaseModel):
    filename: str = "strategy.py"
    source: str = Field(default="", max_length=262144)
    source_base64: str | None = Field(default=None, max_length=349528)
    label: str = Field(default="", max_length=100)


class Label(BaseModel):
    label: str = Field(min_length=1, max_length=100)


class ArmoryOptions(BaseModel):
    round: str = "round1"
    loadout: dict[str, StrictInt] = Field(default_factory=dict)
    carryover_from: str | None = None
    advanced: bool = False


class BattleOptions(ArmoryOptions):
    version: str
    seed: int | None = None
    teams: int = Field(default=2, ge=2, le=20)
    difficulty: str = "medium"


class StepOptions(BaseModel):
    expected_tick: StrictInt = Field(ge=0)


class BenchmarkOptions(BaseModel):
    versions: list[str] = Field(min_length=1, max_length=4)
    matches: int = Field(default=100, ge=1, le=1000)
    teams: int = Field(default=2, ge=2, le=20)
    round: str = "round1"
    difficulty: str = "medium"
    pool: str = "development"
    master_seed: int = 42
    loadout: dict[str, StrictInt] = Field(default_factory=dict)


class ExperimentComparison(BaseModel):
    development: str
    validation: str


@dataclass
class Session:
    battle: Battle
    strategy: StrategyProcess
    opponents: dict
    version: str
    frames: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    recorder: EvidenceRecorder | None = None
    team_names: dict = field(default_factory=dict)
    result_id: str | None = None
    team_strategies: dict = field(default_factory=dict)

    def snapshot(self, traces=None):
        b = self.battle
        frame = {"tick": b.tick, "finished": b.finished, "abandoned": b.abandoned,
                 "engine_kind": b.engine_kind, "wind": list(b.wind), "traces": traces or [],
                 "events": b.events,
                 "teams": [{"seat": label, "name":self.team_names.get(label,"Your strategy" if label == "A" else f"Opponent {label}"),"score": seat.score, "wasted": seat.wasted,
                            "strategy": self.team_strategies.get(label),
                            "boosters": {"purchased": b.purchases[label], "remaining": dict(seat.boosters),
                                         "stats": b.booster_stats[label], "expired": b.finished,
                                         "remaining_points": b.remaining_points[label]},
                            "eliminated": seat.eliminated, "connected": seat.connected,
                            "ships": [{"name": s.name, "cells": [list(c) for c in s.cells], "holes": [list(c) for c in sorted(s.holes)], "sunk": s.sunk} for s in seat.ships],
                            "shots": seat.last_results} for label, seat in b.seats.items()],
                 "strategy_status": self.strategy.last_status,
                 "runtime_error": self.strategy.events[-1].get("detail", "") if isinstance(getattr(self.strategy,"events",None),list) and self.strategy.events else "",
                 "armory": {"round":b.config.name,"remaining_points":b.remaining_points["A"],
                            "inventory":dict(b.seats["A"].boosters),"expired":b.finished},
                 "ranking": [{**row,"name":self.team_names.get(row["seat"],"Your strategy" if row["seat"] == "A" else f'Opponent {row["seat"]}'),
                              "ships_remaining":sum(not ship.sunk for ship in b.seats[row["seat"]].ships)}
                             for row in b.results()["ranking"]] if b.finished else []}
        # Freeze replay data before any later mutation of ships or shots.
        frame = deepcopy(frame)
        self.frames.append(frame)
        return frame

    def step(self, expected_tick=None):
        with self.lock:
            if expected_tick is not None:
                if expected_tick < self.battle.tick:
                    return self.frames[min(expected_tick + 1, len(self.frames)-1)]
                if expected_tick > self.battle.tick:
                    raise HTTPException(409, "Battle tick is ahead of the live state")
            if self.battle.finished:
                return self.frames[-1]
            if self.recorder is None:
                self.recorder = EvidenceRecorder(self.battle)
            actions = {}
            for label, seat in self.battle.seats.items():
                if not seat.connected or seat.eliminated:
                    continue
                bot = self.strategy if label == "A" else self.opponents[label]
                action = bot.on_state(self.battle.state(label))
                actions[label] = action
            detail = ""
            if isinstance(getattr(self.strategy, "events", None), list) and self.strategy.events:
                detail = self.strategy.events[-1].get("detail", "")
            self.recorder.begin(self.battle, actions.get("A"), self.strategy.last_status, detail)
            self.battle.step(actions)
            self.recorder.finish(self.battle)
            traces = self.battle.traces()
            frame = self.snapshot(traces)
            if self.battle.finished:
                self.strategy.close()
            return frame


def create_app(data_dir=None):
    root = Path(data_dir or os.environ.get("BATTLESHIP_DATA", "local_data")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    versions = root / "versions"
    versions.mkdir(exist_ok=True)
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    experiments = root / "experiments"
    experiments.mkdir(exist_ok=True)
    metadata_file = root / "labels.json"
    metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {}
    sessions, jobs = {}, {}
    guard = threading.RLock()

    def save_experiment(kind, payload, title, identifier=None):
        identifier = identifier or uuid.uuid4().hex
        value = {"id":identifier,"kind":kind,"title":title,"created_at":datetime.now(timezone.utc).isoformat(), **payload}
        temp = experiments/f"{identifier}.tmp"
        temp.write_text(json.dumps(value), encoding="utf-8")
        temp.replace(experiments/f"{identifier}.json")
        return value

    def get_experiment(identifier):
        if not re.fullmatch(r"[a-f0-9]{32}",identifier) or not (experiments/f"{identifier}.json").is_file():
            raise HTTPException(404,"Unknown experiment")
        return json.loads((experiments/f"{identifier}.json").read_text(encoding="utf-8"))

    @asynccontextmanager
    async def lifespan(app):
        yield
        for session in sessions.values():
            with session.lock:
                session.strategy.close()

    app = FastAPI(title="Battleship Strategy Lab — Local", lifespan=lifespan)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Reject cross-site browser calls to a service that executes local Python.
        host = request.headers.get("host", "").split(":")[0]
        origin = request.headers.get("origin")
        allowed = {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}
        if host not in ("127.0.0.1", "localhost", "testserver") or (origin and origin not in allowed):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Local requests only"}, status_code=403)
        return await call_next(request)

    def version_path(identifier):
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise HTTPException(404, "Unknown version")
        path = versions / identifier
        if not (path / "strategy.py").is_file():
            raise HTTPException(404, "Unknown version")
        return path

    def save_labels():
        temp = metadata_file.with_suffix(".tmp")
        temp.write_text(json.dumps(metadata), encoding="utf-8")
        temp.replace(metadata_file)

    def validate_options(round_name, difficulty, pool=None, loadout=None):
        from .opponents import LEVELS
        from .simulation import BOOSTERS
        try:
            rounds = ("round1", "round2", "final") if round_name == "all" else (round_name,)
            for name in rounds:
                config = RoundConfig.preset(name)
                budget = config.points
                for booster, count in (loadout or {}).items():
                    if booster not in config.unlocked or count < 0:
                        raise ValueError("Booster unavailable in selected round")
                    budget -= BOOSTERS[booster]*count
                if budget < 0:
                    raise ValueError("Booster budget exceeded")
            if difficulty not in LEVELS or pool not in (None, "development", "holdout"):
                raise ValueError("Invalid difficulty or seed pool")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def quote_armory(body):
        from .simulation import BOOSTERS
        try:
            config = RoundConfig.preset(body.round)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        carryover = 0
        if body.advanced:
            if body.round != "final" or not body.carryover_from:
                raise HTTPException(422,"Carryover requires a completed Round 2 and declared advancement to Final")
            previous = sessions.get(body.carryover_from)
            if previous:
                if previous.battle.config.name != "round2" or not previous.battle.finished or previous.battle.abandoned:
                    raise HTTPException(422,"Carryover source must be a completed, non-abandoned Round 2")
                carryover = previous.battle.remaining_points["A"]
            else:
                saved = get_experiment(body.carryover_from)
                frame = saved.get("frames", [{}])[-1] if saved.get("frames") else {}
                if saved["kind"] != "battle" or not frame.get("finished") or frame.get("abandoned") or frame.get("armory",{}).get("round") != "round2":
                    raise HTTPException(422,"Carryover source must be a completed, non-abandoned Round 2")
                carryover = frame["armory"]["remaining_points"]
        spent = 0
        for name, quantity in body.loadout.items():
            if name not in config.unlocked or type(quantity) is not int or quantity < 0:
                raise HTTPException(422,"Invalid booster purchase for this round")
            spent += BOOSTERS[name]*quantity
        budget = config.points+carryover
        if spent > budget:
            raise HTTPException(422,"Booster budget exceeded")
        return {"round":body.round,"budget":budget,"carryover":carryover,"spent":spent,
                "remaining":budget-spent,"unlocked":list(config.unlocked),"costs":BOOSTERS,
                "eligibility":"Advancement is declared locally; the README does not specify an organizer qualification cutoff."}

    @app.get("/api/health")
    def health():
        return {"status": "ok", "engine_kind": "local_approximation"}

    @app.get("/api/strategy-template",response_class=PlainTextResponse)
    def template():
        return TEMPLATE

    @app.post("/api/validate")
    def validation(body: Upload):
        return validate_source(body.source)

    @app.post("/api/validate-runtime")
    def runtime_validation(body: Upload):
        result = validate_source(body.source)
        if not result["valid"]:
            return result
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/"strategy.py").write_text(body.source,encoding="utf-8")
            with StrategyProcess(folder,seed="validation-only") as worker:
                return {"valid":worker.last_status == "ready",
                        "errors":[] if worker.last_status == "ready" else [{"line":None,"message":e["detail"] or e["status"]} for e in worker.events],
                        "note":"Runtime import/interface check only; on_state actions are validated during battle."}

    @app.post("/api/armory")
    def armory(body: ArmoryOptions):
        return quote_armory(body)

    @app.get("/api/armory/carryover")
    def carryover_sources():
        candidates = []
        with guard:
            for identifier, session in sessions.items():
                b = session.battle
                if b.finished and not b.abandoned and b.config.name == "round2":
                    candidates.append({"id":identifier,"points":b.remaining_points["A"],"label":f"Round 2 seed {b.seed} (live)"})
        for path in sorted(experiments.glob("*.json"),reverse=True):
            saved = json.loads(path.read_text(encoding="utf-8"))
            frame = saved.get("frames",[{}])[-1] if saved.get("frames") else {}
            if saved["kind"] == "battle" and frame.get("finished") and not frame.get("abandoned") and frame.get("armory",{}).get("round") == "round2":
                candidates.append({"id":saved["id"],"points":frame["armory"]["remaining_points"],"label":saved["title"]})
        return candidates

    @app.get("/api/opponents/{level}")
    def opponent_preview(level: str):
        from .opponents import LEVELS
        algorithms = {"easy":"Random reachable targets; learns wind from its own landings.",
                      "medium":"Random search, then neighbours of hits and revealed cells.",
                      "hard":"Parity search, target pursuit, and flares without a lead.",
                      "expert":"Counts compatible straight ship placements at sampled candidate cells.",
                      "extreme":"Probability hunter with targeted clusters and clear-line torpedoes."}
        if level not in LEVELS:
            raise HTTPException(404,"Unknown opponent difficulty")
        return {"name":LEVELS[level],"level":level,"official":False,"implementation":"local_approximation",
                "algorithm":algorithms[level],"source":Path(__file__).with_name("opponents.py").read_text(encoding="utf-8"),
                "note":"Actual local source shared by the five difficulty policies. Official opponent source is unavailable."}

    @app.get("/api/versions")
    def list_versions():
        with guard:
            return [{"id": p.name, "label": metadata.get(p.name, p.name[:12]),
                     "bytes": (p/"strategy.py").stat().st_size}
                    for p in sorted(versions.iterdir()) if re.fullmatch(r"[a-f0-9]{64}", p.name) and (p/"strategy.py").is_file()]

    @app.post("/api/versions", status_code=201)
    def upload(body: Upload):
        try:
            content = base64.b64decode(body.source_base64, validate=True) if body.source_base64 is not None else body.source.encode("utf-8")
            content.decode("utf-8-sig")
        except (binascii.Error, UnicodeError) as exc:
            raise HTTPException(422, "Upload a UTF-8 Python file") from exc
        if not body.filename.lower().endswith(".py") or len(content) > 262144:
            raise HTTPException(422, "Upload a Python file up to 256 KiB")
        validation = validate_source(content)
        if not validation["valid"]:
            raise HTTPException(422,validation["errors"])
        with guard, tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"strategy.py"
            path.write_bytes(content)
            version = import_strategy(path, versions)
            metadata[version.name] = body.label.strip() or body.filename
            save_labels()
            return {"id": version.name, "label": metadata[version.name]}

    @app.get("/api/versions/{identifier}/source", response_class=PlainTextResponse)
    def source(identifier: str):
        return PlainTextResponse((version_path(identifier)/"strategy.py").read_bytes(),
                                 headers={"Content-Disposition": 'attachment; filename="strategy.py"'})

    @app.patch("/api/versions/{identifier}")
    def rename(identifier: str, body: Label):
        version_path(identifier)
        with guard:
            metadata[identifier] = body.label
            save_labels()
        return {"id": identifier, "label": body.label}

    @app.post("/api/battles", status_code=201)
    def new_battle(body: BattleOptions):
        path = version_path(body.version)
        validate_options(body.round, body.difficulty)
        if body.round == "all":
            raise HTTPException(422, "Select one round for a battle")
        with guard:
            # The browser is the only client for this loopback app.  A refresh,
            # hot reload, or abandoned tab can lose the client-side battle id;
            # reclaim those in-memory sessions before enforcing the retention cap.
            for identifier, old_session in list(sessions.items()):
                if len(sessions) >= 8 and identifier != body.carryover_from and old_session.battle.finished:
                    if old_session.lock.acquire(blocking=False):
                        try:
                            old_session.strategy.close()
                            sessions.pop(identifier, None)
                        finally:
                            old_session.lock.release()
            if len(sessions) >= 8:
                raise HTTPException(409, "Close an active battle before creating another")
            quote = quote_armory(body)
            seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
            config = RoundConfig.preset(body.round)
            purchases = {s: opponent_loadout(config, body.difficulty, s) for s in "ABCDEFGHIJKLMNOPQRST"[1:body.teams]}
            b = Battle(seed, seats=body.teams, config=config,
                       purchases={**purchases,"A":body.loadout}, carryover={"A":quote["carryover"]})
            worker = StrategyProcess(path, seed=f"{seed}:bot:A", max_restarts=2)
            if worker.last_status != "ready":
                worker.close()
                raise HTTPException(422, worker.events)
            session = Session(b, worker, {s: Opponent(body.difficulty, f"{seed}:bot:{s}") for s in b.seats if s != "A"}, body.version)
            from .opponents import LEVELS
            session.team_names = {s:metadata.get(body.version,"Your strategy") if s == "A" else f"{LEVELS[body.difficulty]} · {s}" for s in b.seats}
            # Freeze provenance and source from the actual instances, not later UI selections.
            import inspect
            session.team_strategies = {"A": {"name": session.team_names["A"], "type": "MyBot", "level": None,
                                             "official": False, "implementation": "custom_strategy", "version": body.version,
                                             "source": (path/"strategy.py").read_text(encoding="utf-8-sig")}}
            for seat, opponent in session.opponents.items():
                session.team_strategies[seat] = {**opponent_preview(opponent.level), "type": type(opponent).__name__,
                                                "source": inspect.getsource(inspect.getmodule(type(opponent)))}
            identifier = uuid.uuid4().hex
            sessions[identifier] = session
            return {"id": identifier, "seed":seed,"armory":quote,"frame": session.snapshot()}

    def get_session(identifier):
        with guard:
            if identifier not in sessions:
                raise HTTPException(404, "Unknown battle")
            return sessions[identifier]

    @app.get("/api/battles/active")
    def active_battle():
        """Return the local live battle so a refreshed UI can reconnect to it."""
        with guard:
            for identifier, session in sessions.items():
                if not session.battle.finished:
                    return {"id": identifier, "frame": session.frames[-1]}
        return None

    @app.post("/api/battles/{identifier}/step")
    def step(identifier: str, body: StepOptions | None = None):
        session = get_session(identifier)
        frame = session.step(body.expected_tick if body else None)
        with session.lock:
            if frame["finished"]:
                persist_result(session)
            return frame

    def persist_result(session):
        # Called with session.lock held; retries/repeated steps never duplicate history.
        if session.result_id:
            return get_experiment(session.result_id)
        identifier = uuid.uuid4().hex
        session.frames[-1]["history_id"] = identifier
        value = save_experiment("battle", {"version":session.version,"seed":session.battle.seed,
                               "frames":session.frames,"ranking":session.frames[-1]["ranking"],
                               "diagnostics":diagnose(session.recorder.events if session.recorder else [])},
                               f"Battle seed {session.battle.seed} · {session.battle.tick} ticks",identifier)
        session.result_id = identifier
        return value

    @app.get("/api/battle-history")
    def battle_history():
        history = []
        for path in sorted(experiments.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True):
            value = json.loads(path.read_text(encoding="utf-8"))
            frames = value.get("frames",[])
            if value.get("kind") == "battle" and frames and frames[-1].get("finished"):
                final = frames[-1]
                history.append({"id":value["id"],"title":value["title"],"created_at":value["created_at"],
                                "seed":value["seed"],"tick":final["tick"],"abandoned":final["abandoned"],
                                "ranking":final["ranking"],"teams":final["teams"]})
        return history

    @app.get("/api/battles/{identifier}/frames/{index}")
    def replay(identifier: str, index: int):
        session = get_session(identifier)
        with session.lock:
            if not 0 <= index < len(session.frames):
                raise HTTPException(404, "Unknown frame")
            return session.frames[index]

    @app.delete("/api/battles/{identifier}")
    def close_battle(identifier: str):
        session = get_session(identifier)
        with session.lock:
            session.strategy.close()
        with guard:
            sessions.pop(identifier, None)
        return {"closed": True}

    @app.get("/api/battles/{identifier}/diagnostics")
    def battle_diagnostics(identifier: str):
        session = get_session(identifier)
        with session.lock:
            return diagnose(session.recorder.events if session.recorder else [])

    @app.post("/api/battles/{identifier}/experiments",status_code=201)
    def save_battle_experiment(identifier: str):
        session = get_session(identifier)
        with session.lock:
            if session.battle.finished:
                return persist_result(session)
            return save_experiment("battle", {"version":session.version,"seed":session.battle.seed,
                                   "frames":session.frames,"diagnostics":diagnose(session.recorder.events if session.recorder else [])},
                                   f"Battle seed {session.battle.seed} · {session.battle.tick} ticks")

    def run_job(identifier, body, paths):
        try:
            def progress(done, total):
                with guard:
                    jobs[identifier]["done"] = done
                    jobs[identifier]["total"] = total
            report = benchmark(paths, body.matches, body.teams, body.round, body.difficulty,
                               body.pool, body.master_seed, body.loadout, progress=progress)
            (reports/f"{identifier}.json").write_text(json.dumps(report), encoding="utf-8")
            experiment = save_experiment("benchmark", {"report":report,"diagnostics":report.get("diagnostics",{"findings":[]})},
                                         f"{body.pool} · {body.round} · {body.matches} matches/version")
            with guard:
                jobs[identifier].update(status="complete", report=report, experiment_id=experiment["id"])
        except Exception as exc:
            with guard:
                jobs[identifier].update(status="failed", error=f"{type(exc).__name__}: {exc}")

    @app.post("/api/benchmarks", status_code=202)
    def start_benchmark(body: BenchmarkOptions):
        validate_options(body.round, body.difficulty, body.pool, body.loadout)
        paths = [version_path(v) for v in body.versions]
        if len(set(body.versions)) != len(body.versions):
            raise HTTPException(422, "Select distinct versions")
        with guard:
            if any(j["status"] == "running" for j in jobs.values()):
                raise HTTPException(409, "A benchmark is already running")
            identifier = uuid.uuid4().hex
            jobs[identifier] = {"id": identifier, "status": "running", "done": 0, "total": body.matches*len(paths)*(3 if body.round == "all" else 1)}
            threading.Thread(target=run_job, args=(identifier, body, paths), daemon=True).start()
            return dict(jobs[identifier])

    @app.get("/api/benchmarks")
    def list_benchmarks():
        with guard:
            result = [{k:v for k,v in j.items() if k != "report"} for j in jobs.values()]
            known = set(jobs)
        return result + [{"id": p.stem, "status": "complete"} for p in sorted(reports.glob("*.json")) if p.stem not in known]

    @app.get("/api/benchmarks/{identifier}")
    def job(identifier: str):
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise HTTPException(404, "Unknown benchmark")
        with guard:
            if identifier in jobs:
                return dict(jobs[identifier])
        path = reports/f"{identifier}.json"
        if path.is_file():
            return {"id": identifier, "status": "complete", "report": json.loads(path.read_text(encoding="utf-8"))}
        raise HTTPException(404, "Unknown benchmark")

    @app.get("/api/experiments")
    def experiment_history():
        items = []
        for path in sorted(experiments.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True):
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append({k:data[k] for k in ("id","kind","title","created_at")})
        return items

    @app.get("/api/experiments/{identifier}")
    def experiment(identifier: str):
        return get_experiment(identifier)

    @app.get("/api/experiments/{identifier}/export/{format}")
    def export_experiment(identifier: str, format: str):
        value = get_experiment(identifier)
        try:
            content, media = export_report(value,format)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        extension = "md" if format == "markdown" else format
        return PlainTextResponse(content,media_type=media,headers={"Content-Disposition":f'attachment; filename="experiment-{identifier}.{extension}"'})

    @app.get("/api/experiments/{identifier}/prompt",response_class=PlainTextResponse)
    def prompt(identifier: str, round: str | None = None, strategy: int = 0, match: int = 0):
        value = get_experiment(identifier)
        if value["kind"] == "benchmark" and round:
            try:
                if strategy < 0 or match < 0:
                    raise IndexError
                run = value["report"]["rounds"][round]["strategies"][strategy]
                record = run["records"][match]
                context = {k:v for k,v in value["report"].items() if k not in ("rounds", "diagnostics", "seeds")}
                return improvement_prompt({**context, **record, "version":run["version"], "round":round})
            except (KeyError,IndexError) as exc:
                raise HTTPException(404,"Match diagnostics unavailable") from exc
        return improvement_prompt(value)

    @app.post("/api/experiments/compare-pools")
    def compare_experiment_pools(body: ExperimentComparison):
        a, b = get_experiment(body.development),get_experiment(body.validation)
        if a["kind"] != "benchmark" or b["kind"] != "benchmark":
            raise HTTPException(422,"Select two benchmark experiments")
        try:
            comparison = compare_pools(a["report"],b["report"])
        except (ValueError,KeyError) as exc:
            raise HTTPException(422,str(exc)) from exc
        findings = [{"classification":row["classification"],"code":"pool_comparison","message":f'{row["round"]} {row["version"]} {row["metric"]}: holdout minus development = {row["holdout_minus_development"]:.3f}. {row["interpretation"]}',
                     "evidence":[{"development_experiment":a["id"],"validation_experiment":b["id"],**row["evidence"]}]} for row in comparison["comparisons"]]
        return save_experiment("pool_comparison", {"comparison":comparison,"diagnostics":{"findings":findings}},"Development vs validation")

    @app.get("/api/experiments/{identifier}/replay/{tick}")
    def failure_replay(identifier: str, tick: int, round: str = "round1", strategy: int = 0, match: int = 0):
        data = get_experiment(identifier)
        try:
            if data["kind"] == "battle":
                if not 0 <= tick < len(data["frames"]):
                    raise ValueError("Tick outside replay")
                return data["frames"][tick]
            if strategy < 0 or match < 0:
                raise ValueError("Negative replay index")
            record = data["report"]["rounds"][round]["strategies"][strategy]["records"][match]
            return replay_frame(record["replay"],tick)
        except (KeyError,IndexError,ValueError) as exc:
            raise HTTPException(404,"Original replay unavailable for this selection") from exc

    dist = Path(__file__).resolve().parent.parent/"frontend"/"dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app
