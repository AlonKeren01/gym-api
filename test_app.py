import re

import pytest
import requests
from unittest.mock import patch
import app as gym_app  # Import your app module to access its global state

# --- Fixtures ---

@pytest.fixture
def client():
    """Sets up the Flask test client."""
    gym_app.app.config['TESTING'] = True
    with gym_app.app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def reset_state():
    """Wipes in-memory state before each test to start from scratch[cite: 30]."""
    gym_app.users.clear()
    gym_app.users[0] = {"name": "admin", "user-id": 0, "API-key": "ytngh52@gb&&ubt8"} #[cite: 32]
    gym_app.exercises.clear()
    gym_app.schedule_list.clear()
    gym_app.next_user_id = 1


# --- Shared helpers (used by the extended tests at the bottom of the file) ---

ADMIN_KEY = "ytngh52@gb&&ubt8"
ADMIN_H = {"X-Api-Key": ADMIN_KEY}
GOOD_DATE = "20/11/2026"


def add_user(uid, key=None):
    """Inject a regular user straight into the in-memory state. Returns its auth header."""
    key = key or f"key{uid}"
    gym_app.users[uid] = {"name": f"user{uid}", "user-id": uid, "API-key": key}
    return {"X-Api-Key": key}


def hdr(uid):
    """Auth header for an already-injected user."""
    return {"X-Api-Key": gym_app.users[uid]["API-key"]}


def add_exercise(code, name=None, type_="strength", muscle="chest", difficulty="intermediate"):
    """Inject an exercise straight into the in-memory state."""
    gym_app.exercises[code] = {
        "name": name or code,
        "type": type_,
        "muscle-group": muscle,
        "difficulty": difficulty,
        "exercise-code": code,
    }


def ninja_item(name, type_="strength", muscle="chest", difficulty="intermediate"):
    """One API-Ninjas record. Note Ninja calls the field 'muscle'; our API calls it 'muscle-group'."""
    return {"name": name, "type": type_, "muscle": muscle, "difficulty": difficulty}


def mock_ninja(mock_get, results, status=200):
    """Configure the patched requests.get to behave like API-Ninjas."""
    mock_get.return_value.status_code = status
    mock_get.return_value.json.return_value = results


def book(client, uid, code, date=GOOD_DATE, period="morning"):
    """POST /schedule/{uid}/{code} using that user's own key. period=None omits the field."""
    body = {"date": date}
    if period is not None:
        body["period"] = period
    return client.post(f"/schedule/{uid}/{code}", json=body, headers=hdr(uid))


@pytest.fixture
def world():
    """Users 1 and 2 plus exercises inc1, ben1 and run1, so a test can start booking right away."""
    add_user(1)
    add_user(2)
    add_exercise("inc1", "Incline Hammer Curls", muscle="biceps", difficulty="beginner")
    add_exercise("ben1", "Bench Press", muscle="chest", difficulty="intermediate")
    add_exercise("run1", "Running", type_="cardio", muscle="quadriceps", difficulty="beginner")


# --- Tests ---

def test_register_user(client):
    """Tests POST /register[cite: 34]."""
    res = client.post('/register', json={"name": "alon"})
    assert res.status_code == 201 #[cite: 33]
    
    data = res.get_json()
    assert data["name"] == "alon"
    assert data["user-id"] == 1
    assert "API-key" in data #[cite: 34]


def test_validate_user(client):
    """Tests POST /validate/{user-id}[cite: 35]."""
    # 1. Register a user
    reg_data = client.post('/register', json={"name": "test_user"}).get_json()
    uid = reg_data["user-id"]
    api_key = reg_data["API-key"]
    
    # 2. Validate regular user (Privileged should be False)[cite: 35]
    res_regular = client.post(f'/validate/{uid}', json={"API-key": api_key})
    assert res_regular.status_code == 200
    assert res_regular.get_json()["privileged"] is False #[cite: 35]
    
    # 3. Validate admin user (Privileged should be True)[cite: 35]
    res_admin = client.post('/validate/0', json={"API-key": "ytngh52@gb&&ubt8"})
    assert res_admin.status_code == 200
    assert res_admin.get_json()["privileged"] is True #[cite: 35]


@patch('app.requests.get')
def test_add_exercise_mocked(mock_get, client):
    """Tests POST /exercises using a mocked API Ninjas response[cite: 36, 38]."""
    # Mock the external service response
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = [{
        "name": "Bench Press",
        "type": "strength",
        "muscle": "chest",
        "difficulty": "intermediate"
    }]
    
    # Admin requests to add the exercise[cite: 36]
    res = client.post('/exercises', 
                      json={"name": "Bench Press"},
                      headers={"X-Api-Key": "ytngh52@gb&&ubt8"})
    
    assert res.status_code == 201 #[cite: 33]
    data = res.get_json()
    # Verifies the code generation and muscle-group mapping[cite: 36, 38]
    assert data["exercise-code"] == "ben1" 
    assert data["muscle-group"] == "chest"


