"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUpRight, ChevronRight, ClipboardCheck, FilePlus2, Globe2, LayoutGrid, LibraryBig, MapPinned, PanelLeftClose, PanelLeftOpen, ScanLine, UserCog, Users, ClipboardList, ListChecks, MessageSquareText } from "lucide-react";
import { canModerate, roleLabel, useAccount, type Role } from "./auth-gate";

export type PageId = "reports" | "overview" | "identification" | "catalog" | "map" | "review" | "report" | "report-detail" | "account" | "accounts" | "study" | "survey";

const sections = [
  { label: "WORKSPACE", items: [
    { id: "overview", label: "Overview", icon: LayoutGrid },
    { id: "identification", label: "Identify a plant", icon: ScanLine },
    { id: "catalog", label: "Species catalog", icon: LibraryBig },
  ] },
  { label: "FIELD NOTEBOOK", items: [
    { id: "reports", label: "My reports", icon: ListChecks },
    { id: "map", label: "Occurrence map", icon: MapPinned },
  ] },
  { label: "ADMINISTRATION", items: [
    { id: "review", label: "Review & training", icon: ClipboardCheck },
    { id: "accounts", label: "Manage accounts", icon: Users },
    { id: "study", label: "Usability study", icon: ClipboardList },
  ] },
  { label: "ACCOUNT", items: [
    { id: "survey", label: "Feedback survey", icon: MessageSquareText },
    { id: "account", label: "Account settings", icon: UserCog },
  ] },
] as const;

// Administrators manage accounts from Manage accounts, so they do not get the personal Account settings page.
const visible = (id: PageId, role: Role) => id === "review" ? canModerate(role) : id === "accounts" || id === "study" ? role === "admin" : id === "account" ? role !== "admin" : true;

