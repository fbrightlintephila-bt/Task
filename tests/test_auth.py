def test_registration_and_login(client):
    response = client.post("/register", data={
        "full_name": "New Student", "student_id": "N100", "email": "new@example.test",
        "password": "long-enough-password", "confirm_password": "long-enough-password",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Sign in" in response.data
    response = client.post("/login", data={"email": "new@example.test", "password": "long-enough-password"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Your assignments" in response.data


def test_registration_rejects_duplicate_and_password_mismatch(client, users):
    duplicate = client.post("/register", data={
        "full_name": "Duplicate", "student_id": "S100", "email": "one@example.test",
        "password": "long-enough-password", "confirm_password": "long-enough-password",
    })
    mismatch = client.post("/register", data={
        "full_name": "New", "student_id": "N101", "email": "new@example.test",
        "password": "long-enough-password", "confirm_password": "other-password-long",
    })
    assert b"Unable to create account" in duplicate.data
    assert b"Passwords must match" in mismatch.data


def test_login_error_is_generic(client, users):
    response = client.post("/login", data={"email": "one@example.test", "password": "wrong"})
    assert b"Unable to sign in with those details" in response.data
    assert b"email not found" not in response.data.lower()
