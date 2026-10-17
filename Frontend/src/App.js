import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import DashBoard from './components/DashBoard';
import AnimalSpecs from './components/AnimalSpecs';
import Navbar from './components/NavBar';
import Home from './components/Home';
import Register from './components/Register';


const App = () => {
    return (
        <Router>
            <Routes>
                <Route path='/dashboard' element={<DashBoard />} />
                <Route path='/animals/:animalId' element={<AnimalSpecs />} />
                <Route path='/navbar' element={<Navbar />} />
                <Route path='/' element={<Home />} />
                <Route path='/register' element={<Register />} />

            </Routes>
        </Router>
    );
};

export default App;
