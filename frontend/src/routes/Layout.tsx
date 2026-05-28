import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import type { UserDTO } from "@/api/types";

interface Props {
  user: UserDTO;
}

export function Layout({ user }: Props) {
  return (
    <div className="min-h-screen bg-surface-subtle flex">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar user={user} />
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
