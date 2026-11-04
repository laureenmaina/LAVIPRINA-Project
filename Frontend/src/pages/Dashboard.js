import React, { useMemo, useState } from "react";
import { useFarm } from "../context/FarmContext";
import { Field, Notice, PageHeading, SummaryCard, today } from "../components/FarmCommon";

const initialAnimal = {
  name: "",
  tagnumber: "",
  type: "dairycow",
  breed: "",
  sex: "Female",
  birthdate: "",
  currentweight: "",
  status: "Milking",
  penorpaddock: "",
  sire: "",
  dam: "",
  lastvaccinationdate: "",
  nextvaccinationdate: "",
  averagemilk: "",
  expectedbirthdate: "",
  notes: "",
  photo: "",
};

function isDairyCow(animal) {
  return ["cow", "dairycow"].includes(String(animal.type || "").toLowerCase())
    && String(animal.sex || "").toLowerCase() === "female";
}

function AnimalForm({ animal, onClose, onSaved }) {
  const { request } = useFarm();
  const [values, setValues] = useState({ ...initialAnimal, ...(animal || {}) });
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);

  function update(event) {
    const { name, value } = event.target;
    setValues((previous) => ({ ...previous, [name]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    setNotice("");
    if (values.lastvaccinationdate && values.lastvaccinationdate <= values.birthdate) {
      setNotice("Last vaccination date must be after the birthdate.");
      return;
    }
    if (values.nextvaccinationdate && values.nextvaccinationdate < today()
      && values.nextvaccinationdate !== animal?.nextvaccinationdate) {
      setNotice("Next vaccination date cannot be in the past.");
      return;
    }
    if (values.type === "cow" && values.sex === "Male" && values.status.toLowerCase() === "milking") {
      setNotice("A male cow cannot have the status 'Milking'.");
      return;
    }

    const payload = {
      ...values,
      currentweight: Number(values.currentweight),
      averagemilk: values.averagemilk === "" ? null : Number(values.averagemilk),
      weights: animal?.weights || [{ d: today(), w: Number(values.currentweight) }],
    };
    setSaving(true);
    try {
      await request(animal ? `/animals/${animal.id}` : "/animals", {
        method: animal ? "PUT" : "POST",
        body: payload,
      });
      await onSaved();
      onClose();
    } catch (saveError) {
      setNotice(saveError.message);
    } finally {
      setSaving(false);
    }
  }

  async function selectPhoto(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const image = new Image();
      image.onload = () => {
        const scale = Math.min(1, 600 / image.width);
        const canvas = document.createElement("canvas");
        canvas.width = image.width * scale;
        canvas.height = image.height * scale;
        canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
        setValues((previous) => ({ ...previous, photo: canvas.toDataURL("image/jpeg", 0.8) }));
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="farm-form animal-form" onSubmit={submit}>
        <div className="modal-heading">
          <h2>{animal ? `Edit ${animal.name}` : "Register an animal"}</h2>
          <button type="button" className="button secondary" onClick={onClose}>Close</button>
        </div>
        <Notice error>{notice}</Notice>
        <div className="form-grid">
          <Field label="Name"><input name="name" value={values.name || ""} onChange={update} required /></Field>
          <Field label="Tag number"><input name="tagnumber" value={values.tagnumber || ""} onChange={update} required /></Field>
          <Field label="Type">
            <select name="type" value={values.type || "dairycow"} onChange={update}>
              <option value="dairycow">Dairy cow</option><option value="cow">Cow</option><option value="sheep">Sheep</option>
            </select>
          </Field>
          <Field label="Breed"><input name="breed" value={values.breed || ""} onChange={update} required /></Field>
          <Field label="Sex">
            <select name="sex" value={values.sex || "Female"} onChange={update}><option>Female</option><option>Male</option></select>
          </Field>
          <Field label="Birthdate"><input type="date" name="birthdate" value={values.birthdate || ""} onChange={update} required /></Field>
          <Field label="Weight (kg)"><input type="number" min="0.1" step="0.1" name="currentweight" value={values.currentweight || ""} onChange={update} required /></Field>
          <Field label="Status">
            <select name="status" value={values.status || "Growing"} onChange={update}>
              {["Milking", "Dry", "Pregnant", "Lactating", "Growing", "Breeding", "Sick", "For sale"].map((status) => <option key={status}>{status}</option>)}
            </select>
          </Field>
          <Field label="Pen or paddock"><input name="penorpaddock" value={values.penorpaddock || ""} onChange={update} /></Field>
          <Field label="Sire (father tag)"><input name="sire" value={values.sire || ""} onChange={update} /></Field>
          <Field label="Dam (mother tag)"><input name="dam" value={values.dam || ""} onChange={update} /></Field>
          <Field label="Last vaccination"><input type="date" name="lastvaccinationdate" value={values.lastvaccinationdate || ""} onChange={update} /></Field>
          <Field label="Next vaccination due"><input type="date" min={today()} name="nextvaccinationdate" value={values.nextvaccinationdate || ""} onChange={update} /></Field>
          <Field label="Average milk (litres/day)"><input type="number" min="0" step="0.1" name="averagemilk" value={values.averagemilk || ""} onChange={update} /></Field>
          <Field label="Expected birth date"><input type="date" name="expectedbirthdate" value={values.expectedbirthdate || ""} onChange={update} /></Field>
          <Field label="Photo"><input type="file" accept="image/*" onChange={selectPhoto} /></Field>
          <Field label="Notes" className="wide-field"><textarea name="notes" rows="3" value={values.notes || ""} onChange={update} /></Field>
        </div>
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={onClose}>Cancel</button>
          <button className="button primary" disabled={saving}>{saving ? "Saving…" : "Save animal"}</button>
        </div>
      </form>
    </div>
  );
}

export default function Dashboard() {
  const { animals, request, refresh, loading } = useFarm();
  const [search, setSearch] = useState("");
  const [species, setSpecies] = useState("");
  const [sort, setSort] = useState("name");
  const [editing, setEditing] = useState(undefined);
  const [selected, setSelected] = useState(null);
  const [notice, setNotice] = useState("");
  const [weight, setWeight] = useState("");
  const [weighDate, setWeighDate] = useState(today());
  const dairyCows = animals.filter(isDairyCow);
  const filteredAnimals = useMemo(() => {
    const query = search.trim().toLowerCase();
    return animals.filter((animal) => {
      const matchesSpecies = !species
        || (species === "dairycow" ? isDairyCow(animal) : animal.type === species);
      return matchesSpecies && `${animal.name} ${animal.tagnumber} ${animal.breed}`.toLowerCase().includes(query);
    }).sort((left, right) => {
      if (sort === "currentweight") return Number(right.currentweight) - Number(left.currentweight);
      if (sort === "birthdate") return String(left.birthdate).localeCompare(String(right.birthdate));
      return String(left[sort] || "").localeCompare(String(right[sort] || ""));
    });
  }, [animals, search, sort, species]);

  async function deleteAnimal(animal) {
    if (!window.confirm(`Delete ${animal.name || animal.tagnumber}? This cannot be undone.`)) return;
    try {
      await request(`/animals/${animal.id}`, { method: "DELETE" });
      setSelected(null);
      await refresh();
      setNotice("Animal deleted.");
    } catch (deleteError) {
      setNotice(deleteError.message);
    }
  }

  async function logWeight() {
    const amount = Number(weight);
    if (!selected || !Number.isFinite(amount) || amount <= 0) {
      setNotice("Enter a valid weight greater than zero.");
      return;
    }
    const weights = [...(selected.weights || []), { d: weighDate || today(), w: amount }]
      .sort((left, right) => String(left.d).localeCompare(String(right.d)));
    try {
      const result = await request(`/animals/${selected.id}`, {
        method: "PUT",
        body: { weights, currentweight: weights[weights.length - 1].w },
      });
      setSelected(result.animal);
      setWeight("");
      await refresh();
      setNotice("Weight logged.");
    } catch (weightError) {
      setNotice(weightError.message);
    }
  }

  function exportBackup() {
    const link = document.createElement("a");
    const url = URL.createObjectURL(new Blob([JSON.stringify(animals, null, 2)], { type: "application/json" }));
    link.href = url;
    link.download = `herd-backup-${today()}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return (
    <div className="page-content">
      <PageHeading
        title="Know every animal in your herd."
        description="Manage animal profiles, health details, weights and milk production."
        action={<button className="button primary" onClick={() => setEditing(null)}>Add animal</button>}
      />
      <Notice error>{notice}</Notice>
      <div className="summary-grid">
        <SummaryCard label="Animals in total" value={animals.length} />
        <SummaryCard label="Dairy cows" value={dairyCows.length} />
        <SummaryCard label="Sheep" value={animals.filter((animal) => animal.type === "sheep").length} />
        <SummaryCard label="Daily milk average" value={`${dairyCows.reduce((sum, animal) => sum + Number(animal.averagemilk || 0), 0).toFixed(1)} L`} />
        <SummaryCard label="Vaccinations due in 14 days" value={animals.filter((animal) => animal.nextvaccinationdate && animal.nextvaccinationdate <= new Date(Date.now() + 14 * 864e5).toISOString().slice(0, 10)).length} alert />
      </div>
      <section className="content-section">
        <div className="section-heading">
          <h2>Herd records</h2>
          <button className="button secondary" type="button" onClick={exportBackup}>Export backup</button>
        </div>
        <div className="toolbar">
          <input type="search" aria-label="Search animals" placeholder="Search by name, tag or breed" value={search} onChange={(event) => setSearch(event.target.value)} />
          <select aria-label="Filter by species" value={species} onChange={(event) => setSpecies(event.target.value)}>
            <option value="">All animals</option><option value="cow">Cows</option><option value="sheep">Sheep</option><option value="dairycow">Dairy cows</option>
          </select>
          <select aria-label="Sort animals" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="name">Sort by name</option><option value="tagnumber">Sort by tag</option><option value="birthdate">Sort by age</option><option value="currentweight">Sort by weight</option>
          </select>
        </div>
        {loading && animals.length === 0 ? <p>Loading animals…</p> : (
          <div className="animal-grid">
            {filteredAnimals.map((animal) => (
              <button className="animal-card" key={animal.id} onClick={() => setSelected(animal)}>
                <img src={animal.photo || `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="100%" height="100%" fill="#dfe8df"/><text x="50%" y="55%" text-anchor="middle" font-size="80" fill="#36583b">${(animal.name || "?")[0]}</text></svg>`)}`} alt={`${animal.name}, ${animal.breed}`} />
                <span className="animal-card-body">
                  <strong>{animal.name}</strong>
                  <span>Tag {animal.tagnumber} · {animal.breed}</span>
                  <span className="animal-tag">{isDairyCow(animal) ? "Dairy cow" : animal.type}</span>
                </span>
              </button>
            ))}
            {!filteredAnimals.length && <p className="empty-state">{animals.length ? "No animals match your search." : "No animals registered yet. Add your first animal to get started."}</p>}
          </div>
        )}
      </section>
      {selected && (
        <div className="modal-backdrop" role="presentation">
          <section className="farm-form detail-panel" role="dialog" aria-modal="true" aria-labelledby="animal-detail-title">
            <div className="modal-heading">
              <h2 id="animal-detail-title">{selected.name}</h2>
              <button className="button secondary" onClick={() => setSelected(null)}>Close</button>
            </div>
            <dl className="animal-details">
              {[
                ["Tag number", selected.tagnumber], ["Type", selected.type], ["Breed", selected.breed],
                ["Sex", selected.sex], ["Birthdate", selected.birthdate], ["Weight", `${selected.currentweight} kg`],
                ["Status", selected.status], ["Pen or paddock", selected.penorpaddock || "—"],
                ["Sire", selected.sire || "—"], ["Dam", selected.dam || "—"],
                ["Last vaccination", selected.lastvaccinationdate || "—"],
                ["Next vaccination", selected.nextvaccinationdate || "—"],
                ["Average milk", isDairyCow(selected) ? `${selected.averagemilk || "—"} L/day` : "—"],
                ["Expected birth", selected.expectedbirthdate || "—"],
              ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
            </dl>
            {selected.notes && <p className="notes-panel">{selected.notes}</p>}
            <section className="weight-entry">
              <h3>Weight history</h3>
              {(selected.weights || []).length > 0 ? (
                <ul>
                  {selected.weights.map((entry, index) => <li key={`${entry.d}-${index}`}>{entry.d}: {entry.w} kg</li>)}
                </ul>
              ) : <p>No weight history available.</p>}
              <div className="weight-controls">
                <label className="form-field">Weight (kg)<input type="number" min="0.1" step="0.1" value={weight} onChange={(event) => setWeight(event.target.value)} /></label>
                <label className="form-field">Date<input type="date" value={weighDate} onChange={(event) => setWeighDate(event.target.value)} /></label>
                <button className="button secondary" onClick={logWeight}>Log weight</button>
              </div>
            </section>
            <div className="form-actions">
              <button className="button danger" onClick={() => deleteAnimal(selected)}>Delete animal</button>
              <button className="button primary" onClick={() => { setEditing(selected); setSelected(null); }}>Edit record</button>
            </div>
          </section>
        </div>
      )}
      {editing !== undefined && <AnimalForm animal={editing} onClose={() => setEditing(undefined)} onSaved={refresh} />}
    </div>
  );
}
