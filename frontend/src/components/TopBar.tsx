import * as Dropdown from "@radix-ui/react-dropdown-menu";

import type { UserDTO } from "@/api/types";
import { useLogout, useOrgs } from "@/api/hooks";
import { useUiStore } from "@/store/ui";

interface Props {
  user: UserDTO;
}

export function TopBar({ user }: Props) {
  const orgs = useOrgs();
  const orgId = useUiStore((s) => s.orgId);
  const setOrgId = useUiStore((s) => s.setOrgId);
  const logout = useLogout();

  const currentOrg = orgs.data?.find((o) => o.id === orgId);
  const role = user.memberships.find((m) => m.organization.id === orgId)?.role;

  return (
    <header className="h-12 px-4 bg-white border-b border-surface-border flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Dropdown.Root>
          <Dropdown.Trigger asChild>
            <button className="btn-ghost">
              <span className="font-medium">{currentOrg?.name ?? "Select organization"}</span>
              {role && (
                <span className="ml-1 text-xs uppercase tracking-wider text-ink-subtle">
                  {role}
                </span>
              )}
              <svg width="10" height="10" viewBox="0 0 12 12" className="ml-0.5 text-ink-subtle">
                <path d="M3 4.5 6 8l3-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </Dropdown.Trigger>
          <Dropdown.Portal>
            <Dropdown.Content
              align="start" sideOffset={6}
              className="min-w-[180px] bg-white border border-surface-border rounded-md py-1 shadow-sm"
            >
              <div className="px-2 py-1 text-xs uppercase tracking-wider text-ink-subtle">
                Organizations
              </div>
              {orgs.data?.map((o) => (
                <Dropdown.Item
                  key={o.id}
                  onSelect={() => setOrgId(o.id)}
                  className="px-2 py-1 text-sm cursor-pointer hover:bg-surface-muted outline-none flex items-center justify-between"
                >
                  <span>{o.name}</span>
                  {o.id === orgId && <span className="text-xs text-ink-subtle">current</span>}
                </Dropdown.Item>
              ))}
            </Dropdown.Content>
          </Dropdown.Portal>
        </Dropdown.Root>
      </div>

      <Dropdown.Root>
        <Dropdown.Trigger asChild>
          <button className="btn-ghost font-mono text-xs">
            {user.email}
          </button>
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content
            align="end" sideOffset={6}
            className="min-w-[180px] bg-white border border-surface-border rounded-md py-1 shadow-sm"
          >
            <Dropdown.Item
              onSelect={() => logout.mutate()}
              className="px-2 py-1 text-sm cursor-pointer hover:bg-surface-muted outline-none"
            >
              Sign out
            </Dropdown.Item>
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
    </header>
  );
}
