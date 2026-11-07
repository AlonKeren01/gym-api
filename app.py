import os
import random
import re
import string
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()
API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")

app = Flask(__name__)

# --- In-Memory State ---
# The application must start from scratch every time it runs.
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

def generate_api_key():
    """Generates a 16-character alphanumeric string."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

def is_admin():
    """Checks if the current request is from the admin."""
    api_key = request.headers.get("X-Api-Key")
    return api_key and users[0]["API-key"] == api_key

def generate_exercise_code(name):
    """Generates a code using the first 3 letters of the name + a digit."""
    prefix = (name.replace(" ", "").lower() + "xxx")[:3]
    count = 1
    while f"{prefix}{count}" in exercises:
        count += 1
    return f"{prefix}{count}"

DATE_PATTERN = re.compile(r"\d{2}/\d{2}/\d{4}")  # strict DD/MM/YYYY

def validate_date(date_str):
    """None if valid, else an error response: 400 not a real DD/MM/YYYY date, 422 outside the window."""
    if not isinstance(date_str, str) or not DATE_PATTERN.fullmatch(date_str):
        return jsonify({"error": "Malformed date, expected DD/MM/YYYY"}), 400
    try:
        d = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return jsonify({"error": "Malformed date, not a real calendar day"}), 400
    if not datetime(2026, 11, 15) <= d <= datetime(2026, 12, 15):
        return jsonify({"error": "Date must be between 15/11/2026 and 15/12/2026"}), 422
    return None


# --- Authentication Middleware ---
@app.before_request
def require_api_key():
    # Skipped: /register and /validate (GET /register checks admin itself) and unknown routes (404/405).
    if request.endpoint in [None, 'register_post', 'register_get', 'validate_user']:
        return

    api_key = request.headers.get("X-Api-Key")
    if not api_key:
        return jsonify({"error": "Missing API Key header"}), 401

    # A URL with a user-id needs that user's key; any other URL needs some registered user's key.
    user_id = request.view_args.get('user_id')
    if user_id is not None:
        valid = user_id in users and users[user_id]["API-key"] == api_key
    else:
        valid = any(u["API-key"] == api_key for u in users.values())
    if not valid:
        return jsonify({"error": "Unauthorized"}), 401


@app.before_request
def require_json_body():
    # POST/PUT bodies must be a JSON object: 415 for another Content-Type, 400 if it is not an object.
    if request.endpoint is None or request.method not in ('POST', 'PUT'):
        return
    if not request.is_json:
        return jsonify({"error": "Expected application/json media type"}), 415
    if not isinstance(request.get_json(silent=True), dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400


# --- JSON errors instead of Flask's default HTML pages ---
@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method not allowed"}), 405

@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error"}), 500


#1. /register
@app.route('/register', methods=['POST'], endpoint='register_post')
def register_post():
    global next_user_id
    
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    
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
    # Only allowed by the admin.
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(list(users.values())), 200


#2. /validate/{user-id}
@app.route('/validate/<int:user_id>', methods=['POST'])
def validate_user(user_id):
    data = request.get_json(silent=True) or {}
    api_key = data.get('API-key')
    
    if not api_key:
        return jsonify({"error": "Malformed input"}), 400
        
    if user_id not in users or users[user_id]["API-key"] != api_key:
        return jsonify({"error": "Unauthorized"}), 401
    
    #True if used id has admin privileges
    is_privileged = (user_id == 0)
    return jsonify({"privileged": is_privileged}), 201


#3. /exercises
@app.route('/exercises', methods=['POST'])
def add_exercise():
    # Only allowed by the admin
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    name = data.get('name')
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

    # Exact name match required, ignoring capitalization
    exact_match = next((ex for ex in results if ex['name'].lower() == name.lower()), None)
    if not exact_match:
        return jsonify({"error": "No exact match found"}), 422

    exercise_code = generate_exercise_code(exact_match['name'])
    
    # Map API-Ninja's 'muscle' to 'muscle-group'
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
        # Nonsensical query strings return 400
        if key not in allowed_queries:
            return jsonify({"error": f"Bad Request: unknown query string {key}"}), 400
        filters[key] = request.args.get(key)

    filtered_exercises = []
    for ex in exercises.values():
        match = True
        for key, val in filters.items():
            if ex.get(key) != val:
                match = False
                break
        if match:
            filtered_exercises.append(ex)

    # Empty array returned if no matches
    return jsonify(filtered_exercises), 200


#4. /exercises/{exercise-code}
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
    return '', 204


def get_next_appt_id(user_id):
    """Generates a unique appt-id > 0 for a specific user-id."""
    user_appts = [s['appt-id'] for s in schedule_list if s['user-id'] == user_id]
    return max(user_appts) + 1 if user_appts else 1 #


# --- 5. /schedule/{user-id}/{exercise-code} ---
@app.route('/schedule/<int:user_id>/<exercise_code>', methods=['POST'])
def create_schedule(user_id, exercise_code):
    data = request.get_json(silent=True) or {}
    date_str = data.get('date')
    period = data.get('period') 

    date_error = validate_date(date_str)
    if date_error:
        return date_error

    if period and period not in ["morning", "afternoon", "evening"]:
        return jsonify({"error": "Invalid period"}), 400

    if exercise_code not in exercises:
        return jsonify({"error": "Exercise not found"}), 404

    periods_to_check = [period] if period else ["morning", "afternoon", "evening"]
    selected_period = None
    
    for p in periods_to_check:
        slot_taken = any(s for s in schedule_list if s['exercise-code'] == exercise_code and s['date'] == date_str and s['period'] == p)
        if not slot_taken:
            user_conflict = any(s for s in schedule_list if s['user-id'] == user_id and s['date'] == date_str and s['period'] == p)
            if not user_conflict:
                selected_period = p
                break
    
    # If no period is available, the server returns 422 with availability = False and appt-id = 0
    if not selected_period:
        return jsonify({
            "appt-id": 0,
            "user-id": user_id, 
            "availability": False, 
            "exercise-code": exercise_code, 
            "date": date_str, 
            "period": period if period else ""
        }), 422

    current_count = sum(1 for s in schedule_list if s['user-id'] == user_id)
    if current_count >= 3:
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

@app.route('/schedule/<int:user_id>/<exercise_code>', methods=['DELETE'])
def delete_schedule(user_id, exercise_code):
    data = request.get_json(silent=True) or {}
    date_str = data.get('date')
    period = data.get('period')
    
    if not date_str or not period:
        return jsonify({"error": "Malformed input"}), 400

    appt = next((s for s in schedule_list if s['user-id'] == user_id and s['exercise-code'] == exercise_code and s['date'] == date_str and s['period'] == period), None)
    
    if not appt:
        return jsonify({"error": "Appointment not found"}), 422
        
    schedule_list.remove(appt)
    return '', 204



# --- 6. /schedule/{user-id}/{appt-id} ---
@app.route('/schedule/<int:user_id>/<int:appt_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_appointment(user_id, appt_id):
    existing_appt = next((s for s in schedule_list if s['user-id'] == user_id and s['appt-id'] == appt_id), None)
    
    if not existing_appt:
        return jsonify({"error": "Appointment not found"}), 404

    if request.method == 'GET':
        return jsonify(existing_appt), 200

    if request.method == 'DELETE':
        schedule_list.remove(existing_appt)
        return '', 204

    if request.method == 'PUT':
        data = request.get_json(silent=True) or {}
        date_str = data.get('date')
        period = data.get('period')
        
        date_error = validate_date(date_str)
        if date_error:
            return date_error

        if period and period not in ["morning", "afternoon", "evening"]:
            return jsonify({"error": "Invalid period"}), 400

        exercise_code = existing_appt['exercise-code']
        periods_to_check = [period] if period else ["morning", "afternoon", "evening"]
        selected_period = None

        for p in periods_to_check:
            # Check if someone else is in this slot (comparing BOTH user-id and appt-id to isolate the target appt)
            slot_taken = any(
                s for s in schedule_list 
                if s['exercise-code'] == exercise_code 
                and s['date'] == date_str 
                and s['period'] == p 
                and not (s['user-id'] == user_id and s['appt-id'] == appt_id)
            )
            
            if not slot_taken:
                # Check if this user is scheduled for another exercise at this time
                user_conflict = any(
                    s for s in schedule_list 
                    if s['user-id'] == user_id 
                    and s['date'] == date_str 
                    and s['period'] == p 
                    and not (s['user-id'] == user_id and s['appt-id'] == appt_id)
                )
                if not user_conflict:
                    selected_period = p
                    break

        if not selected_period:
            # Return 422 if slot is occupied or unavailable
            return jsonify({
                "error": "Requested replacement slot is already occupied or unavailable"
            }), 422

        # Update fields while preserving the appt-id
        existing_appt['date'] = date_str
        existing_appt['period'] = selected_period
        
        return jsonify(existing_appt), 200


#7. /schedule
@app.route('/schedule', methods=['GET'])
def get_all_schedules():
    if not is_admin():
        return jsonify({"error": "Unauthorized"}), 401
        
    ex_code_filter = request.args.get('exercise-code')
    
    for key in request.args:
        if key != 'exercise-code':
            return jsonify({"error": f"Bad Request: unknown query string {key}"}), 400

    results = schedule_list
    if ex_code_filter:
        results = [s for s in results if s['exercise-code'] == ex_code_filter]
        
    formatted_results = [
        {
            "exercise-code": r["exercise-code"],
            "appt-id": r["appt-id"],
            "date": r["date"],
            "period": r["period"],
            "user-id": r["user-id"]
        } for r in results
    ]
    
    return jsonify(formatted_results), 200


if __name__ == '__main__':
    # Listen on 0.0.0.0 on port 5001
    app.run(host='0.0.0.0', port=5001, debug=False)