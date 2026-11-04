import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useFarm } from "../context/FarmContext";

const links = [
  ["/dashboard", "Dashboard"],
  ["/milkrecords", "Milk records"],
  ["/inventory", "Inventory"],
  ["/feeds", "Feeds"],
  ["/breeding", "Breeding"],
  ["/sales", "Sales"],
  ["/aboutus", "About us"],
  ["/contactus", "Contact us"],
];

export default function FarmNav() {
  const { setToken } = useFarm();
  const navigate = useNavigate();

  function logOut() {
    setToken(null);
    navigate("/login", { replace: true });
  }

  return (
    <header className="farm-header">
      <div className="farm-nav-wrap">
        <NavLink className="farm-brand" to="/dashboard">LAVIPRINA FARM</NavLink>
        <nav className="farm-nav" aria-label="Main navigation">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? "farm-nav-link active" : "farm-nav-link"}>
              {label}
            </NavLink>
          ))}
          <button type="button" className="farm-nav-link logout-button" onClick={logOut}>Log out</button>
        </nav>
      </div>
    </header>
  );
}
