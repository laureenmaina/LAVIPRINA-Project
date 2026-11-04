import React, { useState } from "react";
import { useFarm } from "../context/FarmContext";
import { AnimalSelect, animalLabel, FarmTable, Field, money, Notice, PageHeading, SummaryCard, today } from "../components/FarmCommon";

export default function Sales() {
  const { animals, transactions, reports, request, refresh } = useFarm();
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    data.quantity = Number(data.quantity);
    data.unit_price = Number(data.unit_price);
    data.amount = data.amount === "" ? null : Number(data.amount);
    if (data.animal_id) data.animal_id = Number(data.animal_id);
    else data.animal_id = null;
    setNotice("");
    setSaving(true);
    try {
      await request("/transactions", { method: "POST", body: data });
      form.reset();
      form.elements.transaction_date.value = today();
      form.elements.quantity.value = "1";
      form.elements.unit_price.value = "0";
      await refresh();
      setNotice("Transaction saved.");
    } catch (saveError) {
      setNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeTransaction(id) {
    if (!window.confirm("Delete this transaction?")) return;
    try {
      await request(`/transactions/${id}`, { method: "DELETE" });
      await refresh();
    } catch (deleteError) {
      setNotice(deleteError.message);
    }
  }

  return (
    <div className="page-content">
      <PageHeading title="Sales & expenses" description="Record farm income and spending and review your totals." />
      <Notice error>{notice}</Notice>
      {reports && (
        <div className="summary-grid report-grid">
          <SummaryCard label="Milk recorded (all time)" value={`${Number(reports.total_milk_litres).toFixed(1)} L`} />
          <SummaryCard label="Sales recorded" value={money(reports.sales)} />
          <SummaryCard label="Expenses recorded" value={money(reports.expenses)} />
          <SummaryCard label="Net recorded income" value={money(reports.net)} />
          <SummaryCard label="Low-stock items" value={reports.low_stock_count} alert={reports.low_stock_count > 0} />
        </div>
      )}
      <form className="farm-form" onSubmit={submit}>
        <h2>Record a transaction</h2>
        <div className="form-grid">
          <Field label="Type"><select name="kind" defaultValue="sale"><option value="sale">Sale / income</option><option value="expense">Expense</option></select></Field>
          <Field label="Date"><input type="date" name="transaction_date" defaultValue={today()} required /></Field>
          <Field label="Category"><input name="category" required placeholder="Milk, livestock, feed, vet…" /></Field>
          <Field label="Description"><input name="description" required placeholder="What was sold or purchased?" /></Field>
          <Field label="Quantity"><input type="number" name="quantity" min="0" step="0.01" defaultValue="1" required /></Field>
          <Field label="Unit price (KES)"><input type="number" name="unit_price" min="0" step="0.01" defaultValue="0" required /></Field>
          <Field label="Total amount (KES)"><input type="number" name="amount" min="0" step="0.01" placeholder="Optional" /></Field>
          <AnimalSelect animals={animals} required={false} emptyLabel="None" />
        </div>
        <button className="button primary" disabled={saving}>{saving ? "Saving…" : "Save transaction"}</button>
      </form>
      <FarmTable
        columns={["Date", "Type", "Category", "Description", "Related animal", "Amount", "Actions"]}
        emptyMessage="No transactions yet."
        rows={transactions.map((transaction) => (
          <tr key={transaction.id}>
            <td>{transaction.transaction_date}</td><td>{transaction.kind}</td><td>{transaction.category}</td>
            <td>{transaction.description}</td><td>{transaction.animal_id ? animalLabel(animals, transaction.animal_id) : "—"}</td>
            <td>{money(transaction.amount)}</td>
            <td><button className="button danger small" onClick={() => removeTransaction(transaction.id)}>Delete</button></td>
          </tr>
        ))}
      />
    </div>
  );
}
