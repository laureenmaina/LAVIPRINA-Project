import os
from datetime import date, timedelta

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from flask_migrate import Migrate
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from models import Animal, Owner, db

load_dotenv()

# ---------- configuration ----------
database_uri = os.environ.get("DATABASE_URI", "")
if database_uri.startswith("postgres://"):  # SQLAlchemy needs "postgresql://"
    database_uri = database_uri.replace("postgres://", "postgresql://", 1)
if not database_uri:
    raise RuntimeError("DATABASE_URI is not set. Copy .env.example to .env and fill it in.")

secret_key = os.environ.get("SUPABASE_SECRET_KEY")
if not secret_key:
    raise RuntimeError("SECRET_KEY is not set. Add a long random string to your .env file.")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=secret_key,
    JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", secret_key),
    JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=12),
    SQLALCHEMY_DATABASE_URI=database_uri,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,  # photos are sent as small data URLs
)
app.json.compact = False

# In production set FRONTEND_ORIGINS=https://your-site.com (comma separated).
origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "*").split(",")]
CORS(app, resources={r"/api/*": {"origins": origins}})

db.init_app(app)
Migrate(app, db)
JWTManager(app)


# ---------- helpers ----------
def error(message, status=400):
    return jsonify(error=message), status


def owner_id():
    return int(get_jwt_identity())


def get_owned_animal(animal_id):
    return db.session.scalar(
        select(Animal).where(Animal.id == animal_id, Animal.owner_id == owner_id())
    )


REQUIRED = ["tagnumber", "type", "breed", "sex", "birthdate", "currentweight", "status"]
TEXT_FIELDS = ["tagnumber", "name", "breed", "status", "penorpaddock", "sire", "dam", "notes"]
DATE_FIELDS = ["birthdate", "lastvaccinationdate", "nextvaccinationdate", "expectedbirthdate"]
FLOAT_FIELDS = ["currentweight", "averagemilk"]


def parse_date(value, field):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValueError(f"{field} must be a date in YYYY-MM-DD format")


def parse_float(value, field):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if number < 0:
        raise ValueError(f"{field} cannot be negative")
    return number


def clean_animal_data(data, creating):
    """Validate the request body and return only safe, correctly typed values."""
    if creating:
        missing = [f for f in REQUIRED if data.get(f) in (None, "")]
        if missing:
            raise ValueError("Missing required field(s): " + ", ".join(missing))

    out = {}
    for f in TEXT_FIELDS:
        if f in data:
            value = str(data[f]).strip() if data[f] is not None else ""
            out[f] = value or None
    for f in DATE_FIELDS:
        if f in data:
            out[f] = parse_date(data[f], f)
    for f in FLOAT_FIELDS:
        if f in data:
            out[f] = parse_float(data[f], f)

    if "type" in data:
        animal_type = str(data["type"]).strip().lower()
        if animal_type not in ("cow", "sheep"):
            raise ValueError("type must be 'cow' or 'sheep'")
        out["type"] = animal_type
    if "sex" in data:
        sex = str(data["sex"]).strip().capitalize()
        if sex not in ("Female", "Male"):
            raise ValueError("sex must be 'Female' or 'Male'")
        out["sex"] = sex

    if "photo" in data:
        photo = data["photo"] or None
        if photo and not str(photo).startswith("data:image/"):
            raise ValueError("photo must be an image")
        out["photo"] = photo

    if "weights" in data:
        try:
            weights = data["weights"] or []
            if not isinstance(weights, list) or len(weights) > 500:
                raise ValueError
            out["weights"] = [{"d": str(w["d"])[:10], "w": float(w["w"])} for w in weights]
        except (KeyError, TypeError, ValueError):
            raise ValueError("weights must be a list of {d: date, w: kilograms}")

    # Required fields can never be blanked out on update.
    for f in REQUIRED:
        if f in out and out[f] in (None, ""):
            raise ValueError(f"{f} cannot be empty")
    if out.get("currentweight") == 0:
        raise ValueError("currentweight must be greater than 0")
    return out


