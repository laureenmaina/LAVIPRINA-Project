from datetime import date
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Date, ForeignKey, String, Text, UniqueConstraint, Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Owner(db.Model):
    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    animals: Mapped[list["Animal"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "email": self.email}

    def __repr__(self) -> str:
        return f"Owner(id={self.id!r}, username={self.username!r})"


class Animal(db.Model):
    __tablename__ = "animals"
    __table_args__ = (UniqueConstraint("owner_id", "tagnumber", name="uq_owner_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    tagnumber: Mapped[str] = mapped_column(String(30))
    name: Mapped[Optional[str]] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(10))
    breed: Mapped[str] = mapped_column(String(60))
    sex: Mapped[str] = mapped_column(String(10))
    birthdate: Mapped[date] = mapped_column(Date)
    currentweight: Mapped[float]
    status: Mapped[str] = mapped_column(String(30))
    penorpaddock: Mapped[Optional[str]] = mapped_column(String(60))
    sire: Mapped[Optional[str]] = mapped_column(String(30))
    dam: Mapped[Optional[str]] = mapped_column(String(30))
    lastvaccinationdate: Mapped[Optional[date]] = mapped_column(Date)
    nextvaccinationdate: Mapped[Optional[date]] = mapped_column(Date)
    averagemilk: Mapped[Optional[float]]
    expectedbirthdate: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    photo: Mapped[Optional[str]] = mapped_column(Text)
    weights: Mapped[list] = mapped_column(JSON, default=list)

    owner: Mapped["Owner"] = relationship(back_populates="animals")

    @property
    def age_months(self) -> Optional[int]:
        if not self.birthdate:
            return None
        today = date.today()
        months = (today.year - self.birthdate.year) * 12 + today.month - self.birthdate.month
        if today.day < self.birthdate.day:
            months -= 1
        return max(months, 0)

    def to_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None
        return {
            "id": self.id, "tagnumber": self.tagnumber, "name": self.name,
            "type": self.type, "breed": self.breed, "sex": self.sex,
            "birthdate": iso(self.birthdate), "age_months": self.age_months,
            "currentweight": self.currentweight, "status": self.status,
            "penorpaddock": self.penorpaddock, "sire": self.sire, "dam": self.dam,
            "lastvaccinationdate": iso(self.lastvaccinationdate),
            "nextvaccinationdate": iso(self.nextvaccinationdate),
            "averagemilk": self.averagemilk, "expectedbirthdate": iso(self.expectedbirthdate),
            "notes": self.notes, "photo": self.photo, "weights": self.weights or [],
        }

    def __repr__(self) -> str:
        return f"Animal(id={self.id!r}, tagnumber={self.tagnumber!r})"


class MilkRecord(db.Model):
    __tablename__ = "milk_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id"), index=True)
    record_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    morning_litres: Mapped[float] = mapped_column(Float, default=0)
    evening_litres: Mapped[float] = mapped_column(Float, default=0)
    sold_litres: Mapped[float] = mapped_column(Float, default=0)
    used_litres: Mapped[float] = mapped_column(Float, default=0)
    discarded_litres: Mapped[float] = mapped_column(Float, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    def to_dict(self):
        return {"id": self.id, "animal_id": self.animal_id, "record_date": self.record_date.isoformat(),
                "morning_litres": self.morning_litres, "evening_litres": self.evening_litres,
                "total_litres": self.morning_litres + self.evening_litres,
                "sold_litres": self.sold_litres, "used_litres": self.used_litres,
                "discarded_litres": self.discarded_litres, "notes": self.notes}


class HealthRecord(db.Model):
    __tablename__ = "health_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id"), index=True)
    event_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    category: Mapped[str] = mapped_column(String(30), default="vet_visit")
    description: Mapped[str] = mapped_column(Text)
    medicine: Mapped[Optional[str]] = mapped_column(String(120))
    cost: Mapped[float] = mapped_column(Float, default=0)
    follow_up_date: Mapped[Optional[date]] = mapped_column(Date)

    def to_dict(self):
        return {"id": self.id, "animal_id": self.animal_id, "event_date": self.event_date.isoformat(),
                "category": self.category, "description": self.description, "medicine": self.medicine,
                "cost": self.cost, "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None}


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_owner_inventory_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(40), default="feed")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    reorder_level: Mapped[float] = mapped_column(Float, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "category": self.category, "quantity": self.quantity,
                "unit": self.unit, "reorder_level": self.reorder_level, "unit_cost": self.unit_cost,
                "low_stock": self.quantity <= self.reorder_level}


class Transaction(db.Model):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    animal_id: Mapped[Optional[int]] = mapped_column(ForeignKey("animals.id"), nullable=True, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    kind: Mapped[str] = mapped_column(String(10))  # sale or expense
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0)

    def to_dict(self):
        return {"id": self.id, "animal_id": self.animal_id,
                "transaction_date": self.transaction_date.isoformat(), "kind": self.kind,
                "category": self.category, "description": self.description,
                "quantity": self.quantity, "unit_price": self.unit_price, "amount": self.amount}
