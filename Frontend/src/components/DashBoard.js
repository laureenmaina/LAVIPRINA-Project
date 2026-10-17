import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import "./styles/DashBoard.css";
// import  { useAuth } from "./context/AuthContext";
import Navbar from "./NavBar"; 

function DashBoard() {
  const [animals, setAnimals] = useState([]);

  useEffect(() => {
    fetch("http://127.0.0.1:5000/view_animals")  
      .then((response) => {
        if (!response.ok) {
          throw new Error("Failed to fetch data");
        }
        return response.json();
      })
      .then((data) => setAnimals(data))  
      .catch((error) => {
        console.error("Error fetching the data:", error);
      });
}, []);


  // Delete animal
  // function deleteAnimal(id) {
  //   setAnimals((prevanimals) => prevanimals.filter((animal) => animal.id !== id));
  //   fetch(`http://localhost:3001/animals/${id}`, {
  //     method: "DELETE",
  //     headers: {
  //       "Content-Type": "application/json",
  //     },
  //   })
  //     .then((response) => response.json())
  //     .then((data) => console.log("Deleted animal"));
  // }

  // function deleteAnimal(id) {
  //   // Optimistically update state
  //   setAnimals((prevanimals) => prevanimals.filter((animal) => animal.id !== id));

  //   // Simulate DELETE request (make sure you have an API endpoint)
  //   fetch(`http://localhost:3001/animals/${id}`, { // Update with your actual API endpoint
  //     method: "DELETE",
  //     headers: {
  //       "Content-Type": "application/json",
  //     },
  //   })
  //     .then((response) => {
  //       if (!response.ok) {
  //         throw new Error("Network response was not ok");
  //       }
  //       return response.json();
  //     })
  //     .then(() => console.log("Deleted animal"))
  //     .catch((error) => console.error("Error deleting animal:", error));
  // }

  
  return (
    <div className="home">
        <Navbar />
    <div className="bg-success">
      <div className="row">
        {animals && animals.length > 0 ? (
          animals.map((animal) => (
            <div className="col-sm-3 mb-3 mb-sm-2" key={animal.id}>
              <div className="card">
                <Link to={`/animals/${animal.id}`}>
                  <img id="all-images" src={animal.animal_url} className="card-img-top img-thumbnail" alt={animal.species} />
                  <div className="card-body">
                    <h5 className="text-black card-title text-center fs-4">Tag number: {animal.tag_number}</h5>
                    <h5 className="text-black card-title text-center fs-4">Gender: {animal.gender}</h5>
                    <p className="text-black text-center fs-4">Weight: {animal.weight}</p>
                    <p className="text-black text-center fs-4">Breed: {animal.breed}</p>
                  </div>
                </Link>
              </div>
            </div>
          ))
        ) : (
          <p className="text-center fs-4">No animals available</p>  // Fallback message
        )}
      </div>
    </div>
    </div>
  );
  
}

export default DashBoard;