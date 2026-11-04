import React, { useState } from "react";
import { useFarm } from "../context/FarmContext";
import { FarmTable, Field, money, Notice, PageHeading } from "./FarmCommon";

export default function InventoryManager({ feedsOnly = false }) {
  const { inventory, request, refresh } = useFarm();
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const items = feedsOnly ? inventory.filter((item) => item.category === "feed") : inventory;

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    ["quantity", "reorder_level", "unit_cost"].forEach((key) => { data[key] = Number(data[key]); });
    if (feedsOnly) data.category = "feed";
    setNotice("");
    setSaving(true);
    try {
      await request("/inventory", { method: "POST", body: data });
      form.reset();
      form.elements.unit.value = "kg";
      ["quantity", "reorder_level", "unit_cost"].forEach((key) => { form.elements[key].value = "0"; });
      await refresh();
      setNotice(feedsOnly ? "Feed item added." : "Inventory item added.");
    } catch (saveError) {
      setNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function updateStock(item) {
    const value = window.prompt(`New stock quantity for ${item.name} (${item.unit}):`, item.quantity);
    if (value === null) return;
    if (!value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0) {
      setNotice("Enter a valid non-negative quantity.");
      return;
    }
    try {
      await request(`/inventory/${item.id}`, { method: "PUT", body: { quantity: Number(value) } });
      await refresh();
      setNotice("Stock updated.");
    } catch (updateError) {
      setNotice(updateError.message);
    }
  }

  async function removeItem(item) {
    if (!window.confirm(`Delete ${item.name} from inventory?`)) return;
    try {
      await request(`/inventory/${item.id}`, { method: "DELETE" });
      await refresh();
    } catch (deleteError) {
      setNotice(deleteError.message);
    }
  }

  return (
    <div className="page-content">
      <PageHeading
        title={feedsOnly ? "Feeds" : "Farm inventory"}
        description={feedsOnly
          ? "Track feed and fodder stock, costs and reorder levels."
          : "Manage feed, medicine, supplies and other farm inventory."}
      />
      <Notice error>{notice}</Notice>
      <form className="farm-form" onSubmit={submit}>
        <h2>{feedsOnly ? "Add feed" : "Add inventory item"}</h2>
        <div className="form-grid">
          <Field label="Item name"><input name="name" required placeholder={feedsOnly ? "e.g. Dairy meal" : "e.g. Mineral supplements"} /></Field>
          {!feedsOnly && (
            <Field label="Category">
              <select name="category" defaultValue="feed">
                <option value="feed">Feed / fodder</option><option value="medicine">Medicine</option>
                <option value="supplies">Supplies</option><option value="other">Other</option>
              </select>
            </Field>
          )}
          <Field label="Quantity"><input type="number" name="quantity" min="0" step="0.01" defaultValue="0" required /></Field>
          <Field label="Unit"><input name="unit" defaultValue="kg" required placeholder="kg, bags, litres" /></Field>
          <Field label="Low-stock threshold"><input type="number" name="reorder_level" min="0" step="0.01" defaultValue="0" required /></Field>
          <Field label="Unit cost (KES)"><input type="number" name="unit_cost" min="0" step="0.01" defaultValue="0" required /></Field>
        </div>
        <button className="button primary" disabled={saving}>{saving ? "Saving…" : feedsOnly ? "Add feed" : "Add inventory item"}</button>
      </form>
      <FarmTable
        columns={["Item", "Category", "Stock", "Reorder at", "Unit cost", "Status", "Actions"]}
        emptyMessage={feedsOnly ? "No feed items yet." : "No inventory items yet."}
        rows={items.map((item) => (
          <tr key={item.id}>
            <td>{item.name}</td><td>{item.category}</td><td>{Number(item.quantity)} {item.unit}</td>
            <td>{Number(item.reorder_level)} {item.unit}</td><td>{money(item.unit_cost)}</td>
            <td className={item.low_stock ? "low-stock" : ""}>{item.low_stock ? "Low stock" : "In stock"}</td>
            <td className="action-cell">
              <button className="button secondary small" onClick={() => updateStock(item)}>Update stock</button>
              <button className="button danger small" onClick={() => removeItem(item)}>Delete</button>
            </td>
          </tr>
        ))}
      />
    </div>
  );
}
