# StudentEval AI

A local Flask application for assignment submissions, structured AI feedback, teacher review, and teacher-controlled resubmission windows. Submissions are stored before evaluation. The application does not execute uploaded code. Without configured OpenAI credentials, it preserves the submission and marks evaluation as failed rather than inventing a score. Email delivery is disabled until explicitly enabled.

## Requirements

- Python 3.11 or newer
- An OpenAI API key and supported model for live AI evaluations
- SMTP credentials for real email delivery (optional)

## Install and run on Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a random `FLASK_SECRET_KEY`. Leave `EMAIL_ENABLED=false` until SMTP has been tested. Set `OPENAI_API_KEY` and `OPENAI_MODEL` only when ready for real evaluations.

Initialize the local SQLite database and create an authorized teacher account:

```powershell
flask --app app db upgrade
flask --app app create-teacher
```

For schema changes after the initial setup, use Flask-Migrate:

```powershell
flask --app app db migrate -m "describe schema change"
flask --app app db upgrade
```

Start the server:

```powershell
flask --app app run --debug
```

Open `http://127.0.0.1:5000`. Students can register. Teachers cannot register publicly; create their account with the command above. Email ownership verification is teacher-confirmed in this local build. A teacher must confirm a student's address from the teacher submission list before notifications are delivered.

For stable local sessions, keep the same secret in `.env`:

```text
FLASK_SECRET_KEY=generate_a_long_random_value
```

Generate one with Python:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## AI evaluation

`ai_service.py` uses the official OpenAI Python SDK and `OPENAI_MODEL`. The assignment and student submission are sent as untrusted evaluation data. The service validates the JSON report and score before saving. API errors leave the submission in the database with an evaluation-failed status; they do not produce a made-up result. The application never executes student code, so actual output entered by a student is clearly treated as unverified. A scanned PDF without selectable text is rejected with an OCR-required message.

The default rubric is defined in `evaluator.py`. Teachers can provide a rubric JSON object when creating an assignment. The total score is constrained to 0–100, and a score equal to the threshold (default 90) passes.

## Email setup

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SENDER_EMAIL` in `.env`. For Gmail, use an app password, not the account password. Keep `EMAIL_ENABLED=false` until credentials and recipient verification have been tested. Then set `EMAIL_ENABLED=true`. Email logs record sent, failed, disabled, or blocked status, with an idempotency key. Automated tests do not send email.

## Resubmission workflow

1. A student submits text or a supported document.
2. The server stores a separate attempt and then requests AI evaluation.
3. A passing score marks the task completed. A lower score creates a pending schedule for the teacher.
4. The teacher reviews the report and confirms the opening time, deadline, and IANA time zone. Times are stored in UTC.
5. The generated route uses a random identifier and requires authentication plus ownership checks. The route only accepts submissions inside the active window.
6. New work is stored as a new attempt and evaluated again.

The current local version does not yet enforce a teacher-configured maximum retry count, send email-verification tokens, support schedule cancellation/rescheduling history, or provide an isolated execution service. Do not execute uploaded student code on the Flask host. Add an isolated sandbox before introducing automated execution.

## Tests

```powershell
python -m pytest -q
```

The suite uses an in-memory SQLite database and never requires a live OpenAI or SMTP credential.

## GitHub setup

The project is prepared for a repository named `student-eval-ai`; it has not been created or pushed by this project scaffold. After reviewing files and ensuring `.env` and private student data are excluded:

```powershell
git init
git add .
git status
git commit -m "Build StudentEval AI local application"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/student-eval-ai.git
git push -u origin main
```

Never commit `.env`, private uploads, local databases, student reports, or credentials. If a secret is committed, revoke/rotate it immediately. Removing it from the latest commit is insufficient if it exists in repository history; rewrite history and coordinate the force-push with collaborators.

## Deployment guidance

Use a production WSGI server such as Gunicorn behind HTTPS, configure a stable secret through the deployment secret manager, move from SQLite to PostgreSQL, store uploads in private object storage, and use a shared rate-limit backend such as Redis. Set secure cookie flags, backup and retention policies, error monitoring that excludes submission content, and strict access controls. Add a verified email-token flow and teacher audit trail before using real student accounts. Do not deploy Flask's debug server. Configure trusted proxy handling and file scanning in the hosting environment.
