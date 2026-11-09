import os
import re
import secrets
import string
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")

app = Flask(__name__)

# Everything lives in memory, so the app starts empty on every run.
users = {
    0: {
        "name": "admin",
        "user-id": 0,
        "API-key": "ytngh52@gb&&ubt8"
    }
}

exercises = {}
schedule_list = []
next_user_id = 1
last_appt_id = {}  # highest appt-id given out so far, per user
PERIODS = ["morning", "afternoon", "evening"]


def generate_api_key():
    """16 random letters and digits"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))


def is_admin():
    """True if the request carries the admin's key"""
    return request.headers.get("X-Api-Key") == users[0]["API-key"]


def generate_exercise_code(name):
    """First 3 letters of the name plus the lowest free digit, like bic1, bic2."""
    prefix = (name.replace(" ", "").lower() + "xxx")[:3]
    count = 1
    while f"{prefix}{count}" in exercises:
        count += 1
    return f"{prefix}{count}"


DATE_PATTERN = re.compile(r"\d{2}/\d{2}/\d{4}")


def validate_date(date_str):
    """Return None if the date is fine, otherwise the error response to send.
    400 if it isn't a real DD/MM/YYYY date, 422 if it's outside 15/11-15/12/2026."""
    if not isinstance(date_str, str) or not DATE_PATTERN.fullmatch(date_str):
        return jsonify({"error": "Malformed date, expected DD/MM/YYYY"}), 400
    try:
        d = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return jsonify({"error": "Malformed date, not a real calendar day"}), 400
    if not datetime(2026, 11, 15) <= d <= datetime(2026, 12, 15):
        return jsonify({"error": "Date must be between 15/11/2026 and 15/12/2026"}), 422
    return None


def find_free_period(user_id, exercise_code, date, period, skip=None):
    """First period the user can book: nobody holds this exercise then, and the user has nothing
    else then. Tries only `period` if given, otherwise all of them. `skip` is an appointment that
    is being moved, so it doesn't block itself. Returns None if nothing is free."""
    for p in ([period] if period else PERIODS):
        busy = any(s is not skip and s['date'] == date and s['period'] == p
                   and (s['exercise-code'] == exercise_code or s['user-id'] == user_id)
                   for s in schedule_list)
        if not busy:
            return p
    return None


# --- Request checks that run before every route ---
@app.before_request
def require_api_key():
    # No key needed for /register and /validate (GET /register checks admin itself).
    # Unknown routes fall through to the 404/405 handlers below.
    if request.endpoint in [None, 'register_post', 'register_get', 'validate_user']:
        return

    api_key = request.headers.get("X-Api-Key")
    if not api_key:
        return jsonify({"error": "Missing API Key header"}), 401

    # URLs with a user-id need that user's own key, all others accept any registered key.
    user_id = request.view_args.get('user_id')
    if user_id is not None:
        valid = user_id in users and users[user_id]["API-key"] == api_key
    else:
        valid = any(u["API-key"] == api_key for u in users.values())
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401


