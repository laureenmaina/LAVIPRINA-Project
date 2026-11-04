import React from "react";

export function PageHeading({ title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Notice({ children, error = false }) {
  if (!children) return null;
  return <p className={error ? "notice error-notice" : "notice"} role={error ? "alert" : "status"}>{children}</p>;
}

export function FarmTable({ columns, rows, emptyMessage }) {
  return (
    <div className="table-scroll">
      <table className="farm-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row) => row) : (
            <tr><td className="empty-row" colSpan={columns.length}>{emptyMessage}</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function today() {
  return new Date().toISOString().slice(0, 10);
}

export function money(value) {
  return `KES ${Number(value || 0).toLocaleString("en-KE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function animalLabel(animals, id) {
  const animal = animals.find((entry) => Number(entry.id) === Number(id));
  return animal ? `${animal.name || animal.tagnumber} (${animal.tagnumber})` : `Animal #${id}`;
}

export function AnimalSelect({ animals, name = "animal_id", required = true, emptyLabel = "Select animal" }) {
  return (
    <label className="form-field">
      Animal
      <select name={name} required={required} defaultValue="">
        <option value="">{emptyLabel}</option>
        {animals.map((animal) => (
          <option value={animal.id} key={animal.id}>
            {animal.name || animal.tagnumber} · {animal.tagnumber}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Field({ label, children, className = "" }) {
  return <label className={`form-field ${className}`.trim()}>{label}{children}</label>;
}

export function SummaryCard({ label, value, alert = false }) {
  return (
    <div className={alert ? "summary-card alert" : "summary-card"}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
