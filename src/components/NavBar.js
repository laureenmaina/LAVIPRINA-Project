import React from 'react';
import "./styles/NavBar.css"; // Ensure the path is correct
import { Link} from 'react-router-dom';
import Logo from './styles/logo.jpg';


function Navbar() {

  return (
    <nav className="navbar">
      <div className="navbar-left">
        <img src={Logo} alt="Laviprina logo" className="laviprina-logo" />
        <Link to="/" className="brand">LAVIPRINA FARM</Link>
      </div>
      <div className="navbar-right">
       
          <>
            <Link to="/register" className="link">Regiter Animal</Link>
            <Link to="/login" className="link">Log In</Link>
          </>
     
      </div>
    </nav>
  );
}

export default Navbar;