def test_scheduling_v2_lifecycle(client):
    """Tests the full v2 scheduling flow: POST, PUT, and DELETE with appt-id[cite: 44, 45]."""
    # 1. Setup: Manually inject a user and an exercise into the state
    gym_app.users[1] = {"name": "test_user", "user-id": 1, "API-key": "test_key"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # 2. CREATE (POST /schedule/{user-id}/{exercise-code})[cite: 44]
    res_post = client.post('/schedule/1/inc1',
                           json={"date": "20/11/2026", "period": "morning"},
                           headers={"X-Api-Key": "test_key"})
    
    assert res_post.status_code == 201 #[cite: 33]
    post_data = res_post.get_json()
    assert post_data["appt-id"] == 1 #[cite: 44]
    assert post_data["availability"] is True #[cite: 44]
    
    # 3. UPDATE (PUT /schedule/{user-id}/{appt-id})[cite: 45]
    res_put = client.put('/schedule/1/1',
                         json={"date": "21/11/2026", "period": "afternoon"},
                         headers={"X-Api-Key": "test_key"})
                         
    assert res_put.status_code == 200
    put_data = res_put.get_json()
    # The appt-id must remain the same[cite: 43]
    assert put_data["appt-id"] == 1 
    assert put_data["date"] == "21/11/2026"
    assert put_data["period"] == "afternoon"
    
    # 4. DELETE (DELETE /schedule/{user-id}/{appt-id})[cite: 45]
    res_del = client.delete('/schedule/1/1', headers={"X-Api-Key": "test_key"})
    assert res_del.status_code == 204 #[cite: 33]
    
    # 5. VERIFY DELETION (GET /schedule/{user-id}/{appt-id})[cite: 45]
    res_get = client.get('/schedule/1/1', headers={"X-Api-Key": "test_key"})
    assert res_get.status_code == 404 #[cite: 33]

def test_register_twice(client):
    """A user can only register once. If he registers twice, a 422 exception is raised[cite: 34]."""
    client.post('/register', json={"name": "test_user"})
    res = client.post('/register', json={"name": "test_user"})
    
    assert res.status_code == 422 #[cite: 33, 34]


def test_exercises_query_strings(client):
    """Tests GET /exercises with valid and nonsensical query strings[cite: 36, 47]."""
    add_user(1, "dummy_key")
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    gym_app.exercises["ben1"] = {"name": "Bench", "type": "strength", "muscle-group": "chest", "difficulty": "beginner", "exercise-code": "ben1"}
    
    # Valid filter should return matching records[cite: 36]
    res_valid = client.get('/exercises?difficulty=expert', headers={"X-Api-Key": "dummy_key"}) 
    assert res_valid.status_code == 200
    assert len(res_valid.get_json()) == 1
    
    # Nonsensical query string must return 400 Bad Request[cite: 47]
    res_bad = client.get('/exercises?previous-owner=Lilly', headers={"X-Api-Key": "dummy_key"})
    assert res_bad.status_code == 400 #[cite: 47]


def test_schedule_date_range(client):
    """All requests must be for a date between November 15, 2026 and December 15, 2026[cite: 43]."""
    gym_app.users[1] = {"name": "test_user", "user-id": 1, "API-key": "test_key"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # Out of range date (Nov 14) receives a 422 response[cite: 43]
    res = client.post('/schedule/1/inc1',
                      json={"date": "14/11/2026", "period": "morning"},
                      headers={"X-Api-Key": "test_key"})
    assert res.status_code == 422 #[cite: 33, 43]


def test_schedule_slot_taken(client):
    """If a user attempts to POST a new appointment for a slot already taken, then 422 is returned with availability set to False and appt-id = 0[cite: 42, 44]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.users[2] = {"name": "user2", "user-id": 2, "API-key": "key2"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # User 1 successfully takes the morning slot
    client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    
    # User 2 tries to take the exact same slot for the same exercise
    res = client.post('/schedule/2/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key2"})
    
    assert res.status_code == 422 #[cite: 33, 42]
    data = res.get_json()
    assert data["availability"] is False #[cite: 42, 44]
    assert data["appt-id"] == 0 #[cite: 44]


def test_max_three_appointments(client):
    """A user cannot have more than three active appointments at any given time[cite: 42]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # Add 3 active appointments successfully
    client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    client.post('/schedule/1/inc1', json={"date": "21/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    client.post('/schedule/1/inc1', json={"date": "22/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    
    # 4th request must fail with 422[cite: 42]
    res = client.post('/schedule/1/inc1', json={"date": "23/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    assert res.status_code == 422 #[cite: 33, 42]


def test_admin_global_schedule(client):
    """The GET request to /schedule is only allowed by the admin[cite: 46]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    
    # Regular user attempting access
    res_regular = client.get('/schedule', headers={"X-Api-Key": "key1"})
    assert res_regular.status_code == 401 #[cite: 46]
    
    # Admin attempting access
    res_admin = client.get('/schedule', headers={"X-Api-Key": "ytngh52@gb&&ubt8"})
    assert res_admin.status_code == 200 #[cite: 46]

def test_schedule_optional_period(client):
    """If no period is specified, the server can return any available period on that date[cite: 44]."""
    gym_app.users[1] = {"name": "test_user", "user-id": 1, "API-key": "test_key"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # POST without a 'period' parameter[cite: 44]
    res = client.post('/schedule/1/inc1',
                      json={"date": "20/11/2026"},
                      headers={"X-Api-Key": "test_key"})
                      
    assert res.status_code == 201 #[cite: 33]
    data = res.get_json()
    assert data["availability"] is True #[cite: 44]
    assert data["period"] in ["morning", "afternoon", "evening"] #[cite: 44]


def test_two_different_exercises_same_time(client):
    """A user cannot schedule two different exercises for the same date and period. The second request must fail with 422[cite: 42]."""
    gym_app.users[1] = {"name": "test_user", "user-id": 1, "API-key": "test_key"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    gym_app.exercises["ben1"] = {"name": "Bench", "type": "strength", "muscle-group": "chest", "difficulty": "beginner", "exercise-code": "ben1"}
    
    # Schedule first exercise
    client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "test_key"})
    
    # Attempt to schedule second exercise at the exact same time
    res = client.post('/schedule/1/ben1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "test_key"})
    
    assert res.status_code == 422 #[cite: 33, 42]


def test_put_replacement_slot_occupied(client):
    """If the requested replacement slot is already occupied, the request returns 422 and the original appointment and appt-id remain unchanged[cite: 45]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.users[2] = {"name": "user2", "user-id": 2, "API-key": "key2"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # User 1 books Nov 20 morning
    res_post1 = client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    appt_id1 = res_post1.get_json()["appt-id"]
    
    # User 2 books Nov 21 morning
    res_post2 = client.post('/schedule/2/inc1', json={"date": "21/11/2026", "period": "morning"}, headers={"X-Api-Key": "key2"})
    appt_id2 = res_post2.get_json()["appt-id"]
    
    # User 1 tries to change their appointment to Nov 21 morning (which User 2 occupies)
    res_put = client.put(f'/schedule/1/{appt_id1}', json={"date": "21/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    
    assert res_put.status_code == 422 #[cite: 33, 45]
    
    # Verify original appointment remains unchanged[cite: 45]
    res_verify = client.get(f'/schedule/1/{appt_id1}', headers={"X-Api-Key": "key1"})
    verify_data = res_verify.get_json()
    assert verify_data["date"] == "20/11/2026" #[cite: 45]


def test_strict_user_authorization(client):
    """All requests for a specific user-id must use that user-id's API-key[cite: 32]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.users[2] = {"name": "user2", "user-id": 2, "API-key": "key2"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # User 1 attempts to schedule an appointment for User 2 using User 1's key
    res = client.post('/schedule/2/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    
    # Should be rejected because the API-key does not match the URL's user-id[cite: 32]
    assert res.status_code == 401 


def test_delete_exercise_admin_only(client):
    """The DELETE requests for /exercises/{exercise-code} is only allowed by the admin[cite: 37]. A successful DELETE returns 204[cite: 33]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    
    # Regular user attempts deletion
    res_user = client.delete('/exercises/inc1', headers={"X-Api-Key": "key1"})
    assert res_user.status_code == 401 #[cite: 37]
    
    # Admin attempts deletion
    res_admin = client.delete('/exercises/inc1', headers={"X-Api-Key": "ytngh52@gb&&ubt8"})
    assert res_admin.status_code == 204 #[cite: 33, 37]
    assert "inc1" not in gym_app.exercises


def test_validate_incorrect_user_or_key(client):
    """It returns the same 401 unauthorized code for incorrect user-id or incorrect API-key (does not return 404)[cite: 35]."""
    # 1. Non-existent user-id with random key
    res1 = client.post('/validate/9999', json={"API-key": "some_random_key"})
    assert res1.status_code == 401 #[cite: 35]

    # 2. Existing user with wrong key
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "correct_key"}
    res2 = client.post('/validate/1', json={"API-key": "wrong_key"})
    assert res2.status_code == 401 #[cite: 35]


def test_exercise_code_collisions_and_short_names(client):
    """Tests code generation logic for duplicate prefixes (ben1, ben2) and names shorter than 3 letters[cite: 36]."""
    # Short exercise name (< 3 letters)
    code_short = gym_app.generate_exercise_code("Ab")
    assert len(code_short) == 4
    assert code_short.startswith("abx")  # Padded to 3 characters + 1 digit[cite: 36]

    # Standard names causing collision
    gym_app.exercises["ben1"] = {"name": "Bench Press"}
    code_collision = gym_app.generate_exercise_code("Bench Fly")
    assert code_collision == "ben2" #[cite: 36]


@patch('app.requests.get')
def test_api_ninjas_502_error(mock_get, client):
    """Returns 502 for any other API Ninjas error (e.g. server down or request exception)[cite: 39]."""
    # Simulate API Ninjas returning HTTP 500 Internal Error
    mock_get.return_value.status_code = 500

    res = client.post('/exercises',
                      json={"name": "Squat"},
                      headers={"X-Api-Key": "ytngh52@gb&&ubt8"})
    
    assert res.status_code == 502 #[cite: 39]


def test_schedule_boundary_dates(client):
    """Tests exact inclusive boundary dates: Nov 15, 2026 and Dec 15, 2026[cite: 43]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}

    # Start boundary: Nov 15, 2026
    res_start = client.post('/schedule/1/inc1', json={"date": "15/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    assert res_start.status_code == 201 #[cite: 33, 43]

    # End boundary: Dec 15, 2026
    res_end = client.post('/schedule/1/inc1', json={"date": "15/12/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    assert res_end.status_code == 201 #[cite: 33, 43]


def test_schedule_auto_period_fallback_and_exhaustion(client):
    """If no period is specified, assigns an available slot. If all slots are taken, returns 422 with appt-id=0[cite: 44]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.users[2] = {"name": "user2", "user-id": 2, "API-key": "key2"}
    gym_app.users[3] = {"name": "user3", "user-id": 3, "API-key": "key3"}
    gym_app.users[4] = {"name": "user4", "user-id": 4, "API-key": "key4"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}

    # Book morning, afternoon, and evening slots for inc1 on Nov 20
    client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    client.post('/schedule/2/inc1', json={"date": "20/11/2026", "period": "afternoon"}, headers={"X-Api-Key": "key2"})
    client.post('/schedule/3/inc1', json={"date": "20/11/2026", "period": "evening"}, headers={"X-Api-Key": "key3"})

    # User 4 requests an appointment on Nov 20 without specifying a period
    res = client.post('/schedule/4/inc1', json={"date": "20/11/2026"}, headers={"X-Api-Key": "key4"})

    assert res.status_code == 422 #[cite: 33, 44]
    data = res.get_json()
    assert data["availability"] is False #[cite: 44]
    assert data["appt-id"] == 0 #[cite: 44]


def test_admin_schedule_query_filter(client):
    """Tests GET /schedule?exercise-code=<value> filtering for admin[cite: 46]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}
    gym_app.exercises["ben1"] = {"name": "Bench", "type": "strength", "muscle-group": "chest", "difficulty": "beginner", "exercise-code": "ben1"}

    client.post('/schedule/1/inc1', json={"date": "20/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})
    client.post('/schedule/1/ben1', json={"date": "21/11/2026", "period": "morning"}, headers={"X-Api-Key": "key1"})

    # Filter master schedule by exercise-code=inc1[cite: 46]
    res = client.get('/schedule?exercise-code=inc1', headers={"X-Api-Key": "ytngh52@gb&&ubt8"})
    
    assert res.status_code == 200 #[cite: 46]
    results = res.get_json()
    assert len(results) == 1
    assert results[0]["exercise-code"] == "inc1" #[cite: 46]


# --- 1. /register Edge Cases ---

def test_register_malformed_input(client):
    """Returns 400 if input parameters are malformed or missing[cite: 33, 34]."""
    # 1. Missing 'name' field
    res1 = client.post('/register', json={})
    assert res1.status_code == 400 #[cite: 33]

    # 2. Non-string 'name' field
    res2 = client.post('/register', json={"name": 12345})
    assert res2.status_code == 400 #[cite: 33]


# --- 2. /validate/{user-id} Edge Cases ---

def test_validate_malformed_body(client):
    """Returns 400 if the API-key parameter is missing from the JSON body[cite: 33, 35]."""
    res = client.post('/validate/1', json={})
    assert res.status_code == 400 #[cite: 33]


# --- 3. /exercises & API Ninjas Edge Cases ---

def test_add_exercise_unauthorized_user(client):
    """The POST request for /exercises is only allowed by the admin[cite: 36]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}

    res = client.post('/exercises',
                      json={"name": "Incline hammer curls"},
                      headers={"X-Api-Key": "key1"})
    assert res.status_code == 401 #[cite: 32, 36]


@patch('app.requests.get')
def test_add_exercise_no_exact_name_match(mock_get, client):
    """API-Ninjas may return partial matches. If no exact match exists (ignoring case), return 422[cite: 39]."""
    mock_get.return_value.status_code = 200
    # API Ninjas returns 'Barbell Bench Press', but requested name is 'Bench Press'
    mock_get.return_value.json.return_value = [{
        "name": "Barbell Bench Press",
        "type": "strength",
        "muscle": "chest",
        "difficulty": "intermediate"
    }]

    res = client.post('/exercises',
                      json={"name": "Bench Press"},
                      headers={"X-Api-Key": "ytngh52@gb&&ubt8"})

    assert res.status_code == 422 #[cite: 39]


# --- 4. /exercises/{exercise-code} Edge Cases ---

def test_get_exercise_by_code_details_and_not_found(client):
    """GET /exercises/{exercise-code} returns name, type, muscle-group, and difficulty[cite: 37]. Returns 404 if not found[cite: 33]."""
    add_user(1, "dummy_key")
    gym_app.exercises["inc1"] = {
        "name": "Incline hammer curls",
        "type": "strength",
        "muscle-group": "biceps",
        "difficulty": "beginner",
        "exercise-code": "inc1"
    }

    # 1. Existing exercise returns 200 with required fields[cite: 37]
    res_ok = client.get('/exercises/inc1', headers={"X-Api-Key": "dummy_key"})
    assert res_ok.status_code == 200
    data = res_ok.get_json()
    assert data == {
        "name": "Incline hammer curls",
        "type": "strength",
        "muscle-group": "biceps",
        "difficulty": "beginner"
    } #[cite: 37]

    # 2. Non-existent exercise code returns 404[cite: 33]
    res_404 = client.get('/exercises/nonexistent', headers={"X-Api-Key": "dummy_key"})
    assert res_404.status_code == 404 #[cite: 33]


# --- 5 & 6. /schedule Edge Cases ---

def test_schedule_post_non_existent_exercise(client):
    """Returns 404 if attempting to schedule an exercise code that does not exist[cite: 33]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}

    res = client.post('/schedule/1/fakecode',
                      json={"date": "20/11/2026", "period": "morning"},
                      headers={"X-Api-Key": "key1"})
    assert res.status_code == 404 #[cite: 33]


def test_schedule_invalid_period_string(client):
    """Returns 400 if period is not 'morning', 'afternoon', or 'evening'[cite: 33, 44]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}

    res = client.post('/schedule/1/inc1',
                      json={"date": "20/11/2026", "period": "midnight"},
                      headers={"X-Api-Key": "key1"})
    assert res.status_code == 400 #[cite: 33]


def test_schedule_get_and_delete_non_existent_appt(client):
    """GET and DELETE on non-existent appt-id return 404[cite: 33, 45]."""
    gym_app.users[1] = {"name": "user1", "user-id": 1, "API-key": "key1"}

    # GET non-existent appt-id
    res_get = client.get('/schedule/1/999', headers={"X-Api-Key": "key1"})
    assert res_get.status_code == 404 #[cite: 33, 45]

    # DELETE non-existent appt-id
    res_del = client.delete('/schedule/1/999', headers={"X-Api-Key": "key1"})
    assert res_del.status_code == 404 #[cite: 33, 45]


# --- 7. General API Guidelines & Nonsensical Query Strings ---

def test_missing_x_api_key_header(client):
    """All API requests (except POST /register and POST /validate) require X-Api-Key header[cite: 32]. Returns 401 if missing (lecture 2: 401 = missing or invalid credentials)."""
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}

    # Missing X-Api-Key header on GET /exercises
    res = client.get('/exercises')
    assert res.status_code == 401  # RED until fixed: app.py currently returns 400


def test_admin_schedule_empty_match_query_string(client):
    """When the query string produces no matches, return an empty array with code 200[cite: 47]."""
    # Admin requests schedule for an exercise code that has no bookings
    res = client.get('/schedule?exercise-code=unused_code', headers={"X-Api-Key": "ytngh52@gb&&ubt8"})

    assert res.status_code == 200 #[cite: 47]
    assert res.get_json() == [] #[cite: 47]


# =====================================================================
# EXTENDED COVERAGE
#
# Written against the assignment PDF and the lecture 2 slides
# ("Common Response Status Codes", "Return code conventions",
#  "JSON format for error messages").
#
# Tests marked "RED until fixed" describe a gap in app.py that was found
# by reading the code and by running it in Docker. They are EXPECTED to
# fail until the matching fix lands; every other test locks in behaviour
# that is already correct so the fixes cannot break it.
# =====================================================================


# --- Authentication (X-Api-Key) ---

@pytest.mark.parametrize("method,path,body", [
    ("GET", "/register", None),
    ("GET", "/exercises", None),
    ("GET", "/exercises/inc1", None),
    ("POST", "/exercises", {"name": "Bench Press"}),
    ("DELETE", "/exercises/inc1", None),
    ("GET", "/schedule", None),
    ("POST", "/schedule/1/inc1", {"date": GOOD_DATE, "period": "morning"}),
    ("GET", "/schedule/1/1", None),
    ("PUT", "/schedule/1/1", {"date": GOOD_DATE, "period": "morning"}),
    ("DELETE", "/schedule/1/1", None),
])
def test_missing_api_key_is_401_everywhere(client, world, method, path, body):
    """RED until fixed (except GET /register): a missing key must be 401, not 400."""
    res = client.open(path, method=method, json=body)
    assert res.status_code == 401


@pytest.mark.parametrize("method,path", [
    ("GET", "/exercises"),
    ("GET", "/exercises/inc1"),
    ("GET", "/schedule"),
    ("POST", "/exercises"),
    ("DELETE", "/exercises/inc1"),
])
def test_unregistered_api_key_is_401(client, world, method, path):
    """RED until fixed for GET /exercises and GET /exercises/{code}: any made-up key is accepted today."""
    body = {"name": "Bench Press"} if method == "POST" else None
    res = client.open(path, method=method, json=body, headers={"X-Api-Key": "not-a-registered-key"})
    assert res.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/register", None),
    ("POST", "/exercises", {"name": "Bench Press"}),
    ("DELETE", "/exercises/inc1", None),
    ("GET", "/schedule", None),
])
def test_regular_user_key_on_admin_only_endpoints_is_401(client, world, method, path, body):
    res = client.open(path, method=method, json=body, headers=hdr(1))
    assert res.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/schedule/1/inc1", {"date": GOOD_DATE, "period": "morning"}),
    ("GET", "/schedule/1/1", None),
    ("DELETE", "/schedule/1/1", None),
])
def test_admin_key_cannot_act_on_a_users_schedule_urls(client, world, method, path, body):
    """'All requests for a specific user-id must use that user-id's API-key' - even the admin's."""
    res = client.open(path, method=method, json=body, headers=ADMIN_H)
    assert res.status_code == 401


@pytest.mark.parametrize("method,path", [
    ("POST", "/schedule/99/inc1"),
    ("GET", "/schedule/99/1"),
    ("DELETE", "/schedule/99/1"),
])
def test_unknown_user_id_in_path_is_401(client, world, method, path):
    body = {"date": GOOD_DATE, "period": "morning"} if method == "POST" else None
    res = client.open(path, method=method, json=body, headers=hdr(1))
    assert res.status_code == 401


def test_registered_users_key_is_accepted_on_non_user_urls(client, world):
    assert client.get("/exercises", headers=hdr(1)).status_code == 200
    assert client.get("/exercises/inc1", headers=hdr(2)).status_code == 200


# --- Content-Type (lecture 2: 415 "Expected application/json media type") ---

@pytest.mark.parametrize("path,headers", [
    ("/register", {}),
    ("/validate/1", {}),
    ("/exercises", ADMIN_H),
    ("/schedule/1/inc1", {"X-Api-Key": "key1"}),
])
def test_post_with_non_json_content_type_is_415(client, world, path, headers):
    """RED until fixed: today a non-JSON body is silently treated as an empty one (400/422)."""
    res = client.post(path, data='{"name": "x", "date": "20/11/2026"}',
                      content_type="text/plain", headers=headers)
    assert res.status_code == 415
    assert res.get_json() == {"error": "Expected application/json media type"}


def test_put_with_non_json_content_type_is_415(client, world):
    """RED until fixed."""
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    res = client.put(f"/schedule/1/{appt_id}", data='{"date": "21/11/2026"}',
                     content_type="text/plain", headers=hdr(1))
    assert res.status_code == 415


def test_get_and_delete_do_not_require_a_json_content_type(client, world):
    """Guard so the 415 fix is not applied to requests that have no body."""
    assert client.get("/exercises", content_type="text/plain", headers=hdr(1)).status_code == 200
    assert client.delete("/exercises/inc1", content_type="text/plain", headers=ADMIN_H).status_code == 204


def test_register_with_broken_json_is_400(client):
    res = client.post("/register", data="{this is not json", content_type="application/json")
    assert res.status_code == 400


def test_schedule_post_with_broken_json_is_400(client, world):
    """RED until fixed: today a broken body is read as {} and reported as a 422 date error."""
    res = client.post("/schedule/1/inc1", data="{this is not json",
                      content_type="application/json", headers=hdr(1))
    assert res.status_code == 400


@pytest.mark.parametrize("path,headers", [
    ("/register", {}),
    ("/validate/1", {}),
    ("/exercises", ADMIN_H),
    ("/schedule/1/inc1", {"X-Api-Key": "key1"}),
])
def test_json_body_that_is_not_an_object_is_400(client, world, path, headers):
    """RED until fixed: a JSON list crashes with AttributeError ('list' has no .get)."""
    res = client.post(path, json=[1, 2, 3], headers=headers)
    assert res.status_code == 400


# --- Error body format (lecture 2: "JSON format for error messages") ---

def test_400_body_matches_lecture_format(client):
    """RED until fixed: app.py says 'Malformed input'; the lecture says 'Malformed data'."""
    res = client.post("/register", json={})
    assert res.status_code == 400
    assert res.get_json() == {"error": "Malformed data"}


@pytest.mark.parametrize("path", ["/exercises/nonexistent", "/schedule/1/999"])
def test_404_body_matches_lecture_format(client, world, path):
    """RED until fixed: app.py says 'Exercise not found' / 'Appointment not found'."""
    res = client.get(path, headers=hdr(1))
    assert res.status_code == 404
    assert res.get_json() == {"error": "Not found"}


def test_unknown_route_returns_json_404(client, world):
    """RED until fixed: Flask's default HTML 404 page is returned today."""
    res = client.get("/nothing", headers=hdr(1))
    assert res.status_code == 404
    assert res.is_json
    assert res.get_json() == {"error": "Not found"}


def test_wrong_method_on_existing_route_returns_json(client, world):
    """RED until fixed: Flask's default HTML 405 page is returned today."""
    res = client.delete("/register", headers=hdr(1))
    assert res.status_code in (404, 405)
    assert res.is_json
    assert "error" in res.get_json()


def test_unexpected_exception_returns_json_500(client, world, monkeypatch):
    """RED until fixed: no 500 handler, so Flask (and the debugger) answer with HTML."""
    def boom(_):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(gym_app, "validate_date", boom)
    monkeypatch.setitem(gym_app.app.config, "PROPAGATE_EXCEPTIONS", False)
    res = book(client, 1, "inc1")
    assert res.status_code == 500
    assert res.is_json
    assert res.get_json() == {"error": "Internal Server error"}


# --- /register ---

def test_register_many_users_get_unique_ids_names_and_keys(client):
    results = [client.post("/register", json={"name": f"person{i}"}) for i in range(6)]
    assert all(r.status_code == 201 for r in results)
    bodies = [r.get_json() for r in results]
    assert [b["user-id"] for b in bodies] == [1, 2, 3, 4, 5, 6]
    keys = [b["API-key"] for b in bodies]
    assert len(set(keys)) == 6
    assert ADMIN_KEY not in keys
    assert all(isinstance(k, str) and len(k) == 16 for k in keys)


def test_register_response_has_exactly_name_id_and_key(client):
    body = client.post("/register", json={"name": "alon"}).get_json()
    assert set(body) == {"name", "user-id", "API-key"}
    assert body["name"] == "alon"
    assert isinstance(body["user-id"], int)
    assert isinstance(body["API-key"], str)


def test_cannot_register_the_admin_name(client):
    assert client.post("/register", json={"name": "admin"}).status_code == 422


@pytest.mark.parametrize("body", [{"nme": "alon"}, {"name": ""}, {"name": None}, {"name": ["a"]}, {"name": 5}])
def test_register_malformed_bodies_are_400(client, body):
    assert client.post("/register", json=body).status_code == 400


def test_failed_register_does_not_consume_a_user_id(client):
    client.post("/register", json={"name": "alon"})
    client.post("/register", json={"name": "alon"})  # 422
    second = client.post("/register", json={"name": "dana"}).get_json()
    assert second["user-id"] == 2


def test_register_get_lists_every_user_including_admin(client, world):
    res = client.get("/register", headers=ADMIN_H)
    assert res.status_code == 200
    users = res.get_json()
    assert isinstance(users, list)
    assert {u["name"] for u in users} == {"admin", "user1", "user2"}
    for u in users:
        assert set(u) == {"name", "user-id", "API-key"}


def test_a_freshly_registered_key_works_immediately(client):
    key = client.post("/register", json={"name": "alon"}).get_json()["API-key"]
    assert client.get("/exercises", headers={"X-Api-Key": key}).status_code == 200


# --- /validate/{user-id} ---

def test_validate_with_another_users_key_is_401(client, world):
    res = client.post("/validate/1", json={"API-key": gym_app.users[2]["API-key"]})
    assert res.status_code == 401


def test_validate_admin_id_with_wrong_key_and_regular_id_with_admin_key_are_401(client, world):
    assert client.post("/validate/0", json={"API-key": gym_app.users[1]["API-key"]}).status_code == 401
    assert client.post("/validate/1", json={"API-key": ADMIN_KEY}).status_code == 401


def test_validate_does_not_need_the_api_key_header(client, world):
    res = client.post("/validate/1", json={"API-key": gym_app.users[1]["API-key"]})
    assert res.status_code == 200
    assert res.get_json() == {"privileged": False}


def test_validate_wrong_field_name_is_400(client, world):
    assert client.post("/validate/1", json={"key": "key1"}).status_code == 400


def test_validate_unknown_user_and_wrong_key_return_the_same_body(client, world):
    """The response must not reveal whether the id or the key was wrong."""
    unknown_user = client.post("/validate/99", json={"API-key": "whatever"})
    wrong_key = client.post("/validate/1", json={"API-key": "whatever"})
    assert unknown_user.status_code == wrong_key.status_code == 401
    assert unknown_user.get_json() == wrong_key.get_json()


# --- POST /exercises and the API-Ninjas integration (always mocked) ---

@patch("app.requests.get")
def test_exercise_name_match_ignores_case(mock_get, client):
    mock_ninja(mock_get, [ninja_item("Incline Hammer Curls", muscle="biceps", difficulty="beginner")])
    res = client.post("/exercises", json={"name": "incline hammer curls"}, headers=ADMIN_H)
    assert res.status_code == 201
    body = res.get_json()
    assert body["exercise-code"] == "inc1"
    assert body["muscle-group"] == "biceps"
    assert body["difficulty"] == "beginner"
    assert body["type"] == "strength"


@patch("app.requests.get")
def test_exact_match_is_picked_among_several_ninja_results(mock_get, client):
    mock_ninja(mock_get, [
        ninja_item("Barbell Bench Press", muscle="triceps"),
        ninja_item("Bench Press", muscle="chest"),
        ninja_item("Incline Bench Press", muscle="shoulders"),
    ])
    res = client.post("/exercises", json={"name": "Bench Press"}, headers=ADMIN_H)
    assert res.status_code == 201
    assert res.get_json()["muscle-group"] == "chest"
    assert res.get_json()["exercise-code"] == "ben1"


@patch("app.requests.get")
def test_ninja_returning_nothing_is_422(mock_get, client):
    mock_ninja(mock_get, [])
    res = client.post("/exercises", json={"name": "zzzqqq"}, headers=ADMIN_H)
    assert res.status_code == 422
    assert gym_app.exercises == {}


@patch("app.requests.get")
@pytest.mark.parametrize("error", [requests.exceptions.ConnectionError, requests.exceptions.Timeout])
def test_ninja_network_failures_are_502(mock_get, client, error):
    mock_get.side_effect = error
    res = client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H)
    assert res.status_code == 502
    assert gym_app.exercises == {}


