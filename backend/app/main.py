from __future__ import annotations

import csv
import hashlib
import io
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "expenses.db"))

CATEGORIES = ["Food & dining", "Transport", "Shopping", "Bills", "Health", "Entertainment", "Other"]
PAYMENT_METHODS = ["Debit card", "Credit card", "Cash", "Bank transfer", "Digital wallet"]


class ExpensePayload(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=40)
    date: date
    payment_method: str = Field(min_length=1, max_length=40)
    notes: str = Field(default="", max_length=500)


class Expense(ExpensePayload):
    id: int
    created_at: datetime


class ProfilePayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    account_label: str = Field(min_length=1, max_length=80)


class Profile(ProfilePayload):
    id: int


class RegisterPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=128)


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class AuthUser(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: AuthUser


def connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_expense(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    del item["amount_cents"]
    return item


def initialize_database() -> None:
    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
                title TEXT NOT NULL,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            )
            """
        )
        expense_columns = {row[1] for row in connection.execute("PRAGMA table_info(expenses)").fetchall()}
        if "user_id" not in expense_columns:
            connection.execute("ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)")
            connection.execute("DELETE FROM expenses WHERE user_id IS NULL")
        profile_columns = {row[1] for row in connection.execute("PRAGMA table_info(profile)").fetchall()}
        if profile_columns and "user_id" not in profile_columns:
            connection.execute("ALTER TABLE profile RENAME TO profile_legacy")
            connection.execute(
                """
                CREATE TABLE profile (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                    name TEXT NOT NULL,
                    account_label TEXT NOT NULL
                )
                """
            )
            connection.execute("DROP TABLE profile_legacy")
        elif not profile_columns:
            connection.execute(
                """
                CREATE TABLE profile (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id),
                name TEXT NOT NULL,
                account_label TEXT NOT NULL
                )
                """
            )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2_sha256$120000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def current_user(request: Request) -> sqlite3.Row:
    token = request.headers.get("Authorization", "")
    if not token.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    with connect() as connection:
        user = connection.execute(
            "SELECT users.id, users.name, users.email FROM users JOIN sessions ON sessions.user_id = users.id WHERE sessions.token = ?",
            (token[7:].strip(),),
        ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def profile_for_user(connection: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = connection.execute("SELECT user_id AS id, name, account_label FROM profile WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        connection.execute("INSERT INTO profile (user_id, name, account_label) VALUES (?, ?, ?)", (user_id, "Your name", "Personal account"))
        row = connection.execute("SELECT user_id AS id, name, account_label FROM profile WHERE user_id = ?", (user_id,)).fetchone()
    return row


app = FastAPI(title="Pocketwise API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterPayload) -> dict[str, Any]:
    email = payload.email.strip().lower()
    with connect() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (payload.name.strip(), email, hash_password(payload.password), datetime.utcnow().isoformat()),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="An account with this email already exists") from error
        user_id = cursor.lastrowid
        connection.execute("INSERT INTO profile (user_id, name, account_label) VALUES (?, ?, ?)", (user_id, payload.name.strip(), "Personal account"))
        token = secrets.token_urlsafe(32)
        connection.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user_id, datetime.utcnow().isoformat()))
    return {"token": token, "user": {"id": user_id, "name": payload.name.strip(), "email": email}}


@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginPayload) -> dict[str, Any]:
    with connect() as connection:
        user = connection.execute("SELECT id, name, email, password_hash FROM users WHERE email = ? COLLATE NOCASE", (payload.email.strip(),)).fetchone()
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect")
        token = secrets.token_urlsafe(32)
        connection.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)", (token, user["id"], datetime.utcnow().isoformat()))
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}


@app.get("/api/auth/me", response_model=AuthUser)
def me(user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    return dict(user)


@app.post("/api/auth/logout", status_code=204, response_model=None)
def logout(request: Request) -> Response:
    token = request.headers.get("Authorization", "")[7:].strip()
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
    return Response(status_code=204)


@app.get("/api/meta")
def metadata() -> dict[str, list[str]]:
    return {"categories": CATEGORIES, "payment_methods": PAYMENT_METHODS}


@app.get("/api/profile", response_model=Profile)
def get_profile(user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with connect() as connection:
        row = profile_for_user(connection, user["id"])
    return dict(row)


@app.put("/api/profile", response_model=Profile)
def update_profile(payload: ProfilePayload, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with connect() as connection:
        profile_for_user(connection, user["id"])
        connection.execute("UPDATE profile SET name = ?, account_label = ? WHERE user_id = ?", (payload.name.strip(), payload.account_label.strip(), user["id"]))
        row = connection.execute("SELECT user_id AS id, name, account_label FROM profile WHERE user_id = ?", (user["id"],)).fetchone()
    return dict(row)


@app.get("/api/expenses", response_model=list[Expense])
def list_expenses(
    search: str = "",
    category: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: sqlite3.Row = Depends(current_user),
) -> list[dict[str, Any]]:
    clauses: list[str] = ["user_id = ?"]
    params: list[Any] = [user["id"]]
    if search.strip():
        clauses.append("(lower(title) LIKE ? OR lower(notes) LIKE ?)")
        term = f"%{search.strip().lower()}%"
        params.extend([term, term])
    if category != "all":
        clauses.append("category = ?")
        params.append(category)
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date.isoformat())
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        rows = connection.execute(f"SELECT * FROM expenses {where} ORDER BY date DESC, id DESC LIMIT ?", [*params, limit]).fetchall()
    return [row_to_expense(row) for row in rows]


@app.post("/api/expenses", response_model=Expense, status_code=201)
def create_expense(payload: ExpensePayload, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO expenses (user_id, title, amount_cents, category, date, payment_method, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user["id"], payload.title.strip(), round(payload.amount * 100), payload.category, payload.date.isoformat(), payload.payment_method, payload.notes.strip(), datetime.utcnow().isoformat()),
        )
        row = connection.execute("SELECT * FROM expenses WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_expense(row)


@app.put("/api/expenses/{expense_id}", response_model=Expense)
def update_expense(expense_id: int, payload: ExpensePayload, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    user: sqlite3.Row = Depends(current_user),
    with connect() as connection:
        result = connection.execute(
            "UPDATE expenses SET title = ?, amount_cents = ?, category = ?, date = ?, payment_method = ?, notes = ? WHERE id = ? AND user_id = ?",
            (payload.title.strip(), round(payload.amount * 100), payload.category, payload.date.isoformat(), payload.payment_method, payload.notes.strip(), expense_id, user["id"]),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Expense not found")
        row = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return row_to_expense(row)


@app.delete("/api/expenses/{expense_id}", status_code=204, response_model=None)
def delete_expense(expense_id: int, user: sqlite3.Row = Depends(current_user)) -> Response:
    with connect() as connection:
        result = connection.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user["id"]))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return Response(status_code=204)


@app.get("/api/analytics/summary")
def summary(user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    month_start = date.today().replace(day=1).isoformat()
    with connect() as connection:
        totals = connection.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total, COUNT(*) AS count, COALESCE(AVG(amount_cents), 0) AS average FROM expenses WHERE date >= ? AND user_id = ?",
            (month_start, user["id"]),
        ).fetchone()
        previous_start = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1).isoformat()
        previous = connection.execute("SELECT COALESCE(SUM(amount_cents), 0) AS total FROM expenses WHERE date >= ? AND date < ? AND user_id = ?", (previous_start, month_start, user["id"])).fetchone()["total"]
        all_time = connection.execute("SELECT COALESCE(SUM(amount_cents), 0) AS total FROM expenses WHERE user_id = ?", (user["id"],)).fetchone()["total"]
    current = totals["total"]
    change = ((current - previous) / previous * 100) if previous else 0
    return {"month": date.today().strftime("%B"), "total": current / 100, "count": totals["count"], "average": totals["average"] / 100, "all_time_total": all_time / 100, "change_vs_previous_month": round(change, 1)}


@app.get("/api/analytics/categories")
def category_breakdown(user: sqlite3.Row = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT category, SUM(amount_cents) AS total, COUNT(*) AS count FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total DESC", (user["id"],)).fetchall()
    grand_total = sum(row["total"] for row in rows) or 1
    return [{"category": row["category"], "total": row["total"] / 100, "count": row["count"], "percentage": round(row["total"] / grand_total * 100, 1)} for row in rows]


@app.get("/api/analytics/monthly")
def monthly_breakdown(user: sqlite3.Row = Depends(current_user)) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute("SELECT substr(date, 1, 7) AS month, SUM(amount_cents) AS total, COUNT(*) AS count FROM expenses WHERE user_id = ? GROUP BY month ORDER BY month DESC LIMIT 6", (user["id"],)).fetchall()
    return [{"month": row["month"], "total": row["total"] / 100, "count": row["count"]} for row in reversed(rows)]


@app.get("/api/expenses/export")
def export_expenses(user: sqlite3.Row = Depends(current_user)) -> StreamingResponse:
    with connect() as connection:
        rows = connection.execute("SELECT title, amount_cents, category, date, payment_method, notes FROM expenses WHERE user_id = ? ORDER BY date DESC", (user["id"],)).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Amount", "Category", "Date", "Payment method", "Notes"])
    writer.writerows([[row["title"], f"{row['amount_cents'] / 100:.2f}", row["category"], row["date"], row["payment_method"], row["notes"]] for row in rows])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=expenses.csv"})


FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
