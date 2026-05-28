import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/",         label: "Overview" },
  { to: "/imports",  label: "Imports" },
  { to: "/queue",    label: "Review queue" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-white border-r border-surface-border flex flex-col">
      <div className="h-12 px-4 flex items-center border-b border-surface-border">
        <div className="font-mono text-sm tracking-tight">breathe-esg</div>
      </div>
      <nav className="flex-1 px-2 py-3">
        <ul className="space-y-0.5">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  [
                    "flex items-center h-8 px-2 rounded text-sm transition-colors",
                    isActive
                      ? "bg-surface-muted text-ink font-medium"
                      : "text-ink-muted hover:bg-surface-muted hover:text-ink",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <div className="px-3 py-3 border-t border-surface-border text-xs text-ink-subtle">
        v0.1.0 · prototype
      </div>
    </aside>
  );
}