@patch("app.requests.get")
@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_any_non_200_from_ninja_is_502(mock_get, client, status):
    mock_ninja(mock_get, [], status=status)
    res = client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H)
    assert res.status_code == 502
    assert gym_app.exercises == {}


@patch("app.requests.get")
def test_ninja_error_has_a_json_error_body(mock_get, client):
    """The status is 502 (assignment); the message text is our own, it only has to be JSON."""
    mock_ninja(mock_get, [], status=503)
    res = client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H)
    assert res.status_code == 502
    assert res.is_json
    assert "error" in res.get_json()


@patch("app.requests.get")
def test_ninja_key_is_sent_in_the_x_api_key_header(mock_get, client, monkeypatch):
    monkeypatch.setattr(gym_app, "API_NINJAS_KEY", "test-ninja-key")
    mock_ninja(mock_get, [ninja_item("Squat", muscle="quadriceps")])
    client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H)
    sent = mock_get.call_args.kwargs["headers"]["X-Api-Key"]
    assert sent == "test-ninja-key"
    assert sent != ADMIN_KEY  # the gym admin key must never leak to the third party


@patch("app.requests.get")
def test_ninja_request_encodes_special_characters_in_the_name(mock_get, client):
    """RED until fixed: the name is pasted into the URL by hand, so '&' splits the query string."""
    mock_ninja(mock_get, [])
    client.post("/exercises", json={"name": "Curl & Press #2"}, headers=ADMIN_H)
    args, kwargs = mock_get.call_args
    url = args[0] if args else kwargs.get("url", "")
    params = kwargs.get("params")
    assert (params is not None and params.get("name") == "Curl & Press #2") or "%26" in url


