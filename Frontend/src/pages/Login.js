import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useFarm } from "../context/FarmContext";
import { Field, Notice } from "../components/FarmCommon";

export default function Login() {
  const { request, setToken } = useFarm();
  const navigate = useNavigate();
  const [signup, setSignup] = useState(false);
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const body = signup
      ? { username: values.username, email: values.email, password: values.password }
      : { identifier: values.email, password: values.password };
    setNotice("");
    setSubmitting(true);
    try {
      const data = await request(signup ? "/signup" : "/login", { method: "POST", body });
      setToken(data.token);
      navigate("/dashboard", { replace: true });
    } catch (authError) {
      setNotice(authError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <Link className="login-brand" to="/">LAVIPRINA FARM</Link>
        <h1>{signup ? "Create your account" : "Welcome back"}</h1>
        <p>{signup ? "Set up an account to manage your farm records." : "Log in to manage your herd and farm records."}</p>
        <Notice error>{notice}</Notice>
        {signup && <Field label="Username"><input name="username" autoComplete="username" required /></Field>}
        <Field label={signup ? "Email" : "Email or username"}>
          <input name="email" type={signup ? "email" : "text"} autoComplete="username" required />
        </Field>
        <Field label="Password"><input name="password" type="password" minLength="8" autoComplete={signup ? "new-password" : "current-password"} required /></Field>
        <button className="button primary login-submit" disabled={submitting}>{submitting ? "Please wait…" : signup ? "Create account" : "Log in"}</button>
        <button className="text-button" type="button" onClick={() => { setSignup((value) => !value); setNotice(""); }}>
          {signup ? "I already have an account" : "Create an account"}
        </button>
      </form>
    </main>
  );
}
