import React, { useState } from "react";
import { useFarm } from "../context/FarmContext";
import { AnimalSelect, animalLabel, FarmTable, Field, money, Notice, PageHeading, today } from "../components/FarmCommon";

const categories = [
  ["vet_visit", "Vet visit"], ["treatment", "Treatment"], ["vaccination", "Vaccination"],
  ["breeding", "Breeding"], ["pregnancy_check", "Pregnancy check"], ["lambing", "Lambing"],
  ["birth", "Birth"], ["other", "Other"],
];

export default function Breeding() {
  const { animals, healthRecords, request, refresh } = useFarm();
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.animal_id = Number(data.animal_id);
    data.cost = Number(data.cost);
    if (!data.follow_up_date) data.follow_up_date = null;
    setNotice("");
    setSaving(true);
    try {
      await request("/health-records", { method: "POST", body: data });
      form.reset();
      form.elements.event_date.value = today();
      form.elements.cost.value = "0";
      await refresh();
      setNotice("Health or breeding record saved.");
    } catch (saveError) {
      setNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeRecord(id) {
    if (!window.confirm("Delete this health or breeding record?")) return;
    try {
      await request(`/health-records/${id}`, { method: "DELETE" });
      await refresh();
    } catch (deleteError) {
      setNotice(deleteError.message);
    }
  }

  return (
    <div className="page-content">
      <PageHeading title="Breeding & animal health" description="Keep a dated history of treatments, vaccinations, breeding, pregnancy checks, lambing and births." />
      <Notice error>{notice}</Notice>
      {!animals.length && <Notice>Add animals from Dashboard before recording health or breeding events.</Notice>}
      <form className="farm-form" onSubmit={submit}>
        <h2>Record an event</h2>
        <div className="form-grid">
          <AnimalSelect animals={animals} />
          <Field label="Date"><input type="date" name="event_date" defaultValue={today()} required /></Field>
          <Field label="Record type">
            <select name="category" defaultValue="vet_visit">
              {categories.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </Field>
          <Field label="Medicine / product"><input name="medicine" placeholder="Optional" /></Field>
          <Field label="Cost (KES)"><input type="number" name="cost" min="0" step="0.01" defaultValue="0" required /></Field>
          <Field label="Follow-up date"><input type="date" name="follow_up_date" /></Field>
          <Field label="Details" className="wide-field"><textarea name="description" rows="2" required placeholder="Symptoms, treatment, breeding notes, outcome…" /></Field>
        </div>
        <button className="button primary" disabled={saving || !animals.length}>{saving ? "Saving…" : "Save record"}</button>
      </form>
      <FarmTable
        columns={["Date", "Animal", "Type", "Details", "Cost", "Follow-up", "Actions"]}
        emptyMessage="No health or breeding records yet."
        rows={healthRecords.map((record) => (
          <tr key={record.id}>
            <td>{record.event_date}</td><td>{animalLabel(animals, record.animal_id)}</td>
            <td>{record.category.replaceAll("_", " ")}</td>
            <td>{record.description}{record.medicine ? ` · ${record.medicine}` : ""}</td>
            <td>{money(record.cost)}</td><td>{record.follow_up_date || "—"}</td>
            <td><button className="button danger small" onClick={() => removeRecord(record.id)}>Delete</button></td>
          </tr>
        ))}
      />
    </div>
  );
}
