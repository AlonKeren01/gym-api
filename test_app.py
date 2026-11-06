import pytest
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
    """All API requests (except POST /register and POST /validate) require X-Api-Key header[cite: 32]. Returns 400 if missing[cite: 33]."""
    gym_app.exercises["inc1"] = {"name": "Incline", "type": "strength", "muscle-group": "chest", "difficulty": "expert", "exercise-code": "inc1"}

    # Missing X-Api-Key header on GET /exercises
    res = client.get('/exercises')
    assert res.status_code == 400 #[cite: 32, 33]


def test_admin_schedule_empty_match_query_string(client):
    """When the query string produces no matches, return an empty array with code 200[cite: 47]."""
    # Admin requests schedule for an exercise code that has no bookings
    res = client.get('/schedule?exercise-code=unused_code', headers={"X-Api-Key": "ytngh52@gb&&ubt8"})

    assert res.status_code == 200 #[cite: 47]
    assert res.get_json() == [] #[cite: 47]