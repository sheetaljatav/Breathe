import { type FormEvent, useState } from "react";

import { ApiError } from "@/api/client";
import { useLogin } from "@/api/hooks";

const DEMO = [
  { label: "Acme (analyst)", email: "analyst@acme.test",   password: "breathe" },
  { label: "Acme (admin)",   email: "admin@acme.test",     password: "breathe" },
  { label: "Globex (analyst)", email: "analyst@globex.test", password: "breathe" },
];

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email, password });
  };

  return (
    <div className="min-h-screen bg-surface-subtle flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8">
          <div className="font-mono text-sm tracking-tight text-ink-muted">breathe-esg</div>
          <h1 className="text-xl font-semibold mt-1">Sign in</h1>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-ink-muted mb-1" htmlFor="email">Email</label>
            <input
              id="email" className="input w-full" type="email"
              value={email} onChange={(e) => setEmail(e.target.value)}
              autoComplete="username" autoFocus required
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink-muted mb-1" htmlFor="password">Password</label>
            <input
              id="password" className="input w-full" type="password"
              value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" required
            />
          </div>

          {login.isError && (
            <div className="text-sm text-status-rejected">
              {(login.error as ApiError)?.message ?? "Sign-in failed"}
            </div>
          )}

          <button type="submit" className="btn-primary w-full justify-center" disabled={login.isPending}>
            {login.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="mt-10 pt-6 border-t border-surface-border">
          <div className="text-xs font-medium uppercase tracking-wider text-ink-subtle mb-2">
            Demo accounts (password: <span className="font-mono">breathe</span>)
          </div>
          <div className="space-y-1">
            {DEMO.map((d) => (
              <button
                key={d.email}
                className="block w-full text-left text-sm font-mono px-2 py-1 rounded hover:bg-surface-muted"
                onClick={() => { setEmail(d.email); setPassword(d.password); }}
              >
                <span className="text-ink-subtle mr-2">{d.label}</span>
                {d.email}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
