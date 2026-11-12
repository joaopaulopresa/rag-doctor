import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { Brand } from "../components/Brand";

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = new URLSearchParams(location.search).get("next");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await signIn(email, password);
      navigate(next ?? (user.role === "admin" ? "/admin/doctor" : "/"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="panel pad login-card stack" onSubmit={submit}>
        <Brand />
        <h1>Sign in</h1>
        <p className="muted">The chat is open to everyone. Signing in as an admin opens the lab and the doctor.</p>
        <label className="field">
          E-mail
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="field">
          Password
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="notice error">{error}</p>}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Signing in" : "Sign in"}
        </button>
        <p className="faint">Demo admin: admin@ragdoctor.demo, password doctor-admin.</p>
      </form>
    </div>
  );
}
