/**
 * ITSM section wrapper.
 *
 * The Change and Asset modules render inside the shared Admin Console shell —
 * AdminLayout owns the sidebar, branding, and account menu — so this adds only
 * what those pages need on top: a sub-navigation strip for the active module,
 * a scoped search, a Create menu, and the toast host.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { Plus, Search } from "lucide-react";

import { ToastProvider } from "./components/Toast";
import { useItsmData } from "./api";
import { cn } from "./lib/cn";

const CHANGE_TABS = [
  { label: "List", to: "/itsm/changes", end: true },
  { label: "Calendar", to: "/itsm/changes/calendar" },
  { label: "Change Board", to: "/itsm/changes/board" },
  { label: "Templates", to: "/itsm/changes/templates" },
];

const ASSET_TABS = [
  { label: "List", to: "/itsm/assets", end: true },
  { label: "Board", to: "/itsm/assets/board" },
  { label: "Asset Types", to: "/itsm/assets/types" },
  { label: "Locations", to: "/itsm/assets/locations" },
  { label: "Vendors", to: "/itsm/assets/vendors" },
  { label: "Import", to: "/itsm/assets/import" },
  { label: "Reports", to: "/itsm/assets/reports" },
];

function GlobalSearch() {
  const { assets, changes } = useItsmData();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (needle.length < 2) return [];
    const c = changes
      .filter(
        (x) =>
          x.title.toLowerCase().includes(needle) ||
          x.change_number.toLowerCase().includes(needle),
      )
      .slice(0, 5)
      .map((x) => ({
        id: x.id,
        label: `${x.change_number} — ${x.title}`,
        to: `/itsm/changes/${x.id}`,
      }));
    const a = assets
      .filter(
        (x) =>
          x.name.toLowerCase().includes(needle) ||
          x.asset_tag.toLowerCase().includes(needle) ||
          (x.serial_number ?? "").toLowerCase().includes(needle),
      )
      .slice(0, 5)
      .map((x) => ({
        id: x.id,
        label: `${x.asset_tag} — ${x.name}`,
        to: `/itsm/assets/${x.id}`,
      }));
    return [...c, ...a];
  }, [q, assets, changes]);

  return (
    <div ref={boxRef} className="relative w-full max-w-sm">
      <Search
        size={14}
        aria-hidden="true"
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
      />
      <input
        type="search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search changes and assets…"
        aria-label="Search changes and assets"
        className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-8 pr-3 text-[13px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-30 mt-1 w-full overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
          {results.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => {
                  navigate(r.to);
                  setQ("");
                  setOpen(false);
                }}
                className="block w-full truncate px-3 py-2 text-left text-[12.5px] text-slate-700 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && q.trim().length >= 2 && results.length === 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-[12.5px] text-slate-500 shadow-lg">
          No matches for “{q}”.
        </div>
      )}
    </div>
  );
}

function CreateMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-sky-700 focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
      >
        <Plus size={14} /> Create
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-1 w-44 overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg"
        >
          <Link
            role="menuitem"
            to="/itsm/changes/new"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-[12.5px] text-slate-700 hover:bg-slate-50"
          >
            New change
          </Link>
          <Link
            role="menuitem"
            to="/itsm/assets/new"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-[12.5px] text-slate-700 hover:bg-slate-50"
          >
            New asset
          </Link>
          <Link
            role="menuitem"
            to="/itsm/assets/import"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 text-[12.5px] text-slate-700 hover:bg-slate-50"
          >
            Bulk import assets
          </Link>
        </div>
      )}
    </div>
  );
}

export function ItsmLayout() {
  const location = useLocation();
  const inChanges = location.pathname.startsWith("/itsm/changes");
  const inAssets = location.pathname.startsWith("/itsm/assets");
  const tabs = inChanges ? CHANGE_TABS : inAssets ? ASSET_TABS : [];

  return (
    <ToastProvider>
      <div className="itsm-root flex min-h-full flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-5 py-2.5">
          {tabs.length > 0 && (
            <nav
              aria-label={inChanges ? "Change views" : "Asset views"}
              className="flex flex-wrap items-center gap-1"
            >
              {tabs.map((t) => (
                <NavLink
                  key={t.to}
                  to={t.to}
                  end={t.end}
                  className={({ isActive }) =>
                    cn(
                      "rounded-md px-2.5 py-1 text-[12.5px] transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-sky-500",
                      isActive
                        ? "bg-sky-50 font-medium text-sky-800"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                    )
                  }
                >
                  {t.label}
                </NavLink>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-2">
            <GlobalSearch />
            <CreateMenu />
          </div>
        </header>

        <div className="flex-1 p-5">
          <Outlet />
        </div>
      </div>
    </ToastProvider>
  );
}
