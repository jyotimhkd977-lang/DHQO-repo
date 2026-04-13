"""
model_training.py
-----------------
Trains the project ML assets:
1. wait-time regression model for patient queues
2. fake-submission classifier for patient intake forms
"""

import os
import pickle
import random

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


BASE_DIR = os.path.dirname(__file__)
WAIT_MODEL_PATH = os.path.join(BASE_DIR, "hospital_model.pkl")
FAKE_MODEL_PATH = os.path.join(BASE_DIR, "fake_detection_model.pkl")


# Genuine patient-form building blocks.
GENUINE_FIRST_NAMES = [
    "Aarav",
    "Asha",
    "Rohan",
    "Neha",
    "Priya",
    "Sanjay",
    "Meera",
    "Vikram",
    "Anita",
    "Karan",
    "Pooja",
    "Ritika",
]
GENUINE_LAST_NAMES = [
    "Sharma",
    "Patel",
    "Singh",
    "Reddy",
    "Nair",
    "Iyer",
    "Khan",
    "Das",
    "Verma",
    "Jain",
]
ADDRESS_STREETS = [
    "MG Road",
    "Station Road",
    "Temple Street",
    "Lake View Colony",
    "Ashok Nagar",
    "Gandhi Chowk",
    "Rose Garden Lane",
    "Market Road",
    "Teachers Colony",
    "Shanti Vihar",
]
ADDRESS_CITIES = [
    "Bhubaneswar",
    "Cuttack",
    "Pune",
    "Jaipur",
    "Chennai",
    "Lucknow",
    "Hyderabad",
    "Nagpur",
]
GENUINE_SYMPTOMS = [
    "fever and body pain since yesterday",
    "persistent cough with sore throat for two days",
    "sharp pain in the lower back after lifting weight",
    "itchy skin rash on both hands since morning",
    "headache with dizziness and mild nausea",
    "chest discomfort and shortness of breath while walking",
    "stomach pain with vomiting after dinner",
    "swelling near the ankle after a fall",
    "toothache with gum swelling for three days",
    "burning sensation while urinating and lower abdominal pain",
    "joint pain in knees with difficulty climbing stairs",
    "child has fever, cough, and weakness since last night",
]

# Suspicious/fake patient-form building blocks.
FAKE_NAMES = [
    "test",
    "fake patient",
    "demo user",
    "asdf qwer",
    "null name",
    "aaaaa",
    "12345",
    "sample entry",
]
FAKE_ADDRESSES = [
    "test address",
    "asdf",
    "na",
    "123",
    "xxxxx",
    "dummy location",
    "none",
    "abc abc",
]
FAKE_SYMPTOMS = [
    "test",
    "fake case",
    "11111",
    "1234 1234",
    "asdfgh",
    "pain pain pain pain",
    "qwertyui",
    "demo symptom",
]


def generate_hospital_data(n_samples=1000, random_state=42):
    """
    Simulates realistic hospital records for queue wait prediction.
    """
    np.random.seed(random_state)

    hour_probs = np.array(
        [
            0.01,
            0.01,
            0.01,
            0.01,
            0.01,
            0.01,
            0.01,
            0.03,
            0.06,
            0.08,
            0.08,
            0.06,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.05,
            0.07,
            0.07,
            0.04,
            0.03,
            0.02,
            0.01,
        ]
    )
    hour_probs = hour_probs / hour_probs.sum()
    hour = np.random.choice(range(24), size=n_samples, p=hour_probs)

    severity = np.random.randint(1, 6, size=n_samples)
    age = np.random.randint(1, 90, size=n_samples)
    emergency = np.random.choice([0, 1], size=n_samples, p=[0.80, 0.20])
    doc_available = np.random.choice([0, 1], size=n_samples, p=[0.30, 0.70])
    queue_length = np.random.randint(0, 30, size=n_samples)

    base_wait = queue_length * 3 + (1 - doc_available) * 20
    severity_adj = (6 - severity) * 4
    emergency_adj = emergency * -25
    is_peak = ((hour >= 9) & (hour <= 11)) | ((hour >= 17) & (hour <= 19))
    peak_adj = is_peak.astype(int) * 15
    age_adj = np.where((age < 10) | (age > 65), -5, 0)

    wait_time = (
        base_wait
        + severity_adj
        + emergency_adj
        + peak_adj
        + age_adj
        + np.random.normal(0, 5, n_samples)
    )
    wait_time = np.clip(wait_time, 1, 120)

    return pd.DataFrame(
        {
            "severity": severity,
            "age": age,
            "emergency": emergency,
            "doc_available": doc_available,
            "queue_length": queue_length,
            "hour": hour,
            "wait_time": wait_time.round(1),
        }
    )


def _make_fake_detection_text(name, address, symptoms):
    return (
        f"name: {name.strip()} || "
        f"address: {address.strip()} || "
        f"symptoms: {symptoms.strip()}"
    )