# ---------- routes ----------
@app.get("/api/health")
def health():
    return jsonify(status="ok")


@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not email or not password:
        return error("Username, email and password are required.")
    if "@" not in email:
        return error("Enter a valid email address.")
    if len(password) < 8:
        return error("Password must be at least 8 characters.")

    existing = db.session.scalar(
        select(Owner).where(or_(Owner.email == email, Owner.username == username))
    )
    if existing:
        if existing.email == email:
            return error("Email already registered, kindly log in.", 409)
        return error("Username already taken. Choose another or log in.", 409)

    owner = Owner(username=username, email=email)
    owner.set_password(password)
    db.session.add(owner)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("That username or email is already registered.", 409)

    token = create_access_token(identity=str(owner.id))
    return jsonify(message="Account created", token=token, owner=owner.to_dict()), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or data.get("email") or "").strip()
    password = data.get("password") or ""
    owner = db.session.scalar(
        select(Owner).where(
            or_(Owner.email == identifier.lower(), Owner.username == identifier)
        )
    )
    if not owner or not owner.check_password(password):
        return error("Wrong email, username or password.", 401)
    token = create_access_token(identity=str(owner.id))
    return jsonify(token=token, owner=owner.to_dict())


@app.get("/api/animals")
@jwt_required()
def list_animals():
    animals = db.session.scalars(
        select(Animal).where(Animal.owner_id == owner_id()).order_by(Animal.name, Animal.tagnumber)
    ).all()
    return jsonify([a.to_dict() for a in animals])


@app.get("/api/animals/<int:animal_id>")
@jwt_required()
def get_animal(animal_id):
    animal = get_owned_animal(animal_id)
    if not animal:
        return error("Animal not found.", 404)
    return jsonify(animal.to_dict())


@app.post("/api/animals")
@jwt_required()
def create_animal():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send the animal details as JSON.")
    try:
        values = clean_animal_data(data, creating=True)
    except ValueError as e:
        return error(str(e))

    duplicate = db.session.scalar(
        select(Animal).where(
            Animal.owner_id == owner_id(), Animal.tagnumber == values["tagnumber"]
        )
    )
    if duplicate:
        return error(f"Tag {values['tagnumber']} is already registered.", 409)

    animal = Animal(owner_id=owner_id(), **values)
    if not animal.weights:
        animal.weights = [{"d": date.today().isoformat(), "w": animal.currentweight}]
    db.session.add(animal)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("That tag number is already registered.", 409)
    return jsonify(message="Animal registered", animal=animal.to_dict()), 201


@app.put("/api/animals/<int:animal_id>")
@jwt_required()
def update_animal(animal_id):
    animal = get_owned_animal(animal_id)
    if not animal:
        return error("Animal not found.", 404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error("Send the changes as JSON.")
    try:
        values = clean_animal_data(data, creating=False)
    except ValueError as e:
        return error(str(e))

    new_tag = values.get("tagnumber")
    if new_tag and new_tag != animal.tagnumber:
        taken = db.session.scalar(
            select(Animal).where(Animal.owner_id == owner_id(), Animal.tagnumber == new_tag)
        )
        if taken:
            return error(f"Tag {new_tag} is already registered.", 409)

    for field, value in values.items():
        setattr(animal, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("That tag number is already registered.", 409)
    return jsonify(message="Animal updated", animal=animal.to_dict())


@app.delete("/api/animals/<int:animal_id>")
@jwt_required()
def delete_animal(animal_id):
    animal = get_owned_animal(animal_id)
    if not animal:
        return error("Animal not found.", 404)
    db.session.delete(animal)
    db.session.commit()
    return jsonify(message="Animal deleted")


# ---------- error handlers (always return JSON) ----------
@app.errorhandler(404)
def not_found(_):
    return error("Not found.", 404)


@app.errorhandler(413)
def too_large(_):
    return error("That upload is too large.", 413)


@app.errorhandler(500)
def server_error(_):
    db.session.rollback()
    return error("Something went wrong on the server.", 500)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