@app.before_request
def require_json_body():
    # POST and PUT bodies must be a JSON object, so the routes can rely on that.
    if request.endpoint is None or request.method not in ('POST', 'PUT'):
        return
    if not request.is_json:
        return jsonify({"error": "Expected application/json media type"}), 415
    if not isinstance(request.get_json(silent=True), dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400


# --- JSON errors instead of Flask's HTML pages ---
@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error"}), 500


# 1. /register
@app.route('/register', methods=['POST'], endpoint='register_post')
def register_post():
    global next_user_id

    name = request.get_json().get('name')
    if not name or not isinstance(name, str):
        return jsonify({"error": "Malformed input"}), 400

    if any(u['name'] == name for u in users.values()):
        return jsonify({"error": "User already registered"}), 422

    new_api_key = generate_api_key()
    while any(u['API-key'] == new_api_key for u in users.values()):
        new_api_key = generate_api_key()

    new_user = {
        "name": name,
        "user-id": next_user_id,
        "API-key": new_api_key
    }

    users[next_user_id] = new_user
    next_user_id += 1

    return jsonify(new_user), 201


@app.route('/register', methods=['GET'], endpoint='register_get')
def register_get():
    # Admin only
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(list(users.values())), 200


# 2. /validate/{user-id}
@app.route('/validate/<int:user_id>', methods=['POST'])
def validate_user(user_id):
    api_key = request.get_json().get('API-key')
    if not api_key:
        return jsonify({"error": "Malformed input"}), 400

    # Same 401 whether the id or the key is wrong
    if user_id not in users or users[user_id]["API-key"] != api_key:
        return jsonify({"error": "Unauthorized"}), 401

    # Validation creates nothing, so success is 200. Only admin (id 0) is privileged.
    return jsonify({"privileged": user_id == 0}), 200


# 3. /exercises
@app.route('/exercises', methods=['POST'])
def add_exercise():
    # Admin only
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    name = request.get_json().get('name')
    if not name or not isinstance(name, str):
        return jsonify({"error": "Malformed input"}), 400

    try:
        response = requests.get("https://api.api-ninjas.com/v1/exercises", params={"name": name},
                                headers={'X-Api-Key': API_NINJAS_KEY}, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": "API Ninjas error"}), 502
        results = response.json()
    except requests.RequestException:
        return jsonify({"error": "API Ninjas connection error"}), 502

    # Ninja returns partial matches too, we only accept the exact name (any capitalization).
    exact_match = next((ex for ex in results if ex['name'].lower() == name.lower()), None)
    if not exact_match:
        return jsonify({"error": "No exact match found"}), 422

    exercise_code = generate_exercise_code(exact_match['name'])

    # Ninja calls it 'muscle', we call it 'muscle-group'
    new_exercise = {
        "name": exact_match['name'],
        "type": exact_match['type'],
        "muscle-group": exact_match['muscle'],
        "difficulty": exact_match['difficulty'],
        "exercise-code": exercise_code
    }

    exercises[exercise_code] = new_exercise
    return jsonify(new_exercise), 201


@app.route('/exercises', methods=['GET'])
def get_exercises():
    allowed_queries = {'type', 'muscle-group', 'difficulty'}
    filters = {}

    for key in request.args:
        if key not in allowed_queries:
            return jsonify({"error": f"Bad Request: unknown query string {key}"}), 400
        filters[key] = request.args.get(key)

    # No matches is not an error, just an empty list
    return jsonify([ex for ex in exercises.values()
                    if all(ex.get(key) == val for key, val in filters.items())]), 200


# 4. /exercises/{exercise-code}
@app.route('/exercises/<exercise_code>', methods=['GET'])
def get_exercise_by_code(exercise_code):
    if exercise_code not in exercises:
        return jsonify({"error": "Exercise not found"}), 404

    ex = exercises[exercise_code]
    return jsonify({
        "name": ex["name"],
        "type": ex["type"],
        "muscle-group": ex["muscle-group"],
        "difficulty": ex["difficulty"]
    }), 200


@app.route('/exercises/<exercise_code>', methods=['DELETE'])
def delete_exercise(exercise_code):
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    if exercise_code not in exercises:
        return jsonify({"error": "Exercise not found"}), 404

    del exercises[exercise_code]
    # Stop offering the exercise, but keep appointments already made for it.
    return '', 204


def get_next_appt_id(user_id):
    """Next appt-id for this user, never reused even after a cancellation"""
    last_appt_id[user_id] = last_appt_id.get(user_id, 0) + 1
    return last_appt_id[user_id]


# 5. /schedule/{user-id}/{exercise-code}
@app.route('/schedule/<int:user_id>/<exercise_code>', methods=['POST'])
def create_schedule(user_id, exercise_code):
    data = request.get_json()
    date_str = data.get('date')
    period = data.get('period')

    date_error = validate_date(date_str)
    if date_error:
        return date_error

    if period and period not in PERIODS:
        return jsonify({"error": "Invalid period"}), 400

    if exercise_code not in exercises:
        return jsonify({"error": "Exercise not found"}), 404

    selected_period = find_free_period(user_id, exercise_code, date_str, period)

    # Nothing free: 422 with availability False and appt-id 0.
    if not selected_period:
        return jsonify({
            "appt-id": 0,
            "user-id": user_id,
            "availability": False,
            "exercise-code": exercise_code,
            "date": date_str,
            "period": period if period else ""
        }), 422

    if sum(1 for s in schedule_list if s['user-id'] == user_id) >= 3:
        return jsonify({"error": "Maximum of 3 active appointments allowed"}), 422

    new_appt = {
        "appt-id": get_next_appt_id(user_id),
        "user-id": user_id,
        "availability": True,
        "exercise-code": exercise_code,
        "date": date_str,
        "period": selected_period
    }

    schedule_list.append(new_appt)
    return jsonify(new_appt), 201


# 6. /schedule/{user-id}/{appt-id}
@app.route('/schedule/<int:user_id>/<int:appt_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_appointment(user_id, appt_id):
    appt = next((s for s in schedule_list if s['user-id'] == user_id and s['appt-id'] == appt_id), None)
    if not appt:
        return jsonify({"error": "Appointment not found"}), 404

    if request.method == 'GET':
        return jsonify(appt), 200

    if request.method == 'DELETE':
        schedule_list.remove(appt)
        return '', 204

    data = request.get_json()
    date_str = data.get('date')
    period = data.get('period')

    date_error = validate_date(date_str)
    if date_error:
        return date_error

    if period and period not in PERIODS:
        return jsonify({"error": "Invalid period"}), 400

    selected_period = find_free_period(user_id, appt['exercise-code'], date_str, period, skip=appt)
    if not selected_period:
        return jsonify({
            "error": "Requested replacement slot is already occupied or unavailable"
        }), 422

    # Move the appointment in place, so the appt-id stays the same
    appt['date'] = date_str
    appt['period'] = selected_period
    return jsonify(appt), 200


# 7. /schedule
@app.route('/schedule', methods=['GET'])
def get_all_schedules():
    # Admin only
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    for key in request.args:
        if key != 'exercise-code':
            return jsonify({"error": f"Bad Request: unknown query string {key}"}), 400

    results = schedule_list
    ex_code_filter = request.args.get('exercise-code')
    if ex_code_filter:
        results = [s for s in results if s['exercise-code'] == ex_code_filter]

    return jsonify([
        {
            "exercise-code": r["exercise-code"],
            "appt-id": r["appt-id"],
            "date": r["date"],
            "period": r["period"],
            "user-id": r["user-id"]
        } for r in results
    ]), 200


if __name__ == '__main__':
    # The container has to listen on 0.0.0.0:5001
    app.run(host='0.0.0.0', port=5001, debug=False)