def generate_fake_detection_data(n_samples=600, random_state=42):
    """
    Generates labeled patient-form text examples for fake-submission detection.
    label=1 means suspicious/fake, label=0 means genuine.
    """
    rng = random.Random(random_state)
    rows = []
    genuine_count = n_samples // 2
    fake_count = n_samples - genuine_count

    for _ in range(genuine_count):
        name = f"{rng.choice(GENUINE_FIRST_NAMES)} {rng.choice(GENUINE_LAST_NAMES)}"
        address = (
            f"{rng.randint(4, 780)}, {rng.choice(ADDRESS_STREETS)}, "
            f"{rng.choice(ADDRESS_CITIES)}"
        )
        symptoms = rng.choice(GENUINE_SYMPTOMS)
        if rng.random() < 0.35:
            symptoms = f"{symptoms}, started {rng.choice(['today', 'yesterday', 'two days ago'])}"
        rows.append(
            {
                "text": _make_fake_detection_text(name, address, symptoms),
                "label": 0,
            }
        )

    for _ in range(fake_count):
        pattern = rng.choice(["all_fake", "missing_address", "missing_symptoms", "spam_mix"])
        if pattern == "all_fake":
            name = rng.choice(FAKE_NAMES)
            address = rng.choice(FAKE_ADDRESSES)
            symptoms = rng.choice(FAKE_SYMPTOMS)
        elif pattern == "missing_address":
            name = rng.choice(FAKE_NAMES + GENUINE_FIRST_NAMES)
            address = ""
            symptoms = rng.choice(FAKE_SYMPTOMS + GENUINE_SYMPTOMS)
        elif pattern == "missing_symptoms":
            name = rng.choice(FAKE_NAMES + [f"{rng.choice(GENUINE_FIRST_NAMES)} {rng.choice(GENUINE_LAST_NAMES)}"])
            address = rng.choice(FAKE_ADDRESSES + [f"{rng.randint(1, 30)} {rng.choice(ADDRESS_STREETS)}"])
            symptoms = ""
        else:
            name = rng.choice(
                [
                    "aaa111",
                    "demo patient",
                    "test test",
                    f"{rng.choice(GENUINE_FIRST_NAMES)} 123",
                    "xxxxxx",
                ]
            )
            address = rng.choice(
                [
                    "123",
                    "asdf asdf",
                    "na",
                    "dummy location",
                    f"{rng.randint(1, 9)}",
                ]
            )
            symptoms = rng.choice(
                [
                    "11111",
                    "1234",
                    "pain pain pain pain",
                    "qwerty",
                    "demo symptom text",
                ]
            )
        rows.append(
            {
                "text": _make_fake_detection_text(name, address, symptoms),
                "label": 1,
            }
        )

    rng.shuffle(rows)
    return pd.DataFrame(rows)


def train_model():
    print("=" * 50)
    print("  Hospital Queue ML Model Training")
    print("=" * 50)

    print("\n[1/4] Generating synthetic hospital records...")
    df = generate_hospital_data(n_samples=1000)
    print(f"      Dataset shape: {df.shape}")
    print(df.describe().round(2))

    features = ["severity", "age", "emergency", "doc_available", "queue_length", "hour"]
    target = "wait_time"

    X = df[features]
    y = df[target]

    print("\n[2/4] Splitting data (80% train / 20% test)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    print("\n[3/4] Training Random Forest Regressor...")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=10,
        min_samples_split=4,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)

    importance = pd.Series(model.feature_importances_, index=features)

    print("\n[4/4] Saving wait-time model to hospital_model.pkl...")
    with open(WAIT_MODEL_PATH, "wb") as f:
        pickle.dump(
            {
                "model": model,
                "features": features,
                "r2_score": round(r2, 4),
                "mae": round(mae, 2),
                "feature_importance": importance.to_dict(),
            },
            f,
        )

    print(f"  Saved -> {WAIT_MODEL_PATH}")
    print(f"  Test R2  : {r2:.4f}")
    print(f"  Test MAE : {mae:.2f} minutes")
    return model, r2, mae


def train_fake_detection_model():
    print("=" * 50)
    print("  Fake Submission Detection Model Training")
    print("=" * 50)

    print("\n[1/4] Generating labeled patient-form samples...")
    df = generate_fake_detection_data(n_samples=600)
    print(f"      Dataset shape: {df.shape}")
    print(df['label'].value_counts().sort_index().rename(index={0: 'genuine', 1: 'fake'}))

    X = df["text"]
    y = df["label"]

    print("\n[2/4] Splitting data (80% train / 20% test)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\n[3/4] Training TF-IDF + Logistic Regression classifier...")
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print("\n[4/4] Saving classifier to fake_detection_model.pkl...")
    with open(FAKE_MODEL_PATH, "wb") as f:
        pickle.dump(
            {
                "model": model,
                "accuracy": round(accuracy, 4),
                "samples": int(len(df)),
                "positive_label": "fake_or_suspicious",
            },
            f,
        )

    print(f"  Saved -> {FAKE_MODEL_PATH}")
    print(f"  Test accuracy : {accuracy:.4f}")
    return model, accuracy


if __name__ == "__main__":
    train_model()
    train_fake_detection_model()
