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
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from models import Animal, HealthRecord, InventoryItem, MilkRecord, Owner, Transaction, db

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


def clean_animal_data(
    data,
    creating,
    existing_next_vaccination_date=None,
    existing_birthdate=None,
    existing_last_vaccination_date=None,
    existing_type=None,
    existing_sex=None,
    existing_status=None,
):
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
    birthdate = out.get("birthdate", existing_birthdate)
    last_vaccination_date = out.get(
        "lastvaccinationdate", existing_last_vaccination_date
    )
    if (
        birthdate is not None
        and last_vaccination_date is not None
        and last_vaccination_date <= birthdate
    ):
        raise ValueError("lastvaccinationdate must be after birthdate")
    next_vaccination_date = out.get("nextvaccinationdate")
    if (
        next_vaccination_date is not None
        and next_vaccination_date < date.today()
        and next_vaccination_date != existing_next_vaccination_date
    ):
        raise ValueError("nextvaccinationdate cannot be in the past")
    for f in FLOAT_FIELDS:
        if f in data:
            out[f] = parse_float(data[f], f)

    if "type" in data:
        animal_type = str(data["type"]).strip().lower()
        if animal_type not in ("cow", "sheep", "dairycow"):
            raise ValueError("type must be 'cow', 'sheep', or 'dairycow'")
        out["type"] = animal_type
    if "sex" in data:
        sex = str(data["sex"]).strip().capitalize()
        if sex not in ("Female", "Male"):
            raise ValueError("sex must be 'Female' or 'Male'")
        out["sex"] = sex
    animal_type = out.get("type", existing_type)
    sex = out.get("sex", existing_sex)
    status = out.get("status", existing_status)
    if (
        str(animal_type).lower() == "cow"
        and sex == "Male"
        and str(status).strip().lower() == "milking"
    ):
        raise ValueError("A male cow cannot have the status 'Milking'")

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


@app.get("/api/dairy-cows")
@jwt_required()
def list_dairy_cows():
    animals = db.session.scalars(
        select(Animal)
        .where(
            Animal.owner_id == owner_id(),
            func.lower(Animal.type).in_(("cow", "dairycow")),
            func.lower(Animal.sex) == "female",
        )
        .order_by(Animal.name, Animal.tagnumber)
    ).all()
    return jsonify([animal.to_dict() for animal in animals])


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
        values = clean_animal_data(
            data,
            creating=False,
            existing_next_vaccination_date=animal.nextvaccinationdate,
            existing_birthdate=animal.birthdate,
            existing_last_vaccination_date=animal.lastvaccinationdate,
            existing_type=animal.type,
            existing_sex=animal.sex,
            existing_status=animal.status,
        )
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
    # Remove child records first because these tables reference the animal.
    for model in (MilkRecord, HealthRecord, Transaction):
        children = db.session.scalars(select(model).where(
            model.animal_id == animal.id, model.owner_id == owner_id()
        )).all()
        for child in children:
            db.session.delete(child)
    db.session.delete(animal)
    db.session.commit()
    return jsonify(message="Animal and its linked operation records deleted")




# ---------- farm operations: milk, health/breeding, inventory, finances ----------
def parse_nonnegative(data, field, default=0):
    value = data.get(field, default)
    if value in (None, ""):
        value = default
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")
    if value < 0:
        raise ValueError(f"{field} cannot be negative")
    return value


def owned_animal_id(value, required=True):
    if value in (None, ""):
        if required:
            raise ValueError("animal_id is required")
        return None
    try:
        animal_id = int(value)
    except (TypeError, ValueError):
        raise ValueError("animal_id must be a valid animal ID")
    animal = db.session.scalar(select(Animal).where(
        Animal.id == animal_id, Animal.owner_id == owner_id()
    ))
    if not animal:
        raise ValueError("Animal not found in your herd")
    return animal_id


def owned_records(model):
    return db.session.scalars(
        select(model).where(model.owner_id == owner_id()).order_by(model.id.desc())
    ).all()