@patch("app.requests.get")
def test_ninja_request_has_a_timeout(mock_get, client):
    """RED until fixed: with no timeout one slow Ninja response can hang our server forever."""
    mock_ninja(mock_get, [])
    client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H)
    assert mock_get.call_args.kwargs.get("timeout")


@patch("app.requests.get")
@pytest.mark.parametrize("body", [{}, {"nme": "Squat"}, {"name": ""}, {"name": 123}, {"name": ["Squat"]}])
def test_post_exercise_malformed_body_is_400_and_never_calls_ninja(mock_get, client, body):
    res = client.post("/exercises", json=body, headers=ADMIN_H)
    assert res.status_code == 400
    mock_get.assert_not_called()


@patch("app.requests.get")
def test_non_admin_post_exercise_never_calls_ninja(mock_get, client, world):
    res = client.post("/exercises", json={"name": "Squat"}, headers=hdr(1))
    assert res.status_code == 401
    mock_get.assert_not_called()


@patch("app.requests.get")
def test_three_exercises_with_the_same_prefix_get_digits_1_2_3(mock_get, client):
    codes = []
    for name in ["Bench Press", "Bench Fly", "Bench Dip"]:
        mock_ninja(mock_get, [ninja_item(name)])
        res = client.post("/exercises", json={"name": name}, headers=ADMIN_H)
        assert res.status_code == 201
        codes.append(res.get_json()["exercise-code"])
    assert codes == ["ben1", "ben2", "ben3"]
    listed = client.get("/exercises", headers=ADMIN_H).get_json()
    assert sorted(e["exercise-code"] for e in listed) == ["ben1", "ben2", "ben3"]


