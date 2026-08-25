"""
Hvězdné drby — digitální verze
Webová aplikace pro cca 10 týmů hrajících současně na vlastních zařízeních.
Server je autoritativní zdroj pravdy (otázky, čas, skóre) — klient jen
zobrazuje a odesílá volby. Stejný princip jako TeamQuest: Putování pod
hvězdami, jen s vtipnými/drbnovskými otázkami a hvězdou jako výslednou
kresbou (namísto rakety).
"""
import json, os, time, uuid, hashlib, random
from flask import Flask, request, session, jsonify, render_template, redirect, url_for

from geometry import star_points, wrong_points

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
QUESTIONS_PATH = os.path.join(DATA_DIR, "questions.json")
TEAMS_PATH = os.path.join(DATA_DIR, "teams.json")
os.makedirs(DATA_DIR, exist_ok=True)  # teams.json is created on first save — no need to upload an empty one

with open(QUESTIONS_PATH, encoding="utf-8") as f:
    QUESTIONS = json.load(f)

N = len(QUESTIONS)
STAR_PTS = star_points(N)
WRONG_PTS = wrong_points(STAR_PTS)

TIME_LIMIT = 20      # seconds for full speed bonus window
BASE_SCORE = 100
BONUS_MAX = 50

app = Flask(__name__)
# Stable secret (not regenerated per process start) so a free-tier host's
# cold-start/restart mid-event doesn't silently log every team out.
app.secret_key = os.environ.get("SECRET_KEY", "hvezdne-drby-2026-static-key")

TEAMS = {}  # team_id -> dict, in-memory + persisted to disk
# NOTE: state lives in this process's memory. Run with exactly ONE worker
# process (see Procfile: --workers 1, --threads N is fine) — multiple
# worker *processes* would each have their own empty TEAMS dict and teams
# would randomly "disappear" depending on which worker handled a request.


