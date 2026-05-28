import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { useFactors, useLookups, useUnits } from "@/api/hooks";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { fmtDate } from "@/lib/format";

export function Settings() {
  return (
    <>
      <PageHeader title="Settings" subtitle="Reference data used for normalization and emissions calculations" />
      <div className="px-6 pt-4">
        <nav className="flex gap-1 border-b border-surface-border">
          <Tab to="factors">Emission factors</Tab>
          <Tab to="lookups">Lookups</Tab>
          <Tab to="units">Canonical units</Tab>
        </nav>
      </div>
      <div className="p-6">
        <Routes>
          <Route index element={<Navigate to="factors" replace />} />
          <Route path="factors" element={<Factors />} />
          <Route path="lookups" element={<Lookups />} />
          <Route path="units" element={<Units />} />
        </Routes>
      </div>
    </>
  );
}

function Tab({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "px-3 py-2 text-sm border-b-2 -mb-px transition-colors",
          isActive
            ? "border-ink text-ink"
            : "border-transparent text-ink-muted hover:text-ink",
        ].join(" ")
      }
    >
      {children}
    </NavLink>
  );
}

function Factors() {
  const q = useFactors();
  if (q.isLoading) return <Spinner />;
  return (
    <div className="bg-white border border-surface-border rounded">
      <table className="w-full">
        <thead>
          <tr className="border-b border-surface-border">
            <th className="th">Category</th>
            <th className="th">Scope</th>
            <th className="th">Region</th>
            <th className="th">Year</th>
            <th className="th">Unit</th>
            <th className="th text-right">kg CO₂e / unit</th>
            <th className="th">Source</th>
            <th className="th">Effective</th>
          </tr>
        </thead>
        <tbody>
          {q.data?.results.map((f) => (
            <tr key={f.id} className="border-b last:border-0 border-surface-border">
              <td className="td">{f.category.label}</td>
              <td className="td font-mono">S{f.category.scope}</td>
              <td className="td font-mono uppercase">{f.region}</td>
              <td className="td num">{f.year}</td>
              <td className="td font-mono">{f.unit.code}</td>
              <td className="td num text-right">{f.kg_co2e_per_unit}</td>
              <td className="td text-ink-muted text-xs">{f.source}</td>
              <td className="td font-mono text-xs">{fmtDate(f.effective_from)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="p-3 text-xs text-ink-subtle border-t border-surface-border">
        Factors are seeded via fixtures and pinned per ActivityRecord at calculation time. See TRADEOFFS for why admin editing is not exposed in this UI.
      </div>
    </div>
  );
}

function Lookups() {
  const q = useLookups();
  if (q.isLoading) return <Spinner />;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white border border-surface-border rounded">
        <div className="px-3 h-10 border-b border-surface-border flex items-center font-medium text-sm">
          SAP plant codes
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="th">Code</th>
              <th className="th">Facility</th>
              <th className="th">Country</th>
            </tr>
          </thead>
          <tbody>
            {q.data?.plant_codes.map((p) => (
              <tr key={p.id} className="border-b last:border-0 border-surface-border">
                <td className="td font-mono">{p.code}</td>
                <td className="td">{p.facility_name}</td>
                <td className="td font-mono">{p.country}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-white border border-surface-border rounded">
        <div className="px-3 h-10 border-b border-surface-border flex items-center font-medium text-sm">
          Airports
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="th">IATA</th>
              <th className="th">Airport</th>
              <th className="th">City / Country</th>
            </tr>
          </thead>
          <tbody>
            {q.data?.airports.map((a) => (
              <tr key={a.iata} className="border-b last:border-0 border-surface-border">
                <td className="td font-mono">{a.iata}</td>
                <td className="td">{a.name}</td>
                <td className="td text-ink-muted text-xs">{a.city}, {a.country}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Units() {
  const q = useUnits();
  if (q.isLoading) return <Spinner />;
  return (
    <div className="bg-white border border-surface-border rounded">
      <table className="w-full">
        <thead>
          <tr className="border-b border-surface-border">
            <th className="th">Code</th>
            <th className="th">Label</th>
            <th className="th">Dimension</th>
          </tr>
        </thead>
        <tbody>
          {q.data?.results.map((u) => (
            <tr key={u.id} className="border-b last:border-0 border-surface-border">
              <td className="td font-mono">{u.code}</td>
              <td className="td">{u.label}</td>
              <td className="td font-mono uppercase text-xs text-ink-muted">{u.dimension}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="p-3 text-xs text-ink-subtle border-t border-surface-border">
        Canonical set is closed by design. Adding a unit requires registering a per-pair conversion in emissions/converters.py — see TRADEOFFS #3.
      </div>
    </div>
  );
}
