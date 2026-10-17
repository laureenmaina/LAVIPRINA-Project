from datetime import date
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


# One shared db object. Models MUST inherit from db.Model so that
# Flask-SQLAlchemy and Flask-Migrate can see the tables.
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
    # A tag number only has to be unique within one farm owner's herd.
    __table_args__ = (UniqueConstraint("owner_id", "tagnumber", name="uq_owner_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)

    tagnumber: Mapped[str] = mapped_column(String(30))  # text: "KR-001"
    name: Mapped[Optional[str]] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(10))  # "cow" or "sheep"
    breed: Mapped[str] = mapped_column(String(60))
    sex: Mapped[str] = mapped_column(String(10))  # "Female" or "Male"
    birthdate: Mapped[date] = mapped_column(Date)
    currentweight: Mapped[float]
    status: Mapped[str] = mapped_column(String(30))

    penorpaddock: Mapped[Optional[str]] = mapped_column(String(60))
    sire: Mapped[Optional[str]] = mapped_column(String(30))
    dam: Mapped[Optional[str]] = mapped_column(String(30))
    lastvaccinationdate: Mapped[Optional[date]] = mapped_column(Date)
    nextvaccinationdate: Mapped[Optional[date]] = mapped_column(Date)
    averagemilk: Mapped[Optional[float]]  # sheep and dry cows may have none
    expectedbirthdate: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    photo: Mapped[Optional[str]] = mapped_column(Text)  # small data URL
    weights: Mapped[list] = mapped_column(JSON, default=list)  # [{"d": "2026-09-30", "w": 612}]

    owner: Mapped["Owner"] = relationship(back_populates="animals")

    @property
    def age_months(self) -> Optional[int]:
        # Calculated, never stored, so it can't go out of date.
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
            "id": self.id,
            "tagnumber": self.tagnumber,
            "name": self.name,
            "type": self.type,
            "breed": self.breed,
            "sex": self.sex,
            "birthdate": iso(self.birthdate),
            "age_months": self.age_months,
            "currentweight": self.currentweight,
            "status": self.status,
            "penorpaddock": self.penorpaddock,
            "sire": self.sire,
            "dam": self.dam,
            "lastvaccinationdate": iso(self.lastvaccinationdate),
            "nextvaccinationdate": iso(self.nextvaccinationdate),
            "averagemilk": self.averagemilk,
            "expectedbirthdate": iso(self.expectedbirthdate),
            "notes": self.notes,
            "photo": self.photo,
            "weights": self.weights or [],
        }

    def __repr__(self) -> str:
        return f"Animal(id={self.id!r}, tagnumber={self.tagnumber!r})"
