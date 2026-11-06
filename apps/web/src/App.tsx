"use client";

import { useEffect, useState } from "react";
import AppShell, { type PageId } from "./components/app-shell";
import AuthGate, { canModerate, useAccount } from "./components/auth-gate";
import AdminReview from "./features/admin/admin-review";
import AccountSettings from "./features/accounts/account-settings";
import ManageAccounts from "./features/accounts/manage-accounts";
import CatalogView from "./features/catalog/catalog-view";
import StudyRecorder from "./features/study/study-recorder";
import UserSurvey from "./features/study/user-survey";
import { ArrowRight, BookOpen, Map, ShieldCheck, Sparkles } from "lucide-react";
import OverviewView from "./features/overview/overview-view";
import IdentificationView from "./features/identification/identification-view";
import SightingsMap from "./features/sightings/sightings-map";
import ReportsList from "./features/sightings/reports-list";
import ReportView from "./features/sightings/report-view";

function App() {
  const { user } = useAccount();
  const initialReport = typeof window === "undefined" ? "" : new URL(window.location.href).searchParams.get("report") ?? "";
  const [activePage, setActivePage] = useState<PageId>(/^[a-f0-9]{24}$/i.test(initialReport) ? "report-detail" : canModerate(user.role) ? "review" : "identification");
  const [mapReportId, setMapReportId] = useState<string>();
  const [reportId, setReportId] = useState(initialReport);

  function navigate(page: PageId) {
    // A report is always created from an identification; there is no separate report entry point.
    if (page === "report") page = "identification";
    if (page !== "report-detail") { const url = new URL(window.location.href); url.searchParams.delete("report"); window.history.replaceState(null, "", url); }
    setActivePage(page);
  }

  function viewReport(id: string) {
    setReportId(id); navigate("report-detail");
    const url = new URL(window.location.href); url.searchParams.set("report", id); window.history.pushState(null, "", url);
  }
  useEffect(() => {
    function restore() { const id = new URL(window.location.href).searchParams.get("report") ?? ""; setReportId(id); setActivePage(/^[a-f0-9]{24}$/i.test(id) ? "report-detail" : canModerate(user.role) ? "review" : "identification"); }
    window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore);
  }, [user.role]);

  return (
    <AppShell activePage={activePage} title={activePage === "reports" && canModerate(user.role) ? "All reports" : pageTitle(activePage)} onNavigate={navigate}>
          {activePage === "overview" ? (
            <OverviewView onNavigate={navigate} />
          ) : activePage === "identification" || activePage === "report" ? (
            // The report is saved on the result screen itself (identify -> result -> save report).
            <IdentificationView onViewReport={viewReport} />
          ) : activePage === "reports" ? (
            <ReportsList onViewReport={viewReport} onNew={() => navigate("identification")} />
          ) : activePage === "report-detail" ? (
            <ReportView id={reportId} onAnother={() => navigate("identification")} />
          ) : activePage === "map" ? (
            <SightingsMap focusId={mapReportId} onViewReport={viewReport} />
          ) : activePage === "review" && canModerate(user.role) ? (
            <AdminReview />
          ) : activePage === "catalog" ? (
            <CatalogView />
          ) : activePage === "account" ? (
            <AccountSettings />
          ) : activePage === "accounts" && user.role === "admin" ? (
            <ManageAccounts />
          ) : activePage === "study" && user.role === "admin" ? (
            <StudyRecorder />
          ) : activePage === "survey" ? (
            <UserSurvey />
          ) : (
            <ComingSoon page={activePage} onBack={() => navigate("overview")} />
          )}
          <footer className="mt-12 flex flex-col justify-between gap-2 border-t border-[#dbe2d6] px-1 pt-5 text-[11px] text-[#5f6b62] sm:flex-row sm:items-center">
            <span>GeoFlora · Philippine plant intelligence</span>
            <span>Research workspace · Local development</span>
          </footer>
    </AppShell>
  );
}

function ComingSoon({ page, onBack }: { page: PageId; onBack: () => void }) {
  const descriptions: Record<PageId, string> = {
    "report-detail": "View a saved field report and download its PDF.",
    reports: "Your saved reports.",
    report: "Save a geotagged plant sighting for review.",
    overview: "",
    identification: "A real plant identification workflow will be connected after the model is trained and evaluated.",
    catalog: "Review source-attributed plant records before building the searchable species catalog.",
    map: "Verified field sightings and geographic monitoring will appear here in a future milestone.",
    review: "Human review is required before collected images can be used in training datasets.",
    account: "Manage your password and sessions.",
    accounts: "Administrator access is required to manage accounts.",
    study: "Administrator access is required to record usability sessions.",
    survey: "Tell us how GeoFlora worked for you.",
  };
  const titles: Record<PageId, string> = {
    "report-detail": "Saved field report",
    reports: "My reports",
    report: "Create a field report",
    overview: "Overview",
    identification: "Plant identification",
    catalog: "Species catalog",
    map: "Occurrence map",
    review: "Sighting review",
    account: "Account settings",
    accounts: "Manage accounts",
    study: "Usability study",
    survey: "Feedback survey",
  };
  return (
    <section className="surface-card mx-auto mt-8 max-w-2xl px-6 py-12 text-center sm:px-12">
      <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e8f2e9] text-[var(--green)]">
        {page === "identification" ? <Sparkles size={22} /> : page === "catalog" ? <BookOpen size={22} /> : page === "map" ? <Map size={22} /> : <ShieldCheck size={22} />}
      </span>
      <p className="mt-5 text-[18px] font-semibold tracking-[-0.04em]">{titles[page]}</p>
      <p className="mx-auto mt-2 max-w-md text-[11px] leading-5 text-[var(--muted)]">{descriptions[page]}</p>
      <span className="mx-auto mt-5 inline-flex rounded-full bg-[#f3f5f2] px-3 py-1.5 text-[9px] font-semibold text-[#748077]">
        FOUNDATION UI · FEATURE NOT CONNECTED
      </span>
      <div>
        <button
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-[var(--green)] px-4 py-2.5 text-[10px] font-semibold text-white transition hover:bg-[#20553f]"
          onClick={onBack}
        >
          Back to overview <ArrowRight size={13} />
        </button>
      </div>
    </section>
  );
}

function pageTitle(page: PageId) {
  const titles: Record<PageId, string> = {
    "report-detail": "Saved field report",
    reports: "My reports",
    report: "Create a field report",
    overview: "Overview",
    identification: "Plant identification",
    catalog: "Species catalog",
    map: "Occurrence map",
    review: "Sighting review",
    account: "Account settings",
    accounts: "Manage accounts",
    study: "Usability study",
    survey: "Feedback survey",
  };
  return titles[page];
}

export default function GeoFlora() { return <AuthGate><App /></AuthGate>; }
