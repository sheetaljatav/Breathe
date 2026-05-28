import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { ensureCsrf } from "./api/client";
import { useMe, useOrgs } from "./api/hooks";
import { Layout } from "./routes/Layout";
import { Login } from "./routes/Login";
import { Overview } from "./routes/Overview";
import { Imports } from "./routes/Imports";
import { Queue } from "./routes/Queue";
import { QueueDetail } from "./routes/QueueDetail";
import { Settings } from "./routes/Settings";
import { Spinner } from "./components/Spinner";
import { useUiStore } from "./store/ui";

export function App() {
  const qc = useQueryClient();
  const me = useMe();
  const setOrgId = useUiStore((s) => s.setOrgId);
  const orgId = useUiStore((s) => s.orgId);
  const orgs = useOrgs();

  useEffect(() => { void ensureCsrf(); }, []);

  // Global 401 handler: when any API call comes back unauthorized, drop the
  // user back to /login by invalidating the `me` query. The render branch
  // below sees me.isError and renders the unauthenticated routes.
  useEffect(() => {
    const onUnauthorized = () => {
      useUiStore.getState().setOrgId(null);
      // Setting me to null is enough — App re-renders and shows login routes.
      // Calling invalidateQueries here would kick off a refetch that gets 401
      // again, re-entering this handler and creating an infinite request loop.
      qc.setQueryData(["me"], null);
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, [qc]);

  // If we have a user but the stored orgId isn't in their memberships, fall
  // back to their first membership.
  useEffect(() => {
    if (me.data && orgs.data) {
      const ids = new Set(orgs.data.map((o) => o.id));
      if (!orgId || !ids.has(orgId)) {
        const first = me.data.memberships[0]?.organization.id ?? null;
        if (first) setOrgId(first);
      }
    }
  }, [me.data, orgs.data, orgId, setOrgId]);

  if (me.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (me.isError || !me.data) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<RedirectToLogin />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/" replace />} />
      <Route element={<Layout user={me.data} />}>
        <Route path="/" element={<Overview />} />
        <Route path="/imports" element={<Imports />} />
        <Route path="/queue" element={<Queue />} />
        <Route path="/queue/:id" element={<QueueDetail />} />
        <Route path="/settings/*" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function RedirectToLogin() {
  const loc = useLocation();
  return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
}
