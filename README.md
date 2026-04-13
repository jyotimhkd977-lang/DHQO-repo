# Hospital Queue Management System

A Flask-based hospital queue management app with role-based dashboards for patients, receptionists, and doctors.

The system supports:

- patient registration and login
- patient form submission with personal details and symptoms
- receptionist review with department assignment, severity assignment, fake detection, and approve/reject actions
- emergency-first queue prioritization
- doctor queue view for approved patients only
- treatment notes, suggestions, and digital prescription
- patient SMS-style notifications with a navbar notification bell
- PDF report and prescription download
- ML-based waiting time prediction

## Roles

### Patient

- registers and logs in
- fills the patient form with name, age, phone, address, emergency feeling, and symptoms
- tracks latest form status
- views assigned doctor and queue number after approval
- downloads digital prescription after treatment
- sees SMS notifications from the notification bell in the navbar

### Receptionist

- reviews submitted patient forms
- checks fake detection and emergency prediction
- assigns department and severity
- approves or rejects the patient
- moves emergency patients to top priority
- manages doctor availability
- adds new doctors

### Doctor

- sees only approved waiting patients
- views patient details and symptoms
- completes treatment
- adds suggestions
- creates a digital prescription

## Main Features

- dynamic queue sorting based on emergency, severity, and predicted wait
- machine learning wait-time prediction using a trained model in `hospital_model.pkl`
- SMS notification logging in `sms_log`
- notification bell with unread red dot for patients
- report generation in PDF
- prescription generation in PDF
- SQLite database with lightweight schema migration using `ensure_column`

## Project Structure

```text
.
├── app.py
├── database.db
├── hospital_model.pkl
├── model_training.py
├── requirements.txt
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html
    ├── index.html
    ├── login.html
    ├── register.html
    ├── patient_dashboard.html
    ├── reception_dashboard.html
    └── doctor.html
```

## Installation

### 1. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

The app runs by default at:

```text
http://127.0.0.1:5000
```

## Render Deployment

Use these settings for a Render web service:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Python version: `3.12.3`

This repo also includes `.python-version` and `render.yaml` so the Render runtime and start command stay consistent.

## Demo Credentials

These default users are created automatically when the database is initialized:

- Patient
  - phone: `9988776655`
  - password: `patient123`
- Doctor
  - phone: `9876543210`
  - password: `doctor123`
- Receptionist
  - phone: `9123456789`
  - password: `recep123`

## Database

The app uses SQLite and stores data in `database.db`.

Main tables:

- `users`
- `doctors`
- `patients`
- `sms_log`

## How the Flow Works

1. The patient submits a form.
2. Receptionist reviews the submission.
3. Receptionist assigns department and severity.
4. The app predicts emergency priority and waiting time.
5. Approved patients are added to the live queue.
6. Doctors treat approved patients only.
7. Doctors save treatment, suggestions, and prescription.
8. Patient receives notifications and can download the prescription.

## Tech Stack

- Flask
- SQLite
- NumPy
- Pandas
- scikit-learn
- Matplotlib
- Seaborn
- ReportLab
- Bootstrap 5

## Notes

- SMS in this project is simulated and stored in the database log.
- The patient notification bell reads from `sms_log`.
- Existing databases are migrated with `ensure_column()` when the app starts.
- The ML model is loaded from `hospital_model.pkl`. If it does not exist, `model_training.py` is used to create it.
