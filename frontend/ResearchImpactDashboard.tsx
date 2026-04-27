/**
 * Reference layout: Research Impact Dashboard (Tailwind CSS).
 * Drop into a Vite + React + Tailwind project (this repo runs Streamlit — see streamlit_app/app.py).
 *
 * tailwind.config: content: ["./src/**/*.{ts,tsx}"]
 */

import React, { useMemo, useState } from "react";

const YEAR_OPTIONS = [
  { value: "3yrs", label: "Last 3 complete years" },
  { value: "5yrs", label: "Last 5 years (default)" },
  { value: "10yrs", label: "Last 10 complete years" },
] as const;

const DOCS_OPTIONS = [
  { value: "all", label: "All publication types (default)" },
  { value: "articles", label: "Articles only" },
] as const;

type MetricDef = {
  id: string;
  title: string;
  description: string;
  group: "core" | "collab";
};

const METRICS: MetricDef[] = [
  {
    id: "publication",
    title: "Publication",
    description:
      "Publication count (SciVal scholarly output): Scopus-indexed items in the selected window.",
    group: "core",
  },
  {
    id: "fwci",
    title: "Field-Weighted Citation Impact (FWCI)",
    description:
      "FWCI: citations vs peer average for similar papers (1.0 = average); volatile when the set is small.",
    group: "core",
  },
  {
    id: "topJournal",
    title: "Publications in Top 10% Journals",
    description:
      "Share of publications in journals SciVal ranks in the top tenth by CiteScore percentile.",
    group: "core",
  },
  {
    id: "citationCount",
    title: "Citation Count",
    description: "Citation count: citations received by the selected publications, grouped by publication year.",
    group: "core",
  },
  {
    id: "hIndex",
    title: "H-Index",
    description: "H-index: largest h where at least h papers each have ≥ h citations.",
    group: "core",
  },
  {
    id: "citationsPerPublication",
    title: "Citations Per Publication",
    description:
      "Citations per publication: average citations received per publication in the selected window.",
    group: "core",
  },
  {
    id: "collaborationInternational",
    title: "Collaboration",
    description: "SciVal collaboration-type percentages: institutional, national, international, and single author.",
    group: "collab",
  },
  {
    id: "academicCorporateWith",
    title: "Academic–Corporate Collaboration",
    description:
      "Share of publications SciVal classifies as involving both academic and corporate affiliations.",
    group: "collab",
  },
];

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border transition-colors focus:outline-none focus:ring-2 focus:ring-violet-400 focus:ring-offset-2 ${
        checked
          ? "border-violet-500 bg-violet-500"
          : "border-slate-200 bg-slate-200"
      }`}
    >
      <span
        className={`pointer-events-none absolute top-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform ${
          checked ? "left-0.5 translate-x-5" : "left-0.5 translate-x-0"
        }`}
      />
      <span className="sr-only">{label}</span>
    </button>
  );
}

export function ResearchImpactDashboard() {
  const [authorIds, setAuthorIds] = useState("");
  const [year, setYear] = useState<(typeof YEAR_OPTIONS)[number]["value"]>("5yrs");
  const [docs, setDocs] = useState<(typeof DOCS_OPTIONS)[number]["value"]>("all");
  const [selfCit, setSelfCit] = useState<"include" | "exclude">("include");
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(METRICS.map((m) => [m.id, m.group === "core"])),
  );

  const selectedCount = useMemo(
    () => Object.values(enabled).filter(Boolean).length,
    [enabled],
  );

  const setMetric = (id: string, v: boolean) =>
    setEnabled((s) => ({ ...s, [id]: v }));

  const selectAll = () =>
    setEnabled(Object.fromEntries(METRICS.map((m) => [m.id, true])));
  const clearAll = () =>
    setEnabled(Object.fromEntries(METRICS.map((m) => [m.id, false])));

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8 font-sans text-slate-900 antialiased">
      <div className="mx-auto max-w-5xl space-y-6">
        {/* Search card */}
        <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-lg shadow-slate-200/60">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
                Search
              </p>
              <h2 className="mt-1 text-xl font-bold text-slate-900">
                Search Configuration
              </h2>
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full border border-emerald-300 bg-gradient-to-br from-emerald-100 to-green-200 px-4 py-2 text-sm font-semibold text-emerald-900 shadow-sm transition hover:brightness-105"
            >
              <span aria-hidden>🔍</span>
              Find Scopus ID
            </button>
          </div>
          <label className="block text-sm font-semibold text-slate-800">
            Scopus Author ID
          </label>
          <div className="relative mt-2">
            <span
              className="pointer-events-none absolute left-4 top-4 text-slate-400"
              aria-hidden
            >
              🔍
            </span>
            <textarea
              value={authorIds}
              onChange={(e) => setAuthorIds(e.target.value)}
              rows={4}
              placeholder="Enter your Scopus Author ID. Don’t know your Scopus ID? Use Find Scopus ID above."
              className="w-full rounded-2xl border-2 border-slate-200 bg-white py-3 pl-12 pr-4 text-sm !text-slate-900 caret-slate-900 shadow-inner outline-none transition [color-scheme:light] placeholder:text-slate-400 placeholder:opacity-100 placeholder:[-webkit-text-fill-color:#94a3b8] focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100"
              style={{ WebkitTextFillColor: "#0f172a" }}
            />
          </div>
          <p className="mt-4 rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
            Select the metrics below and press{" "}
            <strong className="text-slate-800">Analyze Metrics</strong>.{" "}
            <a
              href="#analyze"
              className="font-semibold text-blue-600 hover:underline"
            >
              Go to Analyze ↗
            </a>
          </p>
        </section>

        {/* Filter deck */}
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-md">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Analysis scope
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900">Filters</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-600">
              Set the time window, document types, and self-citation rules. Each
              panel applies before metrics are fetched.
            </p>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl border border-sky-200 bg-gradient-to-b from-sky-50 to-sky-100/80 p-4 shadow-sm">
              <div className="mb-3 flex gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-200/80 text-xl">
                  📅
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-sky-700">
                    Year range
                  </p>
                  <p className="font-bold text-slate-900">Filter by Year Range</p>
                  <p className="text-xs text-slate-600">
                    Which publication years feed into metrics.
                  </p>
                </div>
              </div>
              <label className="text-[10px] font-bold uppercase text-slate-500">
                Time window
              </label>
              <select
                value={year}
                onChange={(e) => setYear(e.target.value as typeof year)}
                className="mt-1 w-full rounded-lg border-0 bg-white/80 py-2.5 pl-3 text-sm font-medium text-slate-800 shadow-sm"
              >
                {YEAR_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs text-sky-800">5 complete years</p>
            </div>

            <div className="rounded-2xl border border-emerald-200 bg-gradient-to-b from-emerald-50 to-teal-100/80 p-4 shadow-sm">
              <div className="mb-3 flex gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-200/80 text-xl">
                  📄
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-teal-700">
                    Document types
                  </p>
                  <p className="font-bold text-slate-900">
                    Filter by Document Types
                  </p>
                  <p className="text-xs text-slate-600">
                    Limit which document categories are counted.
                  </p>
                </div>
              </div>
              <label className="text-[10px] font-bold uppercase text-slate-500">
                Document types
              </label>
              <select
                value={docs}
                onChange={(e) => setDocs(e.target.value as typeof docs)}
                className="mt-1 w-full rounded-lg border-0 bg-white/80 py-2.5 pl-3 text-sm font-medium text-slate-800 shadow-sm"
              >
                {DOCS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-xs text-emerald-900">
                Include all types matching your selection.
              </p>
            </div>

            <div className="rounded-2xl border border-amber-200 bg-gradient-to-b from-amber-50 to-orange-100/80 p-4 shadow-sm">
              <div className="mb-3 flex gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-orange-200/80 text-xl">
                  🔀
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-orange-800">
                    Self-citations
                  </p>
                  <p className="font-bold text-slate-900">Self-Citations for Citation Metrics</p>
                  <p className="text-xs text-slate-600">
                    Include or exclude an author’s citations to their own work.
                  </p>
                </div>
              </div>
              <div className="mt-2 flex gap-4">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-orange-950">
                  <input
                    type="radio"
                    name="self"
                    checked={selfCit === "include"}
                    onChange={() => setSelfCit("include")}
                    className="h-4 w-4 accent-orange-600"
                  />
                  Include
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-orange-950">
                  <input
                    type="radio"
                    name="self"
                    checked={selfCit === "exclude"}
                    onChange={() => setSelfCit("exclude")}
                    className="h-4 w-4 accent-orange-600"
                  />
                  Exclude
                </label>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-orange-900/90">
                Self-citation handling applies to citation-based metrics where
                SciVal supports it.
              </p>
            </div>
          </div>
        </section>

        {/* Metrics */}
        <section className="rounded-2xl border border-violet-200 bg-violet-50/40 p-6 shadow-md ring-1 ring-violet-100">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xl" aria-hidden>
                🔽
              </span>
              <h2 className="text-lg font-bold text-violet-950">
                Select Metrics to Include
              </h2>
            </div>
            <span className="rounded-full border border-violet-200 bg-white px-4 py-1.5 text-sm font-bold text-violet-800 shadow-sm">
              {selectedCount} of {METRICS.length} metrics selected
            </span>
          </div>
          <p className="mb-4 text-sm text-violet-900/80">
            Toggle metrics on or off.
          </p>
          <div className="mb-4 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={selectAll}
              className="rounded-lg border-2 border-violet-500 bg-violet-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700"
            >
              Select All
            </button>
            <button
              type="button"
              onClick={clearAll}
              className="rounded-lg border border-slate-300 bg-slate-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
            >
              Clear All
            </button>
          </div>

          <p className="mb-3 border-l-4 border-violet-500 pl-3 text-sm font-bold text-violet-950">
            Core research metrics
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {METRICS.filter((m) => m.group === "core").map((m) => {
              const on = enabled[m.id];
              return (
                <div
                  key={m.id}
                  className={`rounded-xl border p-4 shadow-sm transition ${
                    on
                      ? "border-violet-400 bg-gradient-to-br from-violet-50 to-white"
                      : "border-slate-200 bg-slate-50 text-slate-500"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className={`font-semibold ${on ? "text-slate-900" : "text-slate-500"}`}
                    >
                      {m.title}
                    </span>
                    <Toggle
                      checked={on}
                      onChange={(v) => setMetric(m.id, v)}
                      label={m.title}
                    />
                  </div>
                  <p
                    className={`mt-2 text-xs leading-relaxed ${on ? "text-slate-600" : "text-slate-400"}`}
                  >
                    {m.description}
                  </p>
                </div>
              );
            })}
          </div>

          <p className="mb-3 mt-8 border-l-4 border-violet-500 pl-3 text-sm font-bold text-violet-950">
            Collaboration metrics
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {METRICS.filter((m) => m.group === "collab").map((m) => {
              const on = enabled[m.id];
              return (
                <div
                  key={m.id}
                  className={`rounded-xl border p-4 shadow-sm transition ${
                    on
                      ? "border-violet-400 bg-gradient-to-br from-violet-50 to-white"
                      : "border-slate-200 bg-slate-50 text-slate-500"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className={`font-semibold ${on ? "text-slate-900" : "text-slate-500"}`}
                    >
                      {m.title}
                    </span>
                    <Toggle
                      checked={on}
                      onChange={(v) => setMetric(m.id, v)}
                      label={m.title}
                    />
                  </div>
                  <p
                    className={`mt-2 text-xs leading-relaxed ${on ? "text-slate-600" : "text-slate-400"}`}
                  >
                    {m.description}
                  </p>
                </div>
              );
            })}
          </div>

          <div id="analyze" className="mt-8 scroll-mt-8">
            <button
              type="button"
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-violet-400 to-violet-600 py-3.5 text-base font-bold text-white shadow-lg shadow-violet-400/40 transition hover:brightness-105"
            >
              <span aria-hidden>📈</span>
              Analyze Metrics
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

export default ResearchImpactDashboard;