@patch("app.requests.get")
def test_exercise_code_is_three_lowercase_letters_and_a_digit(mock_get, client):
    for name, prefix in [("Bench Press", "ben"), ("Incline Hammer Curls", "inc"),
                         ("SQUAT", "squ"), ("Deadlift", "dea")]:
        mock_ninja(mock_get, [ninja_item(name)])
        code = client.post("/exercises", json={"name": name}, headers=ADMIN_H).get_json()["exercise-code"]
        assert re.fullmatch(r"[a-z]{3}[0-9]", code), code
        assert code.startswith(prefix)


@patch("app.requests.get")
def test_created_exercise_can_be_read_back(mock_get, client, world):
    mock_ninja(mock_get, [ninja_item("Squat", muscle="quadriceps", difficulty="beginner")])
    code = client.post("/exercises", json={"name": "Squat"}, headers=ADMIN_H).get_json()["exercise-code"]
    got = client.get(f"/exercises/{code}", headers=hdr(1))
    assert got.status_code == 200
    assert got.get_json() == {"name": "Squat", "type": "strength",
                              "muscle-group": "quadriceps", "difficulty": "beginner"}


# --- GET /exercises (filters) ---

def test_get_exercises_without_filter_returns_everything_with_all_fields(client, world):
    res = client.get("/exercises", headers=hdr(1))
    assert res.status_code == 200
    items = res.get_json()
    assert sorted(i["exercise-code"] for i in items) == ["ben1", "inc1", "run1"]
    for item in items:
        assert set(item) == {"name", "type", "muscle-group", "difficulty", "exercise-code"}