def save_teams():
    try:
        with open(TEAMS_PATH, "w", encoding="utf-8") as f:
            json.dump(TEAMS, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print("warn: could not persist teams.json:", e)


def load_teams():
    global TEAMS
    if os.path.exists(TEAMS_PATH):
        try:
            with open(TEAMS_PATH, encoding="utf-8") as f:
                TEAMS = json.load(f)
        except Exception:
            TEAMS = {}


load_teams()


def option_map_for(team_id, idx):
    """Deterministic per-team shuffle of which side ('left'/'right') shows
    option 'a' vs 'b', so the true/false pattern can't be memorised across
    teams or guessed question-to-question."""
    h = hashlib.sha256(f"{team_id}:{idx}".encode()).hexdigest()
    flip = int(h[:8], 16) % 2 == 0
    return {"left": "a", "right": "b"} if flip else {"left": "b", "right": "a"}


def get_team():
    tid = session.get("team_id")
    if not tid or tid not in TEAMS:
        return None
    return TEAMS[tid]


@app.route("/")
def join_page():
    return render_template("join.html")


@app.route("/api/join", methods=["POST"])
def api_join():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()[:40]
    if not name:
        return jsonify({"error": "Zadejte název týmu."}), 400
    tid = uuid.uuid4().hex[:10]
    TEAMS[tid] = {
        "id": tid,
        "name": name,
        "created_at": time.time(),
        "idx": 0,
        "answers": [],
        "q_started_at": None,
        "finished": False,
        "finished_at": None,
        "total_score": 0,
        "total_time": 0,
    }
    save_teams()
    session["team_id"] = tid
    return jsonify({"ok": True, "team_id": tid, "name": name})


@app.route("/play")
def play_page():
    if not get_team():
        return redirect(url_for("join_page"))
    return render_template("play.html")


def current_rank(team_id):
    """Provisional rank of a team among ALL teams that have joined so far
    (finished or still playing), based on points earned up to this moment.
    This is a live/informal standing shown to a team while it is still
    playing — not the same as the final /board ranking, which only lists
    teams once they've completed all questions."""
    ranked = sorted(
        TEAMS.values(),
        key=lambda t: (-t["total_score"], -t["idx"]),
    )
    total = len(ranked)
    for i, t in enumerate(ranked, start=1):
        if t["id"] == team_id:
            return i, total
    return None, total


@app.route("/api/question")
def api_question():
    team = get_team()
    if not team:
        return jsonify({"error": "no-session"}), 401
    if team["finished"] or team["idx"] >= N:
        return jsonify({"finished": True})
    idx = team["idx"]
    q = QUESTIONS[idx]
    if team["q_started_at"] is None:
        team["q_started_at"] = time.time()
        save_teams()
    omap = option_map_for(team["id"], idx)
    options = [
        {"key": "left", "text": q[omap["left"]]},
        {"key": "right", "text": q[omap["right"]]},
    ]
    rank, total_teams = current_rank(team["id"])
    return jsonify({
        "finished": False,
        "index": idx,
        "total": N,
        "topic": q["topic"],
        "text": q["q"],
        "options": options,
        "score_so_far": team["total_score"],
        "rank": rank,
        "total_teams": total_teams,
    })


@app.route("/api/answer", methods=["POST"])
def api_answer():
    team = get_team()
    if not team:
        return jsonify({"error": "no-session"}), 401
    if team["finished"] or team["idx"] >= N:
        return jsonify({"error": "already-finished"}), 400
    data = request.get_json(force=True)
    choice = data.get("choice")
    if choice not in ("left", "right"):
        return jsonify({"error": "bad-choice"}), 400

    idx = team["idx"]
    q = QUESTIONS[idx]
    started = team["q_started_at"] or time.time()
    elapsed = max(0.0, time.time() - started)

    omap = option_map_for(team["id"], idx)
    chosen_letter = omap[choice]
    correct = (chosen_letter == q["correct"])

    bonus = 0
    if correct:
        frac = max(0.0, 1 - (elapsed / TIME_LIMIT))
        bonus = round(BONUS_MAX * frac)
    score_gained = (BASE_SCORE + bonus) if correct else 0

    team["answers"].append({
        "idx": idx, "correct": correct, "elapsed": round(elapsed, 2),
        "score_gained": score_gained,
    })
    team["total_score"] += score_gained
    team["total_time"] += elapsed
    team["idx"] += 1
    team["q_started_at"] = None

    finished_now = team["idx"] >= N
    if finished_now:
        team["finished"] = True
        team["finished_at"] = time.time()

    save_teams()
    rank, total_teams = current_rank(team["id"])
    return jsonify({
        "correct": correct,
        "note": q["note"],
        "score_gained": score_gained,
        "total_score": team["total_score"],
        "finished": finished_now,
        "rank": rank,
        "total_teams": total_teams,
    })


def team_path(team):
    pts = []
    all_correct = True
    for a in team["answers"]:
        i = a["idx"]
        if a["correct"]:
            pts.append(STAR_PTS[i])
        else:
            pts.append(WRONG_PTS[i])
            all_correct = False
    return pts, all_correct


@app.route("/result")
def result_page():
    if not get_team():
        return redirect(url_for("join_page"))
    return render_template("result.html")


@app.route("/api/result")
def api_result():
    team = get_team()
    if not team:
        return jsonify({"error": "no-session"}), 401
    if not team["finished"]:
        return jsonify({"finished": False})
    pts, all_correct = team_path(team)
    n_correct = sum(1 for a in team["answers"] if a["correct"])
    return jsonify({
        "finished": True,
        "name": team["name"],
        "total_score": team["total_score"],
        "total_time": round(team["total_time"], 1),
        "n_correct": n_correct,
        "n_total": N,
        "all_correct": all_correct,
        "path": pts,
    })


@app.route("/board")
def board_page():
    return render_template("board.html")


@app.route("/admin")
def admin_page():
    return render_template("admin.html")


@app.route("/api/leaderboard")
def api_leaderboard():
    finished = [t for t in TEAMS.values() if t["finished"]]
    finished.sort(key=lambda t: (-t["total_score"], t["total_time"]))
    out = []
    for rank, t in enumerate(finished, start=1):
        pts, all_correct = team_path(t)
        n_correct = sum(1 for a in t["answers"] if a["correct"])
        out.append({
            "rank": rank,
            "name": t["name"],
            "total_score": t["total_score"],
            "total_time": round(t["total_time"], 1),
            "n_correct": n_correct,
            "n_total": N,
            "all_correct": all_correct,
            "path": pts,
            "finished_at": t["finished_at"],
        })
    in_progress = sum(1 for t in TEAMS.values() if not t["finished"])
    return jsonify({"teams": out, "in_progress": in_progress, "n_total_questions": N})


ADMIN_KEY = os.environ.get("ADMIN_KEY")  # optional: set this env var on the host to protect /reset


@app.route("/api/admin/reset", methods=["POST"])
def api_reset():
    """Wipe all teams — organizer-only, call manually between runs of the game.
    If ADMIN_KEY is set (recommended for a public cloud deploy), the same
    value must be passed as ?key=... or it's rejected."""
    if ADMIN_KEY and request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    global TEAMS
    TEAMS = {}
    save_teams()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    if "PORT" in os.environ:
        print("Hvezdne drby server starting on port", port)
    else:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
        finally:
            s.close()
        print("=" * 60)
        print(" Hvězdné drby — server běží")
        print(f" Týmy se připojí na:  http://{local_ip}:{port}")
        print(f" Promítání výsledků:  http://{local_ip}:{port}/board")
        print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