def parse_required_date(data, field, default_today=True):
    value = data.get(field)
    if value in (None, "") and default_today:
        return date.today()
    parsed = parse_date(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


@app.get("/api/milk")
@jwt_required()
def list_milk_records():
    rows = db.session.scalars(select(MilkRecord).where(
        MilkRecord.owner_id == owner_id()
    ).order_by(MilkRecord.record_date.desc(), MilkRecord.id.desc())).all()
    return jsonify([r.to_dict() for r in rows])


@app.post("/api/milk")
@jwt_required()
def create_milk_record():
    data = request.get_json(silent=True) or {}
    try:
        animal_id = owned_animal_id(data.get("animal_id"))
        animal = db.session.scalar(select(Animal).where(Animal.id == animal_id))
        if (
            str(animal.type).strip().lower() not in ("cow", "dairycow")
            or str(animal.sex).strip().lower() != "female"
        ):
            raise ValueError("Milk records can only be added for dairy cows")
        morning = parse_nonnegative(data, "morning_litres")
        evening = parse_nonnegative(data, "evening_litres")
        sold = parse_nonnegative(data, "sold_litres")
        used = parse_nonnegative(data, "used_litres")
        discarded = parse_nonnegative(data, "discarded_litres")
        if sold + used + discarded > morning + evening + 0.0001:
            raise ValueError("Sold, used and discarded milk cannot exceed total milk produced")
        row = MilkRecord(owner_id=owner_id(), animal_id=animal_id,
            record_date=parse_required_date(data, "record_date"),
            morning_litres=morning, evening_litres=evening, sold_litres=sold,
            used_litres=used, discarded_litres=discarded,
            notes=(str(data.get("notes") or "").strip() or None))
        db.session.add(row); db.session.commit()
        return jsonify(message="Milk record saved", record=row.to_dict()), 201
    except ValueError as e:
        return error(str(e))


@app.delete("/api/milk/<int:record_id>")
@jwt_required()
def delete_milk_record(record_id):
    row = db.session.scalar(select(MilkRecord).where(
        MilkRecord.id == record_id, MilkRecord.owner_id == owner_id()))
    if not row: return error("Milk record not found.", 404)
    db.session.delete(row); db.session.commit()
    return jsonify(message="Milk record deleted")


@app.get("/api/health-records")
@jwt_required()
def list_health_records():
    rows = db.session.scalars(select(HealthRecord).where(
        HealthRecord.owner_id == owner_id()
    ).order_by(HealthRecord.event_date.desc(), HealthRecord.id.desc())).all()
    return jsonify([r.to_dict() for r in rows])


@app.post("/api/health-records")
@jwt_required()
def create_health_record():
    data = request.get_json(silent=True) or {}
    try:
        animal_id = owned_animal_id(data.get("animal_id"))
        category = str(data.get("category") or "vet_visit").strip().lower()
        allowed = {"treatment", "vaccination", "breeding", "pregnancy_check", "lambing", "birth", "vet_visit", "other"}
        if category not in allowed:
            raise ValueError("Choose a valid health or breeding record type")
        description = str(data.get("description") or "").strip()
        if not description: raise ValueError("description is required")
        follow = parse_date(data.get("follow_up_date"), "follow_up_date")
        row = HealthRecord(owner_id=owner_id(), animal_id=animal_id,
            event_date=parse_required_date(data, "event_date"), category=category,
            description=description, medicine=(str(data.get("medicine") or "").strip() or None),
            cost=parse_nonnegative(data, "cost"), follow_up_date=follow)
        db.session.add(row); db.session.commit()
        return jsonify(message="Health/breeding record saved", record=row.to_dict()), 201
    except ValueError as e:
        return error(str(e))


@app.delete("/api/health-records/<int:record_id>")
@jwt_required()
def delete_health_record(record_id):
    row = db.session.scalar(select(HealthRecord).where(
        HealthRecord.id == record_id, HealthRecord.owner_id == owner_id()))
    if not row: return error("Record not found.", 404)
    db.session.delete(row); db.session.commit()
    return jsonify(message="Record deleted")


@app.get("/api/inventory")
@jwt_required()
def list_inventory():
    rows = db.session.scalars(select(InventoryItem).where(
        InventoryItem.owner_id == owner_id()).order_by(InventoryItem.name)).all()
    return jsonify([r.to_dict() for r in rows])


@app.post("/api/inventory")
@jwt_required()
def create_inventory_item():
    data = request.get_json(silent=True) or {}
    try:
        name = str(data.get("name") or "").strip()
        if not name: raise ValueError("Item name is required")
        category = str(data.get("category") or "feed").strip().lower()
        if category not in {"feed", "medicine", "supplies", "other"}:
            raise ValueError("Invalid inventory category")
        item = InventoryItem(owner_id=owner_id(), name=name, category=category,
            quantity=parse_nonnegative(data, "quantity"),
            unit=str(data.get("unit") or "kg").strip()[:20],
            reorder_level=parse_nonnegative(data, "reorder_level"),
            unit_cost=parse_nonnegative(data, "unit_cost"))
        db.session.add(item); db.session.commit()
        return jsonify(message="Inventory item saved", item=item.to_dict()), 201
    except IntegrityError:
        db.session.rollback()
        return error("An inventory item with that name already exists.", 409)
    except ValueError as e:
        return error(str(e))


@app.put("/api/inventory/<int:item_id>")
@jwt_required()
def update_inventory_item(item_id):
    item = db.session.scalar(select(InventoryItem).where(
        InventoryItem.id == item_id, InventoryItem.owner_id == owner_id()))
    if not item: return error("Inventory item not found.", 404)
    data = request.get_json(silent=True) or {}
    try:
        for field in ("name", "category", "unit"):
            if field in data:
                value = str(data[field] or "").strip()
                if field == "name" and not value: raise ValueError("Item name is required")
                if field == "category" and value not in {"feed", "medicine", "supplies", "other"}:
                    raise ValueError("Invalid inventory category")
                setattr(item, field, value)
        for field in ("quantity", "reorder_level", "unit_cost"):
            if field in data: setattr(item, field, parse_nonnegative(data, field))
        db.session.commit()
        return jsonify(message="Inventory updated", item=item.to_dict())
    except IntegrityError:
        db.session.rollback(); return error("An inventory item with that name already exists.", 409)
    except ValueError as e:
        return error(str(e))


@app.delete("/api/inventory/<int:item_id>")
@jwt_required()
def delete_inventory_item(item_id):
    item = db.session.scalar(select(InventoryItem).where(
        InventoryItem.id == item_id, InventoryItem.owner_id == owner_id()))
    if not item: return error("Inventory item not found.", 404)
    db.session.delete(item); db.session.commit()
    return jsonify(message="Inventory item deleted")


@app.get("/api/transactions")
@jwt_required()
def list_transactions():
    rows = db.session.scalars(select(Transaction).where(
        Transaction.owner_id == owner_id()
    ).order_by(Transaction.transaction_date.desc(), Transaction.id.desc())).all()
    return jsonify([r.to_dict() for r in rows])


@app.post("/api/transactions")
@jwt_required()
def create_transaction():
    data = request.get_json(silent=True) or {}
    try:
        kind = str(data.get("kind") or "").strip().lower()
        if kind not in {"sale", "expense"}: raise ValueError("kind must be sale or expense")
        category = str(data.get("category") or "").strip()
        description = str(data.get("description") or "").strip()
        if not category or not description: raise ValueError("Category and description are required")
        quantity = parse_nonnegative(data, "quantity", 1)
        unit_price = parse_nonnegative(data, "unit_price")
        amount = parse_nonnegative(data, "amount", quantity * unit_price)
        if "animal_id" in data and data.get("animal_id") not in (None, ""):
            animal_id = owned_animal_id(data.get("animal_id"), required=False)
        else: animal_id = None
        row = Transaction(owner_id=owner_id(), animal_id=animal_id,
            transaction_date=parse_required_date(data, "transaction_date"), kind=kind,
            category=category[:50], description=description[:200], quantity=quantity,
            unit_price=unit_price, amount=amount)
        db.session.add(row); db.session.commit()
        return jsonify(message="Transaction saved", transaction=row.to_dict()), 201
    except ValueError as e:
        return error(str(e))


@app.delete("/api/transactions/<int:transaction_id>")
@jwt_required()
def delete_transaction(transaction_id):
    row = db.session.scalar(select(Transaction).where(
        Transaction.id == transaction_id, Transaction.owner_id == owner_id()))
    if not row: return error("Transaction not found.", 404)
    db.session.delete(row); db.session.commit()
    return jsonify(message="Transaction deleted")


@app.get("/api/reports/summary")
@jwt_required()
def reports_summary():
    milk_rows = db.session.scalars(select(MilkRecord).where(MilkRecord.owner_id == owner_id())).all()
    transactions = db.session.scalars(select(Transaction).where(Transaction.owner_id == owner_id())).all()
    inventory = db.session.scalars(select(InventoryItem).where(InventoryItem.owner_id == owner_id())).all()
    produced = sum(r.morning_litres + r.evening_litres for r in milk_rows)
    sales = sum(t.amount for t in transactions if t.kind == "sale")
    expenses = sum(t.amount for t in transactions if t.kind == "expense")
    return jsonify(total_milk_litres=round(produced, 2), milk_record_count=len(milk_rows),
        sales=round(sales, 2), expenses=round(expenses, 2), net=round(sales-expenses, 2),
        low_stock_count=sum(1 for i in inventory if i.quantity <= i.reorder_level))


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
