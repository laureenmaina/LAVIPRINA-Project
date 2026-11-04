import React from "react";
import { PageHeading } from "../components/FarmCommon";

export default function Contactus() {
  return (
    <div className="page-content">
      <PageHeading title="Contact us" description="Get in touch with Laviprina Farm for visits, orders or general enquiries." />
      <section className="information-card contact-card">
        <div>
          <h2>Visit the farm</h2>
          <p>Farm gate open Monday to Saturday, 7:00 am–5:00 pm.</p>
        </div>
        <div>
          <h2>Call us</h2>
          <p><a href="tel:+254715299134">+254 715 299 134</a></p>
        </div>
        <div>
          <h2>Email</h2>
          <p><a href="mailto:info@laviprina.com">info@laviprina.com</a></p>
        </div>
      </section>
    </div>
  );
}
