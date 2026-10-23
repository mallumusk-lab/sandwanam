import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext.jsx";
import { useDocumentTitle } from "../../hooks/useAsync.js";
import { homePath } from "../../lib/permissions.js";
import { BrandMark } from "../../ui/AppShell.jsx";
import { Button, ThemeToggle } from "../../ui/controls.jsx";
import { PasswordField, TextField } from "../../ui/fields.jsx";
import { Banner, Card } from "../../ui/surfaces.jsx";

export default function LoginPage() {
  useDocumentTitle("Sign in");
  const { status, user, notice, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(false);

  if (status === "signed-in") return <Navigate to={homePath(user)} replace />;

  const submit = async (event) => {
    event.preventDefault();
    if (pending) return;
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setPending(true);
    setError(null);
    try {
      const signedIn = await login(username.trim(), password);
      const from = location.state?.from?.pathname;
      navigate(signedIn.must_change_password ? "/account" : from && from !== "/login" ? from : homePath(signedIn), {
        replace: true,
      });
    } catch (err) {
      setError(err.message);
      setPassword("");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="auth-page">
      <ThemeToggle className="theme-corner" />
      <main className="auth-card">
        <div className="brand">
          <BrandMark />
          <span>Gold Loan Desk</span>
        </div>
        <Card title="Sign in" headingLevel={1}>
          <form className="stack" onSubmit={submit} noValidate>
            {notice && !error ? <Banner tone="info">{notice}</Banner> : null}
            {error ? <Banner tone="danger">{error}</Banner> : null}
            <TextField
              label="Username"
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
            <PasswordField
              label="Password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" variant="primary" block loading={pending}>
              Sign in
            </Button>
            <p className="field-hint">Forgot your password? Ask your SuperAdmin to issue a temporary one.</p>
          </form>
        </Card>
      </main>
    </div>
  );
}
