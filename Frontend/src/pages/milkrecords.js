import React, { useState } from "react";
import { useFarm } from "../context/FarmContext";
import { AnimalSelect, animalLabel, FarmTable, Field, Notice, PageHeading, today } from "../components/FarmCommon";

export default function MilkRecords() {
  const { dairyCows, milkRecords, animals, request, refresh } = useFarm();
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    ["animal_id", "morning_litres", "evening_litres", "sold_litres", "used_litres", "discarded_litres"].forEach((key) => {
      data[key] = Number(data[key]);
    });
    setNotice("");
    setSaving(true);
    try {
      await request("/milk", { method: "POST", body: data });
      form.reset();
      form.elements.record_date.value = today();
      ["morning_litres", "evening_litres", "sold_litres", "used_litres", "discarded_litres"].forEach((key) => { form.elements[key].value = "0"; });
      await refresh();
      setNotice("Milk record saved.");
    } catch (saveError) {
      setNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeRecord(id) {
    if (!window.confirm("Delete this milk record?")) return;
    try {
      await request(`/milk/${id}`, { method: "DELETE" });
      await refresh();
    } catch (deleteError) {
      setNotice(deleteError.message);
    }
  }

  return (
    <div className="page-content">
      <PageHeading title="Milk records" description="Log morning and evening milk production for each dairy cow." />
      <Notice error>{notice}</Notice>
      {!dairyCows.length && <Notice>Add female cows from Dashboard before recording milk production.</Notice>}
      <form className="farm-form" onSubmit={submit}>
        <div className="form-grid">
          <AnimalSelect animals={dairyCows} emptyLabel="Select dairy cow" />
          <Field label="Date"><input type="date" name="record_date" defaultValue={today()} required /></Field>
          <Field label="Morning (L)"><input type="number" name="morning_litres" min="0" step="0.1" defaultValue="0" required /></Field>
          <Field label="Evening (L)"><input type="number" name="evening_litres" min="0" step="0.1" defaultValue="0" required /></Field>
          <Field label="Sold (L)"><input type="number" name="sold_litres" min="0" step="0.1" defaultValue="0" required /></Field>
          <Field label="Used (L)"><input type="number" name="used_litres" min="0" step="0.1" defaultValue="0" required /></Field>
          <Field label="Discarded (L)"><input type="number" name="discarded_litres" min="0" step="0.1" defaultValue="0" required /></Field>
          <Field label="Notes"><input name="notes" placeholder="Optional notes" /></Field>
        </div>
        <button className="button primary" disabled={saving || !dairyCows.length}>{saving ? "Saving…" : "Save milk record"}</button>
      </form>
      <FarmTable
        columns={["Date", "Animal", "Total (L)", "Sold", "Used", "Discarded", "Actions"]}
        emptyMessage="No milk records yet."
        rows={milkRecords.map((record) => (
          <tr key={record.id}>
            <td>{record.record_date}</td><td>{animalLabel(animals, record.animal_id)}</td>
            <td>{Number(record.total_litres).toFixed(1)}</td><td>{Number(record.sold_litres).toFixed(1)}</td>
            <td>{Number(record.used_litres).toFixed(1)}</td><td>{Number(record.discarded_litres).toFixed(1)}</td>
            <td><button className="button danger small" onClick={() => removeRecord(record.id)}>Delete</button></td>
          </tr>
        ))}
      />
    </div>
  );
}
