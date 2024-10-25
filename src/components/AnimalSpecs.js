import React, { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import "./styles/AnimalSpecs.css";
import "./NavBar"

function AnimalSpecs() {
  const { animalId } = useParams();
  const [viewAnimals, setViewAnimals] = useState([]);
  const [showEditModal, setShowEditModal] = useState(false); // State to control modal visibility
  const [editedAnimal, setEditedAnimal] = useState({});; // State to hold the edited animal data

  useEffect(() => {
    fetch('http://127.0.0.1:5000/view_animals')
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      } else {
        return response.json();
      }
    })
      .then((data) => setViewAnimals(data.animals || data)) // Adjust based on your API structure
      .catch((error) => console.error("Error fetching animal data:", error));
  }, []);

  if (!viewAnimals.length) {
    return <div>Loading animals...</div>;
  }

  const selectedAnimal = viewAnimals.find((animal) => animal.id === Number(animalId));

  if (!selectedAnimal) {
    return <div>Kindly wait for the selected Animal to load...</div>;
  }

  const handleEdit = () => {
    setEditedAnimal({ ...selectedAnimal });
    setShowEditModal(true);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setEditedAnimal((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  
const handleFormSubmit = async (e) => {
  e.preventDefault();
  try {
    const formData = { ...editedAnimal };
    formData.birth_date = editedAnimal.birth_date ? editedAnimal.birth_date.toISOString().split('T')[0] : null;
    formData.purchase_date = editedAnimal.purchase_date ? editedAnimal.purchase_date.toISOString().split('T')[0] : null;
    formData.expected_delivery_date = editedAnimal.expected_delivery_date ? editedAnimal.expected_delivery_date.toISOString().split('T')[0] : null;

    const response = await fetch(`http://127.0.0.1:5000/update_animal/${animalId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(formData),
    });
    if (!response.ok) {
      throw new Error("Network response was not ok");
    }
    const data = await response.json();
    console.log("Animal updated:", data);
    setShowEditModal(false); // Close the modal after update attempt
  } catch (error) {
    console.error("Error editing animal data:", error);
  }
};

  const handleModalClose = () => {
    setShowEditModal(false); // Close modal
  };

  return (
    <div>    
      <div className="card mb-3">
        <div className="row g-0">
          <div className="col-md-4">
            <img
              id="images"
              src={selectedAnimal.animal_url}
              className="img-fluid rounded-start"
              alt={selectedAnimal.tag_number}
            />
          </div>
          <div className="col-md-8">
            <div className="card-body">
              <h5 className="card-title">Tag number: {selectedAnimal.tag_number}</h5>
              <p className="card-text">Gender: {selectedAnimal.gender}</p>
              <p className="card-text">Birth Date: {selectedAnimal.birth_date}</p>
              <p className="card-text">Purchase Date: {selectedAnimal.purchase_date}</p>
              <p className="card-text">Vaccination Status: {selectedAnimal.vaccination_status}</p>
              <p className="card-text">Weight: {selectedAnimal.weight}</p>
              <p className="card-text">Breed: {selectedAnimal.breed}</p>
              <p className="card-text">Pregnant: {selectedAnimal.is_pregnant ? 'Yes' : 'No'}</p>
              <p className="card-text">Expected Delivery Date: {selectedAnimal.expected_delivery_date}</p>
              <br />
              <div className="d-grid gap-2 col-4">
                <a href="/" role="button" className="btn btn-secondary">Go Back</a>
                <button onClick={handleEdit} className="btn btn-primary">Edit</button>
              </div>
              <br />
            </div>
          </div>
        </div>
      </div>

      {/* Modal for editing */}
      {showEditModal && (
        <div className="modal">
          <div className="modal-content">
            <span className="close" onClick={handleModalClose}>&times;</span>
            <h2>Edit Animal Details</h2>
            <form onSubmit={handleFormSubmit}>
            <label id="edit-label">
                Tag Number:
                <input
                  id="edit"
                  type="text"
                  name="tag_number"
                  value={editedAnimal?.tag_number || ''}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Gender:
                <input
                  id="edit"
                  type="text"
                  name="gender"
                  value={editedAnimal.gender}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Birth Date:
                <input
                  id="edit"
                  type="date"
                  name="birth_date"
                  value={editedAnimal.birth_date}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Purchase Date:
                <input
                  id="edit"
                  type="date"
                  name="purchase_date"
                  value={editedAnimal.purchase_date}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Vaccination Status:
                <input
                  id="edit"
                  type="text"
                  name="vaccination_status"
                  value={editedAnimal.vaccination_status}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Weight:
                <input
                  id="edit"
                  type="text"
                  name="weight"
                  value={editedAnimal.weight}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Breed:
                <input
                  id="edit"
                  type="text"
                  name="breed"
                  value={editedAnimal.breed}
                  onChange={handleInputChange}
                />
              </label>
              <label id="edit-label">
                Pregnant:
                <select
                  name="is_pregnant"
                  value={editedAnimal.is_pregnant}
                  onChange={handleInputChange}
                >
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label id="edit-label">
                Expected Delivery Date:
                <input
                  id="edit"
                  type="date"
                  name="expected_delivery_date"
                  value={editedAnimal.expected_delivery_date}
                  onChange={handleInputChange}
                />
              </label>
              <br/>
              <div className="d-grid gap-2 col-6 mx-auto">
                <button type="submit" className="btn btn-primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default AnimalSpecs;