import React from "react";
import { PageHeading } from "../components/FarmCommon";

export default function Aboutus() {
  return (
    <div className="page-content">
      <PageHeading title="About Laviprina Farm" description="A family-focused dairy and sheep farm built around healthy animals and thoughtful care." />
      <section className="information-card">
        <h2>Our farm</h2>
        <p>
          Laviprina Farm raises dairy cattle and sheep, bringing together responsible
          animal care and practical farm management. Our herd records help us keep
          track of each animal's health, breeding, weight and productivity.
        </p>
        <h2>What we do</h2>
        <p>
          We produce fresh milk and raise sheep for lamb and wool. We work to keep
          accurate records, provide attentive care and make farm information easier
          to manage every day.
        </p>
      </section>
    </div>
  );
}