@pytest.mark.parametrize("query,expected", [
    ("type=cardio", ["run1"]),
    ("type=strength", ["ben1", "inc1"]),
    ("muscle-group=chest", ["ben1"]),
    ("muscle-group=biceps", ["inc1"]),
    ("difficulty=beginner", ["inc1", "run1"]),
    ("difficulty=intermediate", ["ben1"]),
    ("type=strength&difficulty=beginner", ["inc1"]),
    ("type=strength&muscle-group=chest&difficulty=intermediate", ["ben1"]),
])
def test_get_exercises_filters(client, world, query, expected):
    res = client.get(f"/exercises?{query}", headers=hdr(1))
    assert res.status_code == 200
    assert sorted(i["exercise-code"] for i in res.get_json()) == expected


@pytest.mark.parametrize("query", ["type=stretching", "muscle-group=neck", "difficulty=expert",
                                   "type=cardio&difficulty=intermediate"])
def test_get_exercises_filter_with_no_match_is_empty_array_200(client, world, query):
    res = client.get(f"/exercises?{query}", headers=hdr(1))
    assert res.status_code == 200
    assert res.get_json() == []


@pytest.mark.parametrize("query", ["foo=bar", "name=Squat", "exercise-code=inc1", "type=cardio&foo=1", "foo=1&type=cardio"])
def test_get_exercises_unknown_query_key_is_400_even_next_to_a_valid_one(client, world, query):
    assert client.get(f"/exercises?{query}", headers=hdr(1)).status_code == 400


# --- GET / DELETE /exercises/{code} ---

def test_delete_exercise_removes_it_everywhere(client, world):
    res = client.delete("/exercises/inc1", headers=ADMIN_H)
    assert res.status_code == 204
    assert res.data == b""
    assert client.get("/exercises/inc1", headers=hdr(1)).status_code == 404
    codes = [e["exercise-code"] for e in client.get("/exercises", headers=hdr(1)).get_json()]
    assert "inc1" not in codes


def test_delete_missing_exercise_is_404_and_second_delete_is_404(client, world):
    assert client.delete("/exercises/zzz9", headers=ADMIN_H).status_code == 404
    assert client.delete("/exercises/inc1", headers=ADMIN_H).status_code == 204
    assert client.delete("/exercises/inc1", headers=ADMIN_H).status_code == 404


# --- Dates: POST and PUT /schedule ---

MALFORMED_DATES = ["2026-11-20", "abc", "20-11-2026", "20.11.2026", "", 123, 20.11, None, True,
                   ["20/11/2026"], {"d": "20/11/2026"}]
OUT_OF_RANGE_DATES = ["14/11/2026", "16/12/2026", "15/11/2025", "15/12/2027", "01/01/2026", "31/12/2026"]
IMPOSSIBLE_DATES = ["31/11/2026", "30/02/2026", "29/02/2026", "00/11/2026", "32/11/2026", "11/20/2026"]


