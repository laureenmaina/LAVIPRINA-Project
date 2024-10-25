import React, { useState } from "react";
import "./styles/Register.css";

function Register() {
    const [tagNumber, setTagNumber] = useState("");
    const [gender, setGender] = useState("");
    const [birthDate, setBirthDate] = useState("");
    const [weight, setWeight] = useState("");
    const [breed, setBreed] = useState("");
    const [image, setImage] = useState(null);

    const handleRegistration = async (event) => {
        event.preventDefault();
        const animalData = new FormData();
        animalData.append("tagNumber", tagNumber);
        animalData.append("gender", gender);
        animalData.append("birthDate", birthDate);
        animalData.append("weight", weight);
        animalData.append("breed", breed);
        if (image) {
            animalData.append("image", image);  // Append image file to the FormData object
        }

        try {
            const response = await fetch("http://127.0.0.1:5000/register", {
                method: "POST",
                body: animalData,  // Send FormData to the backend
            });

            if (!response.ok) {
                throw new Error("Network response was not ok");
            }

            alert("Animal registered successfully!");
        } catch (error) {
            console.error("Error during registration:", error);
            alert("Failed to register animal. Please try again.");
        }
    };

    return (
        <div className="container mt-4">
            <h2 className="text-center">Animal Registration Form</h2>
            <form onSubmit={handleRegistration} encType="multipart/form-data"> {/* Added encType for file upload */}
                <div className="mb-3">
                    <label htmlFor="tagNumber" className="form-label">Tag Number:</label>
                    <input 
                        type="text" 
                        className="form-control" 
                        id="tagNumber" 
                        value={tagNumber}
                        onChange={(e) => setTagNumber(e.target.value)}
                    />
                </div>
                <div className="mb-3">
                    <label htmlFor="gender" className="form-label">Gender:</label>
                    <input 
                        type="text" 
                        className="form-control" 
                        id="gender" 
                        value={gender}
                        onChange={(e) => setGender(e.target.value)}
                    />
                </div>
                <div className="mb-3">
                    <label htmlFor="birthDate" className="form-label">Birth Date:</label>
                    <input 
                        type="date" 
                        className="form-control" 
                        id="birthDate"
                        value={birthDate}
                        onChange={(e) => setBirthDate(e.target.value)}
                    />
                </div>
                <div className="mb-3">
                    <label htmlFor="weight" className="form-label">Weight:</label>
                    <input 
                        type="text" 
                        className="form-control" 
                        id="weight" 
                        value={weight}
                        onChange={(e) => setWeight(e.target.value)}
                    />
                </div>
                <div className="mb-3">
                    <label htmlFor="breed" className="form-label">Breed:</label>
                    <input 
                        type="text" 
                        className="form-control" 
                        id="breed" 
                        value={breed}
                        onChange={(e) => setBreed(e.target.value)}
                    />
                </div>
                <div className="mb-3">
                    {/* Image upload field */}
                    <label htmlFor="image" className="form-label">Upload Image:</label>
                    <input 
                        type="file" 
                        className="form-control" 
                        id="image" 
                        accept="image/*" 
                        onChange={(e) => setImage(e.target.files[0])} // Get selected file
                    />
                </div>
                <div className="d-grid gap-2 col-6 mx-auto">
                    <button className="btn btn-primary" type="submit">Register</button>
                </div>
            </form>
        </div>
    );
}

export default Register;