export default function AppShell({ activePage, title, onNavigate, children }: {
  activePage: PageId; title: string; onNavigate: (page: PageId) => void; children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const { user, signOut } = useAccount();
  const drawer = useRef<HTMLElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const awaiting = useAwaitingReview(canModerate(user.role), activePage);
  // The report form is the last step of Identify, so Identify stays highlighted there.
  const current: PageId = activePage === "report" ? "identification" : activePage;

  function navigate(page: PageId) { onNavigate(page); setOpen(false); }

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    drawer.current?.querySelector<HTMLButtonElement>("button")?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") { setOpen(false); toggle.current?.focus(); }
      if (event.key === "Tab") {
        const buttons = [...(drawer.current?.querySelectorAll<HTMLButtonElement>("button") ?? [])].filter(button => button.getClientRects().length > 0);
        const first = buttons[0], last = buttons[buttons.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }
    function resize() { if (window.matchMedia("(min-width: 1024px)").matches) setOpen(false); }
    window.addEventListener("keydown", keydown);
    window.addEventListener("resize", resize);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", keydown); window.removeEventListener("resize", resize); };
  }, [open]);

  return <div className="flora-shell min-h-screen text-[var(--ink)]">
    <a href="#workspace-content" className="flora-skip">Skip to content</a>
    {open && <button className="flora-scrim lg:hidden" aria-label="Close navigation" onClick={() => { setOpen(false); toggle.current?.focus(); }} />}
    <aside ref={drawer} id="workspace-navigation" aria-label="Workspace navigation" className={`flora-sidebar ${open ? "is-open" : ""}`}>
      <div className="flex items-center justify-between px-2 pb-6 pt-1">
        <button aria-label="GeoFlora overview" onClick={() => navigate("overview")} className="text-left">
          <span className="flora-wordmark block text-[28px] leading-none">geoflora<span className="text-[#7fa96f]">.</span></span>
          <span className="mt-1.5 block whitespace-nowrap text-[9px] font-semibold tracking-[0.18em] text-[#5f6b62]">PLANT INTELLIGENCE</span>
        </button>
        <button className="flora-icon-button lg:hidden" aria-label="Close navigation" onClick={() => { setOpen(false); toggle.current?.focus(); }}><PanelLeftClose size={19} /></button>
      </div>

      <div className="flora-workspace mb-6 flex items-center gap-3 p-2.5 pr-4">
        <span className="flora-workspace-icon"><Globe2 size={17} strokeWidth={1.7} /></span>
        <div><p className="text-[12px] font-semibold text-[#0d2618]">Philippines</p><p className="mt-0.5 text-[10px] text-[#5f6b62]">Research workspace</p></div>
        <span className="flora-local-dot ml-auto" aria-hidden="true" />
      </div>

      <nav aria-label="Main navigation" className="flex-1 space-y-6">
        {sections.map(section => ({ ...section, items: section.items.filter(item => visible(item.id, user.role)) })).filter(section => section.items.length > 0).map(section => <div key={section.label}>
          <p className="mb-2 px-3 text-[9px] font-bold tracking-[0.18em] text-[#5f6b62]">{section.label}</p>
          <div className="space-y-1">{section.items.map(item => {
            const Icon = item.icon;
            const count = item.id === "review" && awaiting ? awaiting : undefined;
            return <button key={item.id} onClick={() => navigate(item.id)} aria-current={current === item.id ? "page" : undefined} className="flora-nav-item" data-count={count} aria-label={count ? `${item.label}, ${count} awaiting review` : undefined}>
              <span className="flora-nav-icon"><Icon size={17} strokeWidth={1.8} /></span>
              <span className="flex-1 text-left">{item.id === "reports" && canModerate(user.role) ? "All reports" : item.label}</span>
              {current === item.id && <span className="flora-active-dot" aria-hidden="true" />}
            </button>;
          })}</div>
        </div>)}
      </nav>

      <div className="flora-field-note mt-6 p-4 pt-20">
        <p className="lp-display text-[22px] leading-[0.95]">Small sightings.<br /><span className="text-[#c6dcae]">Bigger picture.</span></p>
        <button onClick={() => navigate("identification")} className="mt-4 flex w-full items-center justify-between rounded-full bg-white px-4 py-2.5 text-[12px] font-semibold text-[#0d2618] transition hover:bg-[#c6dcae]">Identify a plant <ArrowUpRight size={14} /></button>
      </div>
      <div className="mt-4 flex items-center gap-2.5 rounded-full bg-[#eef1ea] p-1.5 pr-2 text-[11px]"><span className="flora-avatar" aria-hidden="true">{user.username.slice(0, 2)}</span><span className="min-w-0 flex-1 leading-tight"><span className="block truncate font-semibold text-[#0d2618]">{user.username}</span><span className="block truncate text-[10px] text-[#5f6b62]">{roleLabel(user.role)}</span></span><button onClick={() => void signOut()} className="rounded-full bg-white px-3 py-1.5 text-[11px] font-semibold text-[#0d2618] transition hover:bg-[#c6dcae]">Sign out</button></div>
    </aside>

    <div className="flora-main">
      <header className="flora-topbar">
        <div className="flex min-w-0 items-center gap-3">
          <button ref={toggle} className="flora-icon-button lg:hidden" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded={open} onClick={() => setOpen(true)}><PanelLeftOpen size={20} /></button>
          <div className="flex min-w-0 items-center gap-2 text-[13px]"><span className="hidden text-[#5f6b62] md:inline">Workspace</span><ChevronRight size={13} className="hidden text-[#9aa39c] md:block" /><span className="truncate font-semibold text-[#0d2618]">{title}</span></div>
        </div>
        <div className="flex items-center gap-2"><span className="hidden items-center gap-1.5 rounded-full bg-[#eef1ea] px-3 py-2 text-[11px] font-medium text-[#33433a] xl:flex"><Globe2 size={13} strokeWidth={1.7} />Philippines</span><button onClick={() => navigate("identification")} className="flora-create-button"><FilePlus2 size={16} strokeWidth={1.8} /><span className="hidden sm:inline">New sighting</span><span className="sm:hidden">Report</span></button></div>
      </header>
      <main id="workspace-content" tabIndex={-1} className="flora-content mx-auto max-w-[1440px] px-3 pb-28 pt-5 outline-none sm:px-5 lg:pb-10 lg:pl-0 lg:pr-3">{children}</main>
    </div>
    <nav aria-label="Quick navigation" className="flora-mobile-dock lg:hidden">
      {[{ page: "overview" as const, label: "Home", icon: LayoutGrid }, canModerate(user.role) ? { page: "review" as const, label: "Review", icon: ClipboardCheck } : { page: "identification" as const, label: "Identify", icon: ScanLine }, { page: "reports" as const, label: "Reports", icon: ListChecks }, { page: "map" as const, label: "Map", icon: MapPinned }].map(item => <button key={item.page} aria-current={current === item.page ? "page" : undefined} onClick={() => navigate(item.page)}><item.icon size={20} strokeWidth={1.7} /><span>{item.label}</span></button>)}
    </nav>
  </div>;
}

// Sightings awaiting review, for the navigation badge. Refreshed on page changes, every 15 s on the review page and every minute elsewhere.
function useAwaitingReview(enabled: boolean, page: PageId) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const abort = new AbortController();
    const load = () => fetch("/api/overview", { cache: "no-store", signal: abort.signal }).then(async response => { if (response.ok) setCount((await response.json()).sightings.awaitingReview ?? 0); }).catch(() => {});
    void load(); const timer = setInterval(() => void load(), page === "review" ? 15000 : 60000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [enabled, page]);
  return count;
}