@pytest.mark.parametrize("bad_date", MALFORMED_DATES)
def test_schedule_post_malformed_date_is_400(client, world, bad_date):
    """RED until fixed: bad formats are 422 today, and non-strings crash with a 500."""
    res = client.post("/schedule/1/inc1", json={"date": bad_date, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 400


def test_schedule_post_missing_date_is_400(client, world):
    """RED until fixed: today it is 422."""
    res = client.post("/schedule/1/inc1", json={"period": "morning"}, headers=hdr(1))
    assert res.status_code == 400


@pytest.mark.parametrize("bad_date", IMPOSSIBLE_DATES)
def test_schedule_post_impossible_calendar_date_is_400(client, world, bad_date):
    """RED until fixed. Judgement call: these are not valid DD/MM/YYYY dates at all, so we treat
    them as malformed (400) rather than as well-formed-but-not-allowed (422)."""
    res = client.post("/schedule/1/inc1", json={"date": bad_date, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 400


@pytest.mark.parametrize("date", OUT_OF_RANGE_DATES)
def test_schedule_post_date_outside_window_is_422(client, world, date):
    res = client.post("/schedule/1/inc1", json={"date": date, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 422


@pytest.mark.parametrize("date", ["15/11/2026", "16/11/2026", "30/11/2026", "01/12/2026", "14/12/2026", "15/12/2026"])
def test_schedule_post_date_inside_window_is_201(client, world, date):
    assert book(client, 1, "inc1", date=date).status_code == 201


@pytest.mark.parametrize("bad_date", MALFORMED_DATES)
def test_schedule_put_malformed_date_is_400(client, world, bad_date):
    """RED until fixed, same reasons as POST."""
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    res = client.put(f"/schedule/1/{appt_id}", json={"date": bad_date, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 400


@pytest.mark.parametrize("date", OUT_OF_RANGE_DATES)
def test_schedule_put_date_outside_window_is_422_and_changes_nothing(client, world, date):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    res = client.put(f"/schedule/1/{appt_id}", json={"date": date, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 422
    assert client.get(f"/schedule/1/{appt_id}", headers=hdr(1)).get_json()["date"] == GOOD_DATE


# --- Periods ---

@pytest.mark.parametrize("period", ["morning", "afternoon", "evening"])
def test_each_valid_period_can_be_booked(client, world, period):
    res = book(client, 1, "inc1", period=period)
    assert res.status_code == 201
    assert res.get_json()["period"] == period


@pytest.mark.parametrize("period", ["midnight", "Morning", "EVENING", "noon", 123, ["morning"]])
def test_invalid_period_is_400(client, world, period):
    assert book(client, 1, "inc1", period=period).status_code == 400


# --- POST /schedule/{user-id}/{exercise-code} ---

def test_schedule_post_response_has_exactly_the_documented_fields(client, world):
    res = book(client, 1, "inc1", date="21/11/2026", period="evening")
    assert res.status_code == 201
    body = res.get_json()
    assert set(body) == {"appt-id", "user-id", "availability", "exercise-code", "date", "period"}
    assert body["appt-id"] > 0
    assert body["user-id"] == 1
    assert body["availability"] is True
    assert body["exercise-code"] == "inc1"
    assert body["date"] == "21/11/2026"
    assert body["period"] == "evening"


def test_appt_ids_increment_per_user_and_need_not_be_globally_unique(client, world):
    ids_user1 = [book(client, 1, "inc1", date=d).get_json()["appt-id"]
                 for d in ["20/11/2026", "21/11/2026", "22/11/2026"]]
    assert ids_user1 == [1, 2, 3]
    assert book(client, 2, "inc1", date="23/11/2026").get_json()["appt-id"] == 1


def test_same_slot_booked_twice_by_the_same_user_is_422_unavailable(client, world):
    assert book(client, 1, "inc1").status_code == 201
    res = book(client, 1, "inc1")
    assert res.status_code == 422
    assert res.get_json()["availability"] is False
    assert res.get_json()["appt-id"] == 0
    assert len(gym_app.schedule_list) == 1


def test_different_users_can_hold_different_exercises_at_the_same_time(client, world):
    assert book(client, 1, "inc1").status_code == 201
    assert book(client, 2, "ben1").status_code == 201


def test_same_exercise_different_periods_or_dates_do_not_clash(client, world):
    assert book(client, 1, "inc1", period="morning").status_code == 201
    assert book(client, 2, "inc1", period="afternoon").status_code == 201
    assert book(client, 2, "inc1", date="21/11/2026", period="morning").status_code == 201


def test_no_period_skips_a_period_the_user_is_already_busy_in(client, world):
    assert book(client, 1, "ben1", period="morning").status_code == 201
    res = book(client, 1, "inc1", period=None)
    assert res.status_code == 201
    assert res.get_json()["period"] in ("afternoon", "evening")


def test_no_period_skips_a_period_someone_else_holds(client, world):
    assert book(client, 2, "inc1", period="morning").status_code == 201
    res = book(client, 1, "inc1", period=None)
    assert res.status_code == 201
    assert res.get_json()["period"] in ("afternoon", "evening")


def test_three_appointment_limit_counts_across_different_exercises(client, world):
    assert book(client, 1, "inc1", date="20/11/2026").status_code == 201
    assert book(client, 1, "ben1", date="21/11/2026").status_code == 201
    assert book(client, 1, "run1", date="22/11/2026").status_code == 201
    assert book(client, 1, "inc1", date="23/11/2026").status_code == 422
    assert book(client, 2, "inc1", date="23/11/2026").status_code == 201  # other users unaffected


def test_cancelling_frees_the_slot_for_someone_else(client, world):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    assert book(client, 2, "inc1").status_code == 422
    assert client.delete(f"/schedule/1/{appt_id}", headers=hdr(1)).status_code == 204
    assert book(client, 2, "inc1").status_code == 201


def test_cancelling_frees_one_of_the_three_active_appointments(client, world):
    ids = [book(client, 1, "inc1", date=d).get_json()["appt-id"]
           for d in ["20/11/2026", "21/11/2026", "22/11/2026"]]
    assert book(client, 1, "inc1", date="23/11/2026").status_code == 422
    assert client.delete(f"/schedule/1/{ids[1]}", headers=hdr(1)).status_code == 204
    assert book(client, 1, "inc1", date="23/11/2026").status_code == 201


def test_failed_booking_does_not_change_the_schedule(client, world):
    book(client, 1, "inc1")
    before = [dict(a) for a in gym_app.schedule_list]
    book(client, 2, "inc1")                              # slot taken
    book(client, 1, "inc1", date="01/01/2027")           # out of window
    book(client, 1, "fake99")                            # unknown exercise
    assert gym_app.schedule_list == before


def test_booking_an_unknown_exercise_is_404(client, world):
    assert book(client, 1, "zzz9").status_code == 404


# --- GET / PUT / DELETE /schedule/{user-id}/{appt-id} ---

def test_get_appointment_returns_the_documented_fields(client, world):
    appt_id = book(client, 1, "inc1", date="21/11/2026", period="afternoon").get_json()["appt-id"]
    res = client.get(f"/schedule/1/{appt_id}", headers=hdr(1))
    assert res.status_code == 200
    body = res.get_json()
    for field, value in [("appt-id", appt_id), ("user-id", 1), ("exercise-code", "inc1"),
                         ("date", "21/11/2026"), ("period", "afternoon")]:
        assert body[field] == value


def test_user_cannot_read_or_delete_another_users_appointment(client, world):
    book(client, 1, "inc1")
    assert client.get("/schedule/1/1", headers=hdr(2)).status_code == 401
    assert client.delete("/schedule/1/1", headers=hdr(2)).status_code == 401
    assert len(gym_app.schedule_list) == 1


def test_appt_id_that_belongs_to_someone_else_is_404_under_my_own_url(client, world):
    book(client, 1, "inc1")                     # user 1 has appt 1; user 2 has none
    assert client.get("/schedule/2/1", headers=hdr(2)).status_code == 404
    assert client.put("/schedule/2/1", json={"date": GOOD_DATE, "period": "evening"},
                      headers=hdr(2)).status_code == 404
    assert client.delete("/schedule/2/1", headers=hdr(2)).status_code == 404


def test_put_to_the_same_slot_succeeds(client, world):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    res = client.put(f"/schedule/1/{appt_id}", json={"date": GOOD_DATE, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 200
    assert res.get_json()["appt-id"] == appt_id


def test_put_returns_the_post_fields_and_keeps_appt_id_and_exercise(client, world):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    res = client.put(f"/schedule/1/{appt_id}", json={"date": "25/11/2026", "period": "evening"}, headers=hdr(1))
    assert res.status_code == 200
    body = res.get_json()
    assert set(body) == {"appt-id", "user-id", "availability", "exercise-code", "date", "period"}
    assert body["appt-id"] == appt_id
    assert body["exercise-code"] == "inc1"
    assert body["availability"] is True
    assert (body["date"], body["period"]) == ("25/11/2026", "evening")
    again = client.get(f"/schedule/1/{appt_id}", headers=hdr(1)).get_json()
    assert (again["date"], again["period"]) == ("25/11/2026", "evening")
    assert len(gym_app.schedule_list) == 1  # replaced, not duplicated


def test_put_without_a_period_picks_a_free_one(client, world):
    appt_id = book(client, 1, "inc1", date="20/11/2026", period="morning").get_json()["appt-id"]
    book(client, 2, "inc1", date="21/11/2026", period="morning")
    res = client.put(f"/schedule/1/{appt_id}", json={"date": "21/11/2026"}, headers=hdr(1))
    assert res.status_code == 200
    assert res.get_json()["period"] in ("afternoon", "evening")


def test_put_onto_a_slot_the_user_holds_for_another_exercise_is_422(client, world):
    first = book(client, 1, "inc1", date="20/11/2026", period="morning").get_json()["appt-id"]
    book(client, 1, "ben1", date="21/11/2026", period="morning")
    res = client.put(f"/schedule/1/{first}", json={"date": "21/11/2026", "period": "morning"}, headers=hdr(1))
    assert res.status_code == 422
    unchanged = client.get(f"/schedule/1/{first}", headers=hdr(1)).get_json()
    assert (unchanged["date"], unchanged["period"]) == ("20/11/2026", "morning")


def test_put_onto_an_occupied_slot_leaves_the_original_slot_held(client, world):
    add_user(3)
    first = book(client, 1, "inc1", date="20/11/2026").get_json()["appt-id"]
    book(client, 2, "inc1", date="21/11/2026")
    res = client.put(f"/schedule/1/{first}", json={"date": "21/11/2026", "period": "morning"}, headers=hdr(1))
    assert res.status_code == 422
    assert book(client, 3, "inc1", date="20/11/2026").status_code == 422  # original still held


def test_successful_put_frees_the_old_slot(client, world):
    first = book(client, 1, "inc1", date="20/11/2026").get_json()["appt-id"]
    assert client.put(f"/schedule/1/{first}", json={"date": "21/11/2026", "period": "evening"},
                      headers=hdr(1)).status_code == 200
    assert book(client, 2, "inc1", date="20/11/2026").status_code == 201


def test_put_does_not_count_against_the_three_appointment_limit(client, world):
    ids = [book(client, 1, "inc1", date=d).get_json()["appt-id"]
           for d in ["20/11/2026", "21/11/2026", "22/11/2026"]]
    res = client.put(f"/schedule/1/{ids[2]}", json={"date": "23/11/2026", "period": "morning"}, headers=hdr(1))
    assert res.status_code == 200


def test_put_unknown_appointment_is_404(client, world):
    res = client.put("/schedule/1/999", json={"date": GOOD_DATE, "period": "morning"}, headers=hdr(1))
    assert res.status_code == 404


def test_delete_appointment_returns_204_with_empty_body_and_a_second_delete_is_404(client, world):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    first = client.delete(f"/schedule/1/{appt_id}", headers=hdr(1))
    assert first.status_code == 204
    assert first.data == b""
    assert client.delete(f"/schedule/1/{appt_id}", headers=hdr(1)).status_code == 404


# --- GET /schedule (admin) ---

def test_admin_schedule_lists_every_users_appointments_with_exactly_five_fields(client, world):
    book(client, 1, "inc1", date="20/11/2026")
    book(client, 2, "ben1", date="21/11/2026", period="evening")
    res = client.get("/schedule", headers=ADMIN_H)
    assert res.status_code == 200
    records = res.get_json()
    assert len(records) == 2
    for record in records:
        assert set(record) == {"exercise-code", "appt-id", "date", "period", "user-id"}
    assert {(r["user-id"], r["exercise-code"]) for r in records} == {(1, "inc1"), (2, "ben1")}


def test_admin_schedule_is_empty_array_when_nothing_is_booked(client, world):
    res = client.get("/schedule", headers=ADMIN_H)
    assert res.status_code == 200
    assert res.get_json() == []


def test_admin_schedule_reflects_put_and_delete(client, world):
    appt_id = book(client, 1, "inc1").get_json()["appt-id"]
    client.put(f"/schedule/1/{appt_id}", json={"date": "25/11/2026", "period": "evening"}, headers=hdr(1))
    only = client.get("/schedule", headers=ADMIN_H).get_json()
    assert len(only) == 1 and only[0]["date"] == "25/11/2026" and only[0]["period"] == "evening"
    client.delete(f"/schedule/1/{appt_id}", headers=hdr(1))
    assert client.get("/schedule", headers=ADMIN_H).get_json() == []


@pytest.mark.parametrize("query", ["user-id=1", "date=20/11/2026", "foo=bar", "exercise-code=inc1&foo=bar"])
def test_admin_schedule_unknown_query_key_is_400(client, world, query):
    assert client.get(f"/schedule?{query}", headers=ADMIN_H).status_code == 400


def test_admin_schedule_filter_returns_only_that_exercise(client, world):
    book(client, 1, "inc1", date="20/11/2026")
    book(client, 1, "ben1", date="21/11/2026")
    book(client, 2, "inc1", date="22/11/2026")
    res = client.get("/schedule?exercise-code=inc1", headers=ADMIN_H)
    assert res.status_code == 200
    assert {r["exercise-code"] for r in res.get_json()} == {"inc1"}
    assert len(res.get_json()) == 2


# --- Status-code conventions (lecture 2: only a successful POST returns 201) ---

def test_only_successful_posts_return_201(client, world):
    created = book(client, 1, "inc1")
    appt_id = created.get_json()["appt-id"]
    assert created.status_code == 201
    assert client.get(f"/schedule/1/{appt_id}", headers=hdr(1)).status_code == 200
    assert client.put(f"/schedule/1/{appt_id}", json={"date": "21/11/2026", "period": "morning"},
                      headers=hdr(1)).status_code == 200
    assert client.get("/exercises", headers=hdr(1)).status_code == 200
    assert client.get("/schedule", headers=ADMIN_H).status_code == 200
    assert client.delete(f"/schedule/1/{appt_id}", headers=hdr(1)).status_code == 204


# --- End to end: the same flow that was run by hand against Docker and the real API-Ninjas ---

@patch("app.requests.get")
def test_end_to_end_register_exercise_book_move_cancel(mock_get, client):
    mock_ninja(mock_get, [ninja_item("Incline Hammer Curls", muscle="biceps", difficulty="beginner")])

    reg = client.post("/register", json={"name": "alon"})
    assert reg.status_code == 201
    uid, key = reg.get_json()["user-id"], reg.get_json()["API-key"]
    user_h = {"X-Api-Key": key}

    ex = client.post("/exercises", json={"name": "Incline Hammer Curls"}, headers=ADMIN_H)
    assert ex.status_code == 201
    code = ex.get_json()["exercise-code"]
    assert code == "inc1"

    appt = client.post(f"/schedule/{uid}/{code}", json={"date": "20/11/2026", "period": "morning"}, headers=user_h)
    assert appt.status_code == 201
    appt_id = appt.get_json()["appt-id"]

    moved = client.put(f"/schedule/{uid}/{appt_id}", json={"date": "21/11/2026", "period": "evening"}, headers=user_h)
    assert moved.status_code == 200
    assert moved.get_json()["appt-id"] == appt_id

    listed = client.get("/schedule", headers=ADMIN_H).get_json()
    assert [(r["user-id"], r["appt-id"], r["date"], r["period"]) for r in listed] == [(uid, appt_id, "21/11/2026", "evening")]

    assert client.delete(f"/schedule/{uid}/{appt_id}", headers=user_h).status_code == 204
    assert client.get(f"/schedule/{uid}/{appt_id}", headers=user_h).status_code == 404
    assert client.get("/schedule", headers=ADMIN_H).get_json() == []