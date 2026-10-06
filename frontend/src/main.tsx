import {MobileApp} from "./MobileApp";
import {apiFetch} from "./NetworkFetch";
import QualificationManager from "./QualificationManager";
import {HistorySuggestions,SmallModelSettings} from './Suggestions';
import {CastProposal} from './CastProposal';
import {saveFile} from './saveFile';
import {EventRoles,AddStage,removeStage} from './EventPlanEditor';
import { tr, useLanguage, setLanguage, getLanguage, Language } from "./i18n";
import React, { useState, useEffect, useRef } from "react";
import { createRoot } from "react-dom/client";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import ruLocale from "@fullcalendar/core/locales/ru";
import {
  Plus,
  CalendarDays,
  Clapperboard,
  Users,
  Building2,
  Boxes,
  Settings,
  Search,
  Bell,
  Sparkles,
  Command,
  ArrowRight,
  X,
  ChevronRight,
  Check,
  AlertTriangle,
  Activity,
  Layers,
  SlidersHorizontal,
  Truck,
  MoveUpRight,
} from "lucide-react";
import "./style.css";
import {AccountGate,AccountMenu} from "./Accounts";
import {ApprovalActions} from "./ApprovalActions";
import {DatabaseLocation} from "./Connection";
import PassportEditor from "./PassportEditor";
import VenueEditor from "./VenueEditor";
import ScheduleExport from "./ScheduleExport";
import {DataValue,ImportedData,isImportedMetadata,importedLabel} from "./ImportedData";
import { ru } from "./ru";
type Obj = Record<string, any>;
const initialToken = new URLSearchParams(location.search).get("token");
if (initialToken) {
  sessionStorage.setItem("stageos-token", initialToken);
  history.replaceState({}, "", location.pathname);
}
async function api(path: string, method = "GET", body?: any) {
  const res = await apiFetch("/api" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-StageOS-Token": sessionStorage.getItem("stageos-token") || "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status===401) window.dispatchEvent(new Event("stageos-session-expired"));
  if (!res.ok) {
    let e = await res.json();
    throw new Error(
      typeof e.detail === "string"
        ? e.detail
        : Array.isArray(e.detail)
          ? e.detail
              .map((x: Obj) => "Проверьте поле «" + ru(x.loc?.at(-1)) + "».")
              .join(" ")
          : "Ошибка проверки данных",
    );
  }
  return res.json();
}
const time = (s: string) =>
  new Date(s).toLocaleTimeString(getLanguage()==="en" ? "en-GB" : "ru-RU", { hour: "2-digit", minute: "2-digit" });
const date = (s: string) =>
  new Date(s).toLocaleDateString(getLanguage()==="en" ? "en-GB" : "ru-RU", { day: "numeric", month: "long" });
const local = (d: Date) =>
  new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 19);
const statusLabels: Obj = {
  READY: "Готово",
  WARNING: "Внимание",
  CONFLICT: "Конфликт",
};
function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value.toLowerCase()}>
      {tr(value === "READY"
        ? "✓ "
        : value === "CONFLICT"
          ? "× "
          : value === "WARNING"
            ? "⚠ "
            : "")}
      {tr(statusLabels[value] || ru(value))}
    </span>
  );
}
function shiftedStart(req: Obj, start: string): Obj {
  const delta = +new Date(start) - +new Date(req.start);
  const edits = Object.fromEntries(Object.entries(req.task_overrides || {}).map(([name, raw]) => {
    const edit = raw as Obj;
    return [name, {...edit, ...(edit.start && Number.isFinite(delta) ? {start:local(new Date(+new Date(edit.start)+delta))} : {})}];
  }));
  return {...req,start,task_overrides:edits,extra_tasks:(req.extra_tasks||[]).map((t:Obj)=>({...t,start:Number.isFinite(delta)?local(new Date(+new Date(t.start)+delta)):t.start}))};
}
const today = local(new Date()).slice(0,10);
function newEventForm(f: Obj): Obj {
  return { ...f, event_id: undefined, version: undefined, replacements: {}, role_assignments:{}, removed_tasks:[], extra_tasks:[], task_overrides: {}, baseline_plan:true, run_through:true, duration:undefined, force: false, override_reason: "", notes: "" };
}
function App({account,exit}:{account?:Obj|null;exit?:()=>Promise<void>}) {
  const canApprove = !account || ["admin", "artistic_director"].includes(account.user.role);
  const canEdit = !account || account.user.role !== "viewer";
  const language=useLanguage();
  const languageLoaded=useRef(false);
  const changeLanguage=async(value:Language)=>{
    try {await api("/settings/interface","PUT",{language:value});setLanguage(value);}
    catch(e:any){setError(e.message);}
  };
  const [boot, setBoot] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [page, setPage] = useState("Назначить"),
    [busy, setBusy] = useState(false),
    [toast, setToast] = useState("");
  const [form, setForm] = useState<Obj>({
      production_id: 0,
      venue_id: 0,
      kind: "Спектакль",
      cast: "B",
      start: today + "T18:00:00",
      duration: undefined, baseline_plan: true, run_through: true,
      adaptation: true,
      scenes: [],
      replacements: {},
    }),
    [live, setLive] = useState<Obj | null>(null),
    [preview, setPreview] = useState<Obj | null>(null),
    [detail, setDetail] = useState<Obj | null>(null),
    [override, setOverride] = useState("");
  const [events, setEvents] = useState<Obj[]>([]),
    [filter, setFilter] = useState<Obj>({}),
    [view, setView] = useState("timeGridWeek"),
    [calDate, setCalDate] = useState(today),
    [showExport, setShowExport] = useState(false),
    [calendarBusy, setCalendarBusy] = useState(false),
    [selected, setSelected] = useState<Obj | null>(null),
    [tab, setTab] = useState("Люди"),
    [find, setFind] = useState(""),
    [palette, setPalette] = useState(false),
    [windows, setWindows] = useState<Obj[]>([]),
    [blocks, setBlocks] = useState<Obj[]>([]),
    [analytics, setAnalytics] = useState<Obj | null>(null),
    [notes, setNotes] = useState<Obj[]>([]),
    [settings, setSettings] = useState<Obj | null>(null),
    [diagnostics, setDiagnostics] = useState<Obj | null>(null),
    [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState(""),
    [revision, setRevision] = useState(0),
    [slots, setSlots] = useState<Obj[]>([]),
    [showTasks, setShowTasks] = useState(false),
    [resourceEditor, setResourceEditor] = useState<Obj | null>(null),
    [scenarios, setScenarios] = useState<Obj[]>([]);
  const [theatreName, setTheatreName] = useState(""),
    [venueEditor, setVenueEditor] = useState<Obj | null>(null),
    [rehearsalDept, setRehearsalDept] = useState("");
  const [passport, setPassport] = useState<Obj | null>(null),
    [catalogDept, setCatalogDept] = useState(""),
    [catalogCategory, setCatalogCategory] = useState(""),
    [personStats, setPersonStats] = useState<Obj | null>(null);
  useEffect(() => {
    setPersonStats(null);
    let active = true;
    if (selected?.kind === "Person")
      api("/resources/" + selected.id + "/statistics")
        .then((x) => {
          if (active) setPersonStats(x);
        })
        .catch((e) => setError(ru(e.message)));
    return () => {
      active = false;
    };
  }, [selected, revision]);
  function equipmentCategory(r: Obj) {
    if (r.data.category) return r.data.category;
    const n = r.name.toLowerCase();
    for (const [pattern, label] of [
      ["microphone|wireless|микрофон", "Микрофоны"],
      ["console|консоль", "Консоли"],
      ["monitor|iem|монитор", "Мониторы"],
      ["wash", "Wash"],
      ["bar", "LED Bar"],
      ["haze|дымка", "Дымка"],
      ["fog|дым", "Дым"],
      ["moving|profile|bsw", "BSW"],
      ["stagebox", "Стейджбоксы"],
      ["projector", "Проекторы"],
      ["server", "Медиасерверы"],
    ])
      if (new RegExp(pattern).test(n)) return label;
    return r.kind === "Equipment Kit"
      ? "Комплекты"
      : r.kind === "Equipment"
        ? "Прочее"
        : r.kind;
  }
  async function newPassport() {
    await run(async () => {
      const template = await api("/production-template");
      template.data.home_venue = resources.find(r => r.kind === "Venue")?.id || 0;
      setPassport(template);
    });
  }
  async function changePlan(p: Obj, changes: Obj) {
    const optimistic = "force" in changes;
    if (optimistic) setPreview({ ...p, request: { ...p.request, ...changes } });
    const result = await run(async () => {
      const req = "start" in changes ? shiftedStart(p.request, changes.start) : p.request;
      const next = await api("/preview", "POST", { ...req, ...changes });
      setPreview(next);
      setForm(next.request);
      return next;
    });
    if (!result && optimistic) setPreview(p);
    return result;
  }
  const cal = useRef<FullCalendar>(null);
  const resources: Obj[] = boot?.resources || [],
    productions: Obj[] = boot?.productions || [];
  const resource = (id: number) => resources.find((r) => r.id === id);
  const prod = productions.find((p) => p.id === form.production_id);
  const [showQualifications,setShowQualifications]=useState(false);
  const departments = [
    ...new Set([...(boot?.departments || []),
      ...resources.filter((r) => r.kind === "Person").map((r) => r.department)]),
  ];
  async function load() {
    try {
      const b = await api("/bootstrap");
      if (!languageLoaded.current){languageLoaded.current=true;if(b.language === "ru" || b.language === "en")setLanguage(b.language);}
      setBoot(b);
      if (!boot && b.demo_enabled) {
        setForm(f=>({...f,start:"2026-10-16T19:00:00"}));setCalDate("2026-10-16");
      }
      if (b.initialized)
        setForm((f) => ({
          ...f,
          production_id: b.productions.some((p: Obj) => p.id === f.production_id) ? f.production_id : (b.productions[0]?.id || 0),
          venue_id:
            b.resources.some((r: Obj) => r.id === f.venue_id) ? f.venue_id : (b.resources.find((r: Obj) => r.kind === "Venue")?.id || 0),
        }));
    } catch (e: any) {
      setError(ru(e.message));
    }
  }
  useEffect(()=>{if(!account)return;let stopped=false;let seen:number|undefined;
    const poll=async()=>{try{const next=await api('/sync');if(stopped)return;if(seen!==undefined&&seen!==next.revision){await load();setRevision(v=>v+1)}seen=next.revision}catch{}};
    poll();const timer=setInterval(poll,5000);return()=>{stopped=true;clearInterval(timer)};
  },[account?.theatre.id]);
  useEffect(() => {
    load();
    const fn = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setPalette((x) => !x);
      }
      if (e.key === "Escape") {
        setPalette(false);
        setPreview(null);
        setDetail(null);
      }
    };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, []);
  useEffect(() => {
    if (toast) {
      let t = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    if (!boot?.initialized || !form.production_id || !form.venue_id) return;
    let cancelled = false;
    setLive(null);
    if (form.kind === "Репетиция" && form.rehearsal_people?.length === 0)
      return;
    const t = setTimeout(
      () =>
        api("/preview", "POST", form)
          .then((x) => {
            if (!cancelled) setLive(x);
          })
          .catch((e) => {
            if (!cancelled) setError(ru(e.message));
          }),
      350,
    );
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [form, boot?.initialized]);
  useEffect(() => {
    if (!boot?.initialized && page !== "Настройки") return;
    let cancelled = false;
    if (page === "Календарь") {
      setCalendarBusy(true);
      const qs = new URLSearchParams(
        Object.entries(filter)
          .filter(([, v]) => v)
          .map(([k, v]) => [k, String(v)]),
      );
      Promise.all([api("/events?" + qs), api("/blocks")])
        .then(([e, b]) => {
          if (!cancelled) {
            setEvents(e);
            setBlocks(b);
          }
        })
        .catch((e) => setError(ru(e.message)))
        .finally(() => {
          if (!cancelled) setCalendarBusy(false);
        });
    }
    if (page === "Аналитика")
      api("/analytics")
        .then(setAnalytics)
        .catch((e) => setError(ru(e.message)));
    if (page === "Уведомления")
      api("/notifications")
        .then(setNotes)
        .catch((e) => setError(ru(e.message)));
    if (page === "Настройки")
      Promise.all([
        api("/settings/llm"),
        api("/diagnostics"),
        boot?.demo_enabled ? api("/demo/scenarios") : Promise.resolve([]),
      ])
        .then(([s, d, cases]) => {
          setScenarios(cases);
          setSettings(s);
          setDiagnostics(d);
        })
        .catch((e) => setError(ru(e.message)));
    return () => {
      cancelled = true;
    };
  }, [page, filter, revision, boot?.initialized]);
  useEffect(() => {
    if (page !== "Календарь" || view !== "production") return;
    let cancelled = false;
    setSlots([]);
    const matching = events.filter(e => e.start.slice(0, 10) === calDate ||
      (e.tasks || []).some((t: Obj) => t.start.slice(0, 10) <= calDate && t.end.slice(0, 10) >= calDate));
    Promise.all(matching.map(e => api("/events/" + e.id)))
      .then(items => { if (!cancelled) setSlots(items); })
      .catch(e => { if (!cancelled) setError(ru(e.message)); });
    return () => { cancelled = true; };
  }, [page, view, events, calDate]);
  function go(p: string, preserveEvent = false) {
    if (p === "Назначить" && !preserveEvent) {
      setForm(f => f.event_id ? newEventForm(f) : f);
      setOverride("");
      setPreview(null);
      setWindows([]);
      setError("");
    }
    setPage(p);
    setVenueEditor(null);
    setSelected(null);
    setFind("");
    setCatalogDept("");
    setCatalogCategory("");
    if (p === "Добавить спектакль") newPassport();
  }
  function update(k: string, v: any) {
    setForm((f) => k === "start" ? shiftedStart(f, v) : ({ ...f, [k]: v, ...(k === "kind"||k === "production_id" ? { task_overrides:{},removed_tasks:[],extra_tasks:[],role_assignments:{},replacements:{},baseline_plan:true,run_through:true,duration:undefined,rehearsal_people:null,rehearsal_items:[] } : k==="cast"?{role_assignments:{},replacements:{}}:{}) }));
    setWindows([]);
  }
  async function run(fn: () => Promise<any>) {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e: any) {
      setError(ru(e.message));
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function importDatabase(file: File) {
    await run(async () => {
      const res = await apiFetch("/api/database/import", {
        method: "POST",
        headers: {
          "X-StageOS-Token": sessionStorage.getItem("stageos-token") || "",
          "Content-Type": "application/octet-stream",
        },
        body: file,
      });
      if (!res.ok) throw new Error((await res.json()).detail);
      location.reload();
    });
  }
  async function exportDatabase() {
    await run(async () => {
      const res = await apiFetch("/api/database/export", {
        headers: {
          "X-StageOS-Token": sessionStorage.getItem("stageos-token") || "",
        },
      });
      if (!res.ok) throw new Error("Не удалось создать резервную копию");
      setToast(await saveFile(await res.blob(), "StageOS-backup.db"));
    });
  }
  async function analyze(req = form) {
    await run(async () => {
      const p = await api("/preview", "POST", req);
      setPreview(p);
      setOverride(req.override_reason || "");
    });
  }
  async function save(proposal = false) {
    if (!preview || preview.demo_scenario) return;
    await run(async () => {
      const req = { ...preview.request, override_reason: canApprove ? override : "", force: canApprove && !!preview.request.force };
      const p = await api("/preview", "POST", req);
      const reviewed = (plan: Obj) => {
        const copy = JSON.parse(JSON.stringify(plan));
        delete copy.fingerprint;
        delete copy.request.override_reason;
        return JSON.stringify(copy);
      };
      if (reviewed(p) !== reviewed(preview)) {
        setPreview(p);
        setError(
          "Условия изменились. Проверьте обновлённый план и подтвердите ещё раз.",
        );
        return;
      }
      if (proposal) {
        await api("/proposals", "POST", req);
        setPreview(null);
        setToast("Предложение ожидает согласования");
        return;
      }
      const ev = await api("/events", "POST", {
        request: req,
        fingerprint: p.fingerprint,
      });
      setPreview(null);
      setDetail(null);
      setCalDate(ev.start.slice(0, 10));
      setView("timeGridWeek");
      setPage("Календарь");
      setRevision((x) => x + 1);
      setForm(newEventForm);
      setToast("Событие и производственная цепочка сохранены");
    });
  }
  async function openEvent(id: number) {
    await run(async () => setDetail(await api("/events/" + id)));
  }
  function personal(r: Obj) {
    setFilter(
      r.kind === "Person"
        ? { person: r.id }
        : r.kind === "Venue"
          ? { venue: r.id }
          : { equipment: r.id },
    );
    go("Календарь");
  }
  function startEdit(req: Obj) {
    setForm(req);
    setDetail(null);
    setPreview(null);
    go("Назначить", true);
  }
  const nav = [
    ["Назначить", Plus],
    ["Календарь", CalendarDays],
    ["Постановки", Clapperboard],
    ["Сотрудники", Users],
    ["Добавить спектакль", Plus],
    ["Площадки", Building2],
    ["Оборудование", Boxes],
    ["Сценическая механика", Layers],
    ["Аналитика", Activity],
    ["Stage Assistant", Sparkles],
    ["Уведомления", Bell],
    ["Настройки", Settings],
  ] as const;
  function picker(
    label: string,
    key: string,
    opts: Obj[],
    value: any,
    onChange: (v: string) => void,
  ) {
    return (
      <label className="field">
        <span>{tr(ru(label))}</span>
        <select
          aria-label={ru(label)}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          {opts.map((o) => (
            <option key={o.id} value={o.id}>
              {o.kind || typeof o.id === "number" ? o.name : ru(o.name)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function conflicts(p: Obj) {
    return (
      <div className="conflicts">
        {tr(p.conflicts.length === 0 ? (
          <div className="empty success">
            <Check size={22} />{tr("Пересечений и технических ограничений не найдено")}</div>
        ) : (
          p.conflicts.map((c: Obj, i: number) => (
            <details className={"conflict " + c.severity.toLowerCase()} key={i}>
              <summary>
                <AlertTriangle size={15} />
                <b>{tr(ru(c.resource))}</b>
                <span>{tr(ru(c.reason))}</span>
                <Badge value={c.severity} />
              </summary>
              <div>
                {tr(c.current_event && (
                  <p>{tr("Занят: ")}{tr(c.current_event)}{tr(" · ")}{tr(c.venue)}
                  </p>
                ))}
                {tr(c.busy && (
                  <p>
                    {tr(date(c.busy[0]))} {tr(time(c.busy[0]))}{tr("–")}{tr(time(c.busy[1]))}{tr(" · требуется ")}{tr(time(c.required[0]))}{tr("–")}{tr(time(c.required[1]))}
                  </p>
                ))}
                {tr(c.overlap && (
                  <p>{tr("Пересечение: ")}{tr(time(c.overlap[0]))}{tr("–")}{tr(time(c.overlap[1]))}
                  </p>
                ))}
                <p>{tr(ru(c.solutions.join(" · ")))}</p>
              </div>
            </details>
          ))
        ))}
      </div>
    );
  }
  function timeline(tasks: Obj[]) {
    if (!tasks.length) return <p>{tr("Нет задач")}</p>;
    const min = Math.min(...tasks.map((t) => +new Date(t.start))),
      max = Math.max(...tasks.map((t) => +new Date(t.end)));
    return (
      <div className="timeline">
        <div className="timeline-axis">
          <span>{tr(date(new Date(min).toISOString()))} {tr(time(new Date(min).toISOString()))}</span>
          <span>{tr(time(new Date((max + min) / 2).toISOString()))}</span>
          <span>{tr(date(new Date(max).toISOString()))} {tr(time(new Date(max).toISOString()))}</span>
        </div>
        {tasks.map((t, i) => (
          <div className="timeline-row" key={i}>
            <span>{ru(t.name)}</span>
            <div className="track">
              <div
                className="bar"
                style={{
                  left: ((+new Date(t.start) - min) / (max - min)) * 100 + "%",
                  width:
                    Math.max(
                      1,
                      ((+new Date(t.end) - +new Date(t.start)) / (max - min)) *
                        100,
                    ) + "%",
                  background: ["#5169c7", "#23846f", "#bc8750"][i % 3],
                }}
                title={`${date(t.start)} ${time(t.start)}–${date(t.end)} ${time(t.end)}`}
              />
            </div>
            <small>
              {tr(date(t.start))} {tr(time(t.start))}{tr("–")}{tr(date(t.end))} {tr(time(t.end))}
            </small>
          </div>
        ))}
      </div>
    );
  }
  function planContent(p: Obj) {
    return (
      <>
        <div className="metrics">
          <div>
            <small>{tr("СОСТОЯНИЕ")}</small>
            <Badge value={p.status} />
          </div>
          <div>
            <small>{tr("УЧАСТНИКОВ")}</small>
            <b>{tr(p.assignments.length)}</b>
          </div>
          <div>
            <small>{tr("ПОДГОТОВКА С")}</small>
            <b>{tr(time(p.tasks[0].start))}</b>
          </div>
          <div>
            <small>{tr("КОНФИГУРАЦИЯ")}</small>
            <b>{tr(ru(p.compatibility.version))}</b>
          </div>
        </div>
        {p === preview && !p.demo_scenario ? (
          <label className="field">
            <span>{tr("Примечание к событию")}</span>
            <textarea
              key={p.fingerprint + "notes"}
              defaultValue={p.request.notes || ""}
              onBlur={(e) => {
                if (e.target.value !== (p.request.notes || ""))
                  changePlan(p, { notes: e.target.value });
              }}
            />
          </label>
        ) : (
          p.notes && (
            <section className="notice">
              <h3>{tr("Примечание")}</h3>
              {p.notes}
            </section>
          )
        )}
        {tr(p.request.force && (
          <p className="notice">{tr("Принудительное назначение. Конфликты сохранены и требуют решения.")}</p>
        ))}
        {p === preview && !p.demo_scenario && <EventRoles plan={p} resources={resources} busy={busy} onChange={changes=>changePlan(p,changes)}/>}
        <h3>{tr("Ответственные и состав")}</h3>
        <div className="accordion-grid">
          {[...new Set(p.assignments.map((a: Obj) => a.department))].map(
            (dep: any) => (
              <details key={dep}>
                <summary>
                  {tr(ru(dep))}
                  <span>
                    {
                      tr(p.assignments.filter((a: Obj) => a.department === dep)
                        .length)
                    }
                  </span>
                </summary>
                {p.assignments
                  .filter((a: Obj) => a.department === dep)
                  .map((a: Obj, i: number) => (
                    <div className="personline" key={i}>
                      <span>
                        <b>{a.actual}</b>
                        <small>
                          {tr(ru(a.role))}
                          {a.responsible_id !== a.actual_id &&
                            " · ответственный: " + a.responsible}
                        </small>
                      </span>
                      <time>{tr(time(a.call))}</time>
                      {p === preview && !p.demo_scenario && a.department!=="Артисты" && (
                        <select
                          aria-label={"Заменить " + a.actual}
                          value={a.actual_id}
                          disabled={busy}
                          onChange={(e) =>
                            changePlan(p, {
                              replacements: {
                                ...p.request.replacements,
                                [a.responsible_id]: +e.target.value,
                              },
                            })
                          }
                        >
                          {resources
                            .filter(
                              (r) =>
                                r.kind === "Person" &&
                                (a.eligible_ids || [a.actual_id]).includes(
                                  r.id,
                                ),
                            )
                            .map((r) => (
                              <option key={r.id} value={r.id}>
                                {r.name}
                                {tr(r.id === a.responsible_id ? " · основной" : "")}
                              </option>
                            ))}
                        </select>
                      )}
                    </div>
                  ))}
              </details>
            ),
          )}
        </div>
        <h3>{tr("Техническая совместимость")}</h3>
        <div className="check-grid">
          {p.compatibility.checks.map((c: Obj) => (
            <div key={c.name} className={c.ok ? "ok" : "bad"}>
              <span>
                {tr(c.ok ? "✓" : "×")} {ru(c.name)}
              </span>
              <small>
                {tr(c.required)}{tr(" / ")}{tr(c.available)}
              </small>
            </div>
          ))}
        </div>
        {tr(p.compatibility.override && (
          <p className="notice">{tr(p.compatibility.override.note)}</p>
        ))}
        <details>
          <summary>{tr("Техника и резервирования ")}<span>{tr(p.bookings.length)}</span>
          </summary>
          <div className="resource-tags">
            {p.bookings
              .filter((b: Obj) => b.kind !== "Person")
              .map((b: Obj) => (
                <span key={b.resource_id}>
                  {ru(b.name)}{tr(" · ")}{tr(time(b.start))}{tr("–")}{tr(time(b.end))}
                </span>
              ))}
          </div>
        </details>
        <h3>{tr("Производственный план")}</h3>
        {p === preview && !p.demo_scenario && (
          <>
            {tr(p.request.kind !== "Репетиция" && (
              <label className="row">
                <input
                  type="checkbox"
                  checked={!!p.request.run_through}
                  disabled={busy}
                  onChange={(e) =>
                    changePlan(p, {
                      run_through: e.target.checked,
                      task_overrides: {}, removed_tasks:[], extra_tasks:[],
                    })
                  }
                />{tr("Базовый план: прогон, обед и сбор перед спектаклем")}</label>
            ))}
            <p className="muted">{tr("Укажите дату и время каждого этапа, включая предыдущие дни. Измените начало или длительность этапа: зависимости и занятость пересчитываются. Начало и общую продолжительность спектакля с антрактами можно изменить; занятость пересчитывается. Явно заданные времена отмечены как закреплённые.")}</p>
            <AddStage key={p.request.production_id+":"+p.start} plan={p} busy={busy} onChange={changes=>changePlan(p,changes)}/>
            <div key={p.fingerprint} className="schedule-editor">
              {p.tasks.map((t: Obj) => (
                <div className="schedule-row" key={t.name}>
                  <b>{ru(t.name)}</b>
                  <input
                    aria-label={"Начало " + t.name}
                    type="datetime-local"
                    defaultValue={t.start.slice(0, 16)}
                    disabled={busy}
                    onBlur={(e) => {
                      const value=e.target.value;
                      e.target.value=t.start.slice(0,16);
                      if (value && value !== t.start.slice(0,16)) {
                        if (["Спектакль", "Репетиция"].includes(t.name))
                          changePlan(p, { start: value });
                        else
                          changePlan(p, {
                            task_overrides: {
                              ...p.request.task_overrides,
                              [t.name]: {
                                ...p.request.task_overrides?.[t.name],
                                start: value,
                              },
                            },
                          });
                      }
                    }}
                  />
                  <input
                    aria-label={"Длительность " + t.name}
                    type="number"
                    min={["Спектакль","Репетиция"].includes(t.name) ? 15 : 1}
                    max={["Спектакль","Репетиция"].includes(t.name) ? 480 : 10080}
                    defaultValue={Math.round(
                      (+new Date(t.end) - +new Date(t.start)) / 60000,
                    )}
                    disabled={busy}
                    onBlur={(e) => {
                      const n = +e.target.value;
                      e.target.value=String(Math.round((+new Date(t.end)-+new Date(t.start))/60000));
                      if (
                        Number.isInteger(n) && n >= (["Спектакль","Репетиция"].includes(t.name) ? 15 : 1) && n <= (["Спектакль","Репетиция"].includes(t.name) ? 480 : 10080) &&
                        n !==
                          Math.round(
                            (+new Date(t.end) - +new Date(t.start)) / 60000,
                          )
                      ) {
                        if (["Спектакль","Репетиция"].includes(t.name))
                          changePlan(p, { duration: n });
                        else
                          changePlan(p, {
                            task_overrides: {
                              ...p.request.task_overrides,
                              [t.name]: {
                                ...p.request.task_overrides?.[t.name],
                                duration: n,
                              },
                            },
                          });
                      }
                    }}
                  />
                  <small>{tr("до ")}{tr(date(t.end))} {tr(time(t.end))}</small>
                  {!["Спектакль","Репетиция"].includes(t.name)&&<button disabled={busy} aria-label={tr("Удалить этап")+" "+t.name} onClick={()=>changePlan(p,removeStage(p,t.name))}>{tr("Удалить этап")}</button>}
                  {p.request.task_overrides?.[t.name] && (
                    <button
                      onClick={() => {
                        const o = { ...p.request.task_overrides };
                        delete o[t.name];
                        changePlan(p, { task_overrides: o });
                      }}
                    >{tr("Снять закрепление")}</button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
        {tr(timeline(p.tasks))}
        <h3>{tr("Конфликты и предупреждения · ")}{tr(p.conflicts.length)}</h3>
        {tr(conflicts(p))}
        <p className="muted">{tr("Решатель: ")}{tr(ru(p.solver.status))}{tr(" · Штраф мягких ограничений:")}{tr(" ")}
          {tr(p.penalty)}{tr(" · Предварительный план не изменяет расписание")}</p>
      </>
    );
  }
  if (!boot)
    return (
      <div className="loading">
        <Layers />
        <h2>{tr("StageOS")}</h2>
        <p>{tr(error || "Подключение к локальному ядру…")}</p>
        <button onClick={load}>{tr("Повторить")}</button>
      </div>
    );
  return (
    <div className="app">
      <input
        id="database-upload"
        type="file"
        accept=".db,.sqlite,.sqlite3"
        style={{ display: "none" }}
        onChange={(e) => {
          if (e.target.files?.[0]) importDatabase(e.target.files[0]);
        }}
      />
      <aside>
        <div className="brand">
          <div className="brandmark">
            <img src="/stageos-icon.svg" width={40} height={40} alt="" />
          </div>
          <span>{tr("Stage")}<span className="thin">{tr("OS")}</span>
            <small>{tr("ТЕАТРАЛЬНОЕ ПРОИЗВОДСТВО")}</small>
          </span>
        </div>
        <div className="theatre">
          <span className="avatar">{tr("Т")}</span>
          <div>
            {boot?.theatre_name || (boot?.demo_enabled ? "Демо театр" : "Рабочий театр")}<small>{tr("Локальное пространство")}</small>
          </div>
          <span className="online" />
        </div>
        <nav>
          {tr(nav.filter(([name])=>!account||account.user.role==="admin"||name!=="Настройки").map(([name, Icon], i) => (
            <button
              key={name}
              className={
                (page === name ? "active " : "") + (i === 8 ? "nav-gap" : "")
              }
              onClick={() => go(name)}
            >
              <Icon size={18} />
              {tr(ru(name))}
              {tr(name === "Назначить" && <small>{tr("⌘ N")}</small>)}
            </button>
          )))}
        </nav>
        <div className="sidebar-bottom">
          <DatabaseLocation/><small>StageOS · 1.0.12</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <span className="muted">{tr("Рабочее пространство")}</span>
            <ChevronRight size={14} />
            <b>{tr(ru(page))}</b>
          </div>
          <button className="search-btn" onClick={() => setPalette(true)}>
            <Search size={15} />{tr("Быстрый поиск")}<kbd>{tr("Ctrl K")}</kbd>
          </button>
          <button
            className="icon"
            aria-label={tr("Уведомления")}
            onClick={() => go("Уведомления")}
          >
            <Bell size={19} />
          </button>
          <label className="language-switch"><span>{tr("Язык")}</span><select aria-label={tr("Язык приложения")} value={language} onChange={e=>changeLanguage(e.target.value as Language)}><option value="ru">Русский</option><option value="en">English</option></select></label>
          {account && exit ? <AccountMenu session={account} exit={exit}/> : <span className="avatar">{tr("АД")}</span>}
        </header>
        {tr(error && (
          <div role="alert" className="error-banner">
            {tr(error)}
            <button className="icon" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        ))}
        {tr(toast && (
          <div className="toast">
            <Check size={17} />
            {tr(toast)}
          </div>
        ))}
        {!boot.initialized && page !== "Настройки" ? (
          <section className="welcome">
            <div className="eyebrow">{tr("ТЕАТР. ЛЮДИ. ТЕХНОЛОГИИ.")}</div>
            <h1>{tr("Добро пожаловать")}<br />{tr("в StageOS.")}</h1>
            <p>{tr("Всё, что нужно, чтобы поднять занавес.")}<br />{tr("Люди, площадки и производство — в одном расписании.")}</p>
            {tr(!boot.demo_enabled && <label className="field"><span>{tr("Название театра")}</span><input maxLength={200} value={theatreName} onChange={e=>setTheatreName(e.target.value)} /></label>)}
            <button
              className="primary"
              disabled={busy || (!boot.demo_enabled && !theatreName.trim())}
              onClick={() =>
                run(async () => {
                  await api(boot.demo_enabled ? "/demo" : "/theatre", "POST", boot.demo_enabled ? undefined : {name:theatreName});
                  await load();
                  if (!boot.demo_enabled) go("Сотрудники");
                })
              }
            >
              {tr(busy ? "Создаём театр…" : boot.demo_enabled ? "Создать демонстрационный театр" : "Создать рабочую базу")}
              <ArrowRight size={18} />
            </button>
            <div className="row">
              <button
                onClick={() =>
                  document.getElementById("database-upload")?.click()
                }
              >{tr("Открыть существующую базу")}</button>
              <button onClick={() => go("Настройки")}>{tr("Настроить локального помощника")}</button>
            </div>
            <p className="muted">{tr("Данные хранятся на этом компьютере. Основные функции работают без интернета и без ИИ.")}</p>
          </section>
        ) : (
          <div className="content">
            {page === "Назначить" && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">{tr("ПЛАНИРОВАНИЕ БЕЗ ЛИШНИХ ШАГОВ")}</div>
                    <h1>
                      {tr(form.event_id ? "Изменить событие" : "Поднимем занавес.")}
                    </h1>
                    <p>{tr("Выберите главное. StageOS проверит людей, технику и площадку.")}</p>
                  </div>
                  <span className="pill">
                    <span className="online" />{tr("Производственный движок")}</span>
                </div>
                {tr((!productions.length || !resources.some(r => r.kind === "Venue")) && <p className="notice">{tr("Для назначения создайте площадку и постановку. Сотрудников добавьте в разделе «Сотрудники», затем выберите их в паспорте постановки.")}</p>)}
                <div className="assign-card">
                  <div className="segmented">
                    {tr(["Спектакль", "Репетиция"].map((k) => (
                      <button
                        className={form.kind === k ? "chosen" : ""}
                        key={k}
                        onClick={() => update("kind", k)}
                      >
                        {tr(k === "Спектакль" ? (
                          <Clapperboard size={16} />
                        ) : (
                          <Users size={16} />
                        ))}{tr(" ")}
                        {tr(ru(k))}
                      </button>
                    )))}
                  </div>
                  <div className="assign-form">
                    <label className="field">
                      <span>{tr("Дата")}</span>
                      <input
                        aria-label={tr("Дата")}
                        type="date"
                        value={form.start.slice(0, 10)}
                        onChange={(e) =>
                          update("start", e.target.value + form.start.slice(10))
                        }
                      />
                    </label>
                    {tr(picker(
                      "Постановка",
                      "production_id",
                      productions,
                      form.production_id,
                      (v) => {
                        setForm((f) => ({
                          ...f,
                          production_id: +v,
                          replacements: {},
                          role_assignments: {}, removed_tasks: [], extra_tasks: [], baseline_plan:true, run_through:true, duration:undefined,
                          scenes: [],
                          task_overrides: {},
                          rehearsal_people: null,
                          rehearsal_items: [],
                        }));
                      },
                    ))}
                    {tr(picker(
                      "Состав",
                      "cast",
                      [
                        { id: "A", name: "Состав А · первый" },
                        { id: "B", name: "Состав Б · второй" },
                      ],
                      form.cast,
                      (v) => update("cast", v),
                    ))}
                    {tr(picker(
                      "Площадка",
                      "venue_id",
                      resources.filter(
                        (r) =>
                          r.kind === "Venue" ||
                          (form.kind === "Репетиция" && r.kind === "Room"),
                      ),
                      form.venue_id,
                      (v) => update("venue_id", +v),
                    ))}
                    <label className="field">
                      <span>{tr("Начало")}</span>
                      <input
                        type="time"
                        aria-label={tr("Начало")}
                        value={form.start.slice(11, 16)}
                        onChange={(e) =>
                          update(
                            "start",
                            form.start.slice(0, 11) + e.target.value + ":00",
                          )
                        }
                      />
                    </label>
                  </div>
                  {form.kind !== "Репетиция" && <label className="field"><span>{tr("Общая продолжительность с антрактами, мин")}</span><input type="number" min={15} max={480} value={form.duration ?? prod?.data.duration ?? 120} onChange={e=>update("duration",e.target.value ? +e.target.value : undefined)}/></label>}
                  {form.kind === "Репетиция" && (
                    <div className="row rehearsal">
                      <label>{tr("Длительность, мин")}{tr(" ")}
                        <input
                          type="number"
                          min="15"
                          max="480"
                          value={form.duration ?? 120}
                          onChange={(e) => update("duration", +e.target.value)}
                        />
                      </label>
                      {prod?.data.scenes.map((s: Obj, i: number) => (
                        <label key={i}>
                          <input
                            type="checkbox"
                            checked={form.scenes?.includes(i)}
                            onChange={(e) =>
                              update(
                                "scenes",
                                e.target.checked
                                  ? [...form.scenes, i]
                                  : form.scenes.filter((x: number) => x !== i),
                              )
                            }
                          />
                          {s.name}
                        </label>
                      ))}
                    </div>
                  )}
                  {tr(form.kind !== "Репетиция" && (
                    <label className="row">
                      <input
                        type="checkbox"
                        checked={!!form.run_through}
                        onChange={(e) =>
                          update("run_through", e.target.checked)
                        }
                      />{tr("Прогон на площадке в день спектакля (начало в 11:00)")}</label>
                  ))}
                  <label className="field">
                    <span>{tr("Примечание к событию")}</span>
                    <textarea
                      maxLength={8000}
                      value={form.notes || ""}
                      onChange={(e) => update("notes", e.target.value)}
                      placeholder={tr("Пометки для помрежа и служб")}
                    />
                  </label>
                  <div className="assign-footer">
                    <label>
                      <input
                        type="checkbox"
                        checked={form.adaptation}
                        onChange={(e) => update("adaptation", e.target.checked)}
                      />{tr(" ")}{tr("Использовать согласованную адаптацию площадки")}</label>
                    <button
                      className="primary"
                      disabled={busy || !live || !form.production_id || !form.venue_id}
                      onClick={() => analyze()}
                    >{tr("Проверить и назначить ")}<ArrowRight size={17} />
                    </button>
                  </div>
                </div>
                <HistorySuggestions request={form} api={api} onReview={analyze}/>
                <div className="section-title">
                  <h3>{tr("Всё под контролем")}</h3>
                  <span className="muted">
                    {tr(live
                      ? "Проверено по локальной базе"
                      : "Проверяем доступность…")}
                  </span>
                </div>
                <div className="validation-grid">
                  {tr([
                    "Артисты",
                    "Режиссёр",
                    "Помреж",
                    "Дирижёр",
                    "Хор",
                    "Балет",
                    "Оркестр",
                    "Техдир",
                    "Звук",
                    "Свет",
                    "Видео",
                    "Сцена",
                    "Верхняя механика",
                    "Софиты",
                    "Оборудование",
                    "Логистика",
                  ].map((d) => {
                    let ids =
                      live?.assignments
                        .filter((a: Obj) => a.department === d)
                        .map((a: Obj) => a.actual_id) || [];
                    let codes: Obj = {
                      "Верхняя механика": [
                        "fly_system",
                        "fly_bars",
                        "bar_capacity",
                        "movement",
                      ],
                      Софиты: ["soffits", "preferred_soffits"],
                      Логистика: [
                        "travel",
                        "setup",
                        "teardown",
                        "gate_width",
                        "gate_height",
                      ],
                      Оборудование: [
                        "resource_status",
                        "maintenance",
                        "kit_missing",
                      ],
                    };
                    let cs =
                      live?.conflicts.filter(
                        (c: Obj) =>
                          ids.includes(c.resource_id) ||
                          resource(c.resource_id)?.department === d ||
                          codes[d]?.includes(c.code) ||
                          (d === "Оборудование" &&
                            ["Equipment", "Equipment Kit"].includes(
                              resource(c.resource_id)?.kind,
                            )),
                      ) || [];
                    let st = !live
                      ? "wait"
                      : cs.some((c: Obj) =>
                            ["ERROR", "CRITICAL"].includes(c.severity),
                          )
                        ? "bad"
                        : cs.length
                          ? "warn"
                          : "ok";
                    return (
                      <div
                        className={"validation " + st}
                        key={d}
                        role={
                          form.kind === "Репетиция" && departments.includes(d)
                            ? "button"
                            : undefined
                        }
                        tabIndex={0}
                        onClick={() => {
                          if (
                            form.kind === "Репетиция" &&
                            departments.includes(d)
                          )
                            setRehearsalDept(d);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && form.kind === "Репетиция")
                            setRehearsalDept(d);
                        }}
                      >
                        <span>{tr(ru(d))}</span>
                        <span>
                          {tr(st === "wait"
                            ? "…"
                            : st === "ok"
                              ? "✓"
                              : st === "warn"
                                ? "⚠"
                                : "×")}
                        </span>
                      </div>
                    );
                  }))}
                </div>
                {form.kind === "Репетиция" && (
                  <section className="panel">
                    <h3>{tr("Кто нужен на репетиции")}</h3>
                    <p>{tr("Выберите цех и конкретных людей. В расписание попадут только выбранные участники.")}</p>
                    <div className="toolbar">
                      {tr(departments.map((d) => (
                        <button
                          key={d}
                          className={d === rehearsalDept ? "primary" : ""}
                          onClick={() => {
                            setRehearsalDept(d);
                            if (form.rehearsal_people == null)
                              update("rehearsal_people", []);
                          }}
                        >
                          {tr(ru(d))}
                        </button>
                      )))}
                    </div>
                    <div className="row">
                      <button onClick={() => update("rehearsal_people", null)}>{tr("Состав постановки автоматически")}</button>
                      <button onClick={() => update("rehearsal_people", [])}>{tr("Очистить выбор")}</button>
                      <b>{tr("Выбрано:")}{tr(" ")}
                        {
                          tr((
                            form.rehearsal_people ??
                            live?.assignments.map((a: Obj) => a.actual_id) ??
                            []
                          ).length)
                        }
                      </b>
                    </div>
                    {rehearsalDept && (
                      <div className="resource-grid">
                        {resources
                          .filter(
                            (r) =>
                              r.kind === "Person" &&
                              !r.data?.retired && (r.data?.qualification || []).includes(rehearsalDept),
                          )
                          .map((r) => (
                            <label className="rehearsal-person" key={r.id}>
                              <input
                                type="checkbox"
                                checked={(
                                  form.rehearsal_people ??
                                  live?.assignments.map(
                                    (a: Obj) => a.actual_id,
                                  ) ??
                                  []
                                ).includes(r.id)}
                                onChange={(e) => {
                                  const ids =
                                    form.rehearsal_people ??
                                    live?.assignments.map(
                                      (a: Obj) => a.actual_id,
                                    ) ??
                                    [];
                                  update(
                                    "rehearsal_people",
                                    e.target.checked
                                      ? [...new Set([...ids, r.id])]
                                      : ids.filter((id: number) => id !== r.id),
                                  );
                                }}
                              />
                              <span><b>{r.name}</b>
                              <small>{tr(ru(r.data.specialization))}</small></span>
                            </label>
                          ))}
                      </div>
                    )}
                  </section>
                )}
                <div className="two-col">
                  <section className="panel">
                    <div className="section-title">
                      <h3>{tr("Производственная версия")}</h3>
                      {tr(live && <Badge value={live.status} />)}
                    </div>
                    <h2>{ru(prod?.name)}</h2>
                    <p className="muted">
                      {tr(prod?.data.genre)}{tr(" · ")}{tr(prod?.data.duration)}{tr(" мин · версия")}{tr(" ")}
                      {tr(ru(prod?.version))}
                    </p>
                    <div className="stats">
                      <div>
                        <b>{tr(live?.assignments.length || "—")}</b>
                        <span>{tr("участников")}</span>
                      </div>
                      <div>
                        <b>{tr(live ? time(live.tasks[0].start) : "—")}</b>
                        <span>{tr("начало подготовки")}</span>
                      </div>
                      <div>
                        <b>{tr(live?.conflicts.length ?? "—")}</b>
                        <span>{tr("замечаний")}</span>
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        go("Постановки");
                        setSelected(prod || null);
                      }}
                    >{tr("Открыть постановку ")}<MoveUpRight size={16} />
                    </button>
                  </section>
                  <section className="panel tinted">
                    <div className="eyebrow">{tr("ПЛАН БЕЗ РИСКА")}</div>
                    <h2>{tr("А если перенести?")}</h2>
                    <p>{tr("Меняйте время, состав и площадку. Все варианты остаются предварительными до подтверждения.")}</p>
                    <div className="row">
                      <button onClick={() => analyze()}>{tr("Изменить ")}<ArrowRight size={16} />
                      </button>
                      {tr(form.kind === "Репетиция" && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            run(async () =>
                              setWindows(await api("/windows", "POST", form)),
                            )
                          }
                        >{tr("Найти 3 окна")}</button>
                      ))}
                    </div>
                    {tr(windows.map((w) => (
                      <button key={w.start} onClick={() => setForm(w.request)}>
                        {tr(date(w.start))}{tr(" · ")}{tr(time(w.start))}
                      </button>
                    )))}
                  </section>
                </div>
                {tr(live && live.conflicts.length > 0 && (
                  <section className="panel">
                    <h3>{tr("Что требует внимания")}</h3>
                    {tr(conflicts(live))}
                  </section>
                ))}
              </>
            )}
            {page === "Календарь" && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">{tr("ЛЮДИ И ПРОИЗВОДСТВО В ОДНОМ РИТМЕ")}</div>
                    <h1>{tr("Календарь")}</h1>
                  </div>
                  <button onClick={()=>setShowExport(true)}>{tr("Экспорт расписания")}</button>
                  <button
                    className="primary"
                    onClick={() => {
                      setForm(newEventForm);
                      go("Назначить");
                    }}
                  >
                    <Plus size={17} />{tr("Создать событие")}</button>
                </div>
                <div className="calendar-tools">
                  <div className="segmented">
                    {tr([
                      ["timeGridDay", "День"],
                      ["timeGridWeek", "Неделя"],
                      ["dayGridMonth", "Месяц"],
                      ["production", "Производство"],
                    ].map(([v, n]) => (
                      <button
                        key={v}
                        className={view === v ? "chosen" : ""}
                        onClick={() => {
                          setView(v);
                          if (v !== "production")
                            setTimeout(
                              () =>
                                cal.current?.getApi().changeView(v, calDate),
                              0,
                            );

                        }}
                      >
                        {tr(n)}
                      </button>
                    )))}
                  </div>
                  <label className="search-inline">
                    <Search size={16} />
                    <input
                      placeholder={tr("Найти в расписании")}
                      value={filter.q || ""}
                      onChange={(e) =>
                        setFilter({ ...filter, q: e.target.value })
                      }
                    />
                  </label>
                </div>
                <div className="filters">
                  <label className="row">
                    <input
                      type="checkbox"
                      checked={showTasks}
                      onChange={(e) => setShowTasks(e.target.checked)}
                    />{tr("Подготовка и выезды")}</label>
                  <SlidersHorizontal size={16} />
                  {[
                    [
                      "kind",
                      "Тип",
                      [
                        "Спектакль",
                        "Репетиция",
                        "Монтаж",
                        "Выездное мероприятие",
                      ].map((x) => ({ id: x, name: x })),
                    ],
                    [
                      "department",
                      "Подразделение",
                      departments.map((x) => ({ id: x, name: x })),
                    ],
                    [
                      "venue",
                      "Площадка",
                      resources.filter((r) => r.kind === "Venue"),
                    ],
                    [
                      "person",
                      "Сотрудник",
                      resources.filter((r) => r.kind === "Person"),
                    ],
                    ["production", "Постановка", productions],
                    [
                      "equipment",
                      "Equipment Kit",
                      resources.filter((r) => r.kind === "Equipment Kit"),
                    ],
                  ].map(([key, label, opts]: any) => (
                    <select
                      aria-label={"Фильтр " + ru(label)}
                      key={key}
                      value={filter[key] || ""}
                      onChange={(e) =>
                        setFilter({ ...filter, [key]: e.target.value })
                      }
                    >
                      <option value="">{tr(ru(label))}</option>
                      {opts.map((o: Obj) => (
                        <option key={o.id} value={o.id}>
                          {o.kind || typeof o.id === "number" ? o.name : ru(o.name)}
                        </option>
                      ))}
                    </select>
                  ))}
                  <button onClick={() => setFilter({})}>{tr("Сброс")}</button>
                </div>
                <div className="calendar-panel">
                  {tr((busy || calendarBusy) && (
                    <div className="cal-loading">{tr("Обновляем расписание…")}</div>
                  ))}
                  {view === "production" ? (
                    <>
                      <div className="row">
                        <input
                          aria-label={tr("Дата производства")}
                          type="date"
                          value={calDate}
                          onChange={(e) => {
                            setCalDate(e.target.value);

                          }}
                        />
                      </div>
                      {slots.length ? (
                        slots.map((e) => (
                          <section className="panel" key={e.id}>
                            <div className="section-title">
                              <h3>
                                {e.title}{tr(" · ")}{tr(date(e.start))}
                              </h3>
                              <button onClick={() => openEvent(e.id)}>{tr("Открыть")}</button>
                            </div>
                            {tr(timeline(e.tasks))}
                          </section>
                        ))
                      ) : (
                        <div className="empty">{tr("Выберите дату с событиями, чтобы увидеть производственную цепочку.")}</div>
                      )}
                    </>
                  ) : (
                    <FullCalendar
                      ref={cal}
                      plugins={[
                        dayGridPlugin,
                        timeGridPlugin,
                        interactionPlugin,
                      ]}
                      locale={language === "ru" ? ruLocale : "en-gb"}
                      initialView={view}
                      initialDate={calDate}
                      firstDay={1}
                      headerToolbar={{
                        left: "today prev,next",
                        center: "title",
                        right: "",
                      }}
                      height="auto"
                      allDaySlot={true}
                      slotMinTime="07:00:00"
                      slotMaxTime="25:00:00"
                      slotDuration="00:30:00"
                      nowIndicator
                      eventDidMount={(arg) => {
                        arg.el.dataset.eventId = arg.event.id;
                        arg.el.dataset.start = arg.event.start
                          ? local(arg.event.start)
                          : "";
                      }}
                      selectable
                      editable
                      eventResizableFromStart={false}
                      datesSet={(arg) => {
                        const d =
                          arg.view.type === "timeGridDay"
                            ? arg.start
                            : arg.view.currentStart;
                        setCalDate(local(d).slice(0, 10));
                      }}
                      events={[
                        ...events.map((e) => ({
                          id: String(e.id),
                          title:
                            e.title +
                            " · " +
                            e.venue +
                            (e.health === "CONFLICT" ? " ⚠" : ""),
                          start: e.start,
                          end: e.end,
                          color:
                            e.health === "CONFLICT"
                              ? "#bc716a"
                              : e.kind === "Репетиция"
                                ? "#7975ad"
                                : "#2c8477",
                          durationEditable: true,
                          extendedProps: { event: e },
                        })),
                        ...(showTasks
                          ? events.flatMap((e) =>
                              (e.tasks || [])
                                .filter(
                                  (t: Obj) =>
                                    !["Спектакль", "Репетиция"].includes(
                                      t.name,
                                    ) &&
                                    (!filter.department ||
                                      t.department === filter.department ||
                                      t.department === "Все"),
                                )
                                .map((t: Obj) => ({
                                  id: "task-" + t.id,
                                  title: t.name + " · " + e.title,
                                  start: t.start,
                                  end: t.end,
                                  color: "#7b96a3",
                                  editable: false,
                                  extendedProps: { event: e },
                                })),
                            )
                          : []),
                        ...blocks
                          .filter(
                            (b) =>
                              (!filter.department || resource(b.resource_id)?.department === filter.department) &&
                              (!filter.q || (b.label + " " + (resource(b.resource_id)?.name || "")).toLowerCase().includes(String(filter.q).toLowerCase())) &&
                              (!filter.production && !filter.kind) &&
                              (!filter.person ||
                                +filter.person === b.resource_id) &&
                              (!filter.venue ||
                                +filter.venue === b.resource_id) &&
                              (!filter.equipment ||
                                +filter.equipment === b.resource_id),
                          )
                          .map((b) => ({
                            id: "block-" + b.id,
                            title:
                              b.label + " · " + resource(b.resource_id)?.name,
                            start: b.start,
                            end: b.end,
                            color: "#9b916f",
                            editable: false,
                          })),
                      ]}
                      eventClick={(arg) => {
                        if (!arg.event.id.startsWith("block-"))
                          openEvent(
                            arg.event.extendedProps.event?.id || +arg.event.id,
                          );
                      }}
                      dateClick={(arg) => {
                        setCalDate(arg.dateStr.slice(0, 10));
                        if (arg.view.type === "dayGridMonth") {
                          setView("timeGridDay");
                          cal.current
                            ?.getApi()
                            .changeView("timeGridDay", arg.date);
                        } else {
                          setForm(f => newEventForm({ ...f, start: local(arg.date) }));
                          go("Назначить");
                        }
                      }}
                      eventDrop={(arg) => {
                        const e = arg.event.extendedProps.event;
                        const start = local(arg.event.start!);
                        arg.revert();
                        analyze(shiftedStart(e.data.request, start));
                      }}
                      eventResize={(arg) => {
                        const e = arg.event.extendedProps.event;
                        const duration = Math.round(
                          (+arg.event.end! - +arg.event.start!) / 60000,
                        );
                        arg.revert();
                        analyze({ ...e.data.request, duration });
                      }}
                    />
                  )}
                </div>
                <p className="muted">{tr("Перенос и изменение длительности сначала открывают Предварительный план. До подтверждения расписание не меняется.")}</p>
              </>
            )}
            {tr((page === "Добавить спектакль" ||
              (page === "Постановки" && passport)) &&
              passport && (
                <PassportEditor
                  key={passport.id || "new"}
                  initial={passport}
                  resources={resources}
                  onCreate={async (body) => {
                    const units = await api("/inventory/units", "POST", body);
                    await load();
                    return units;
                  }}
                  onCancel={() => {
                    setPassport(null);
                    go("Постановки");
                  }}
                  onSave={async (p) => {
                    const saved = await api(
                      "/productions" + (p.id ? "/" + p.id : ""),
                      p.id ? "PATCH" : "POST",
                      p,
                    );
                    await load();
                    setPassport(null);
                    go("Постановки");
                    setSelected(saved);
                    setToast("Паспорт постановки сохранён");
                  }}
                />
              ))}
            {page === "Постановки" && !passport && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">{tr("РЕПЕРТУАР И ПРОИЗВОДСТВЕННЫЕ ПАСПОРТА")}</div>
                    <h1>{selected?.name || tr("Постановки")}</h1>
                  </div>
                  {tr(selected && (
                    <button
                      onClick={() =>
                        setPassport(JSON.parse(JSON.stringify(selected)))
                      }
                    >{tr("Редактировать постановку")}</button>
                  ))}
                  <button onClick={() => go("Добавить спектакль")}>{tr("Добавить спектакль")}</button>
                  {tr(selected && (
                    <button onClick={() => setSelected(null)}>{tr("Все постановки")}</button>
                  ))}
                </div>
                {!selected ? (
                  <div className="production-grid">
                    {productions.map((p, i) => (
                      <button
                        className="production-card"
                        key={p.id}
                        onClick={() => {
                          setSelected(p);
                          setTab("Люди");
                        }}
                      >
                        <div className={"poster poster" + i}>
                          <span>{tr("СЦЕНА / ")}{tr(String(i + 1).padStart(2, "0"))}</span>
                          <div className="poster-orbit" />
                          <b>{ru(p.name)}</b>
                        </div>
                        <div className="production-caption">
                          <span>{tr(p.data.genre)}</span>
                          <h3>{ru(p.name)}</h3>
                          <p>
                            {tr(p.data.duration)}{tr(" мин")}{tr(" ")}
                            <span>{p.data.source_metadata?.technical_passport_complete===false?tr("Подготовка не указана"):<>{tr("Подготовка ")}{tr(Math.floor(p.data.preparation / 60))}{tr(":")}{tr(String(p.data.preparation % 60).padStart(2, "0"))}</>}
                            </span>
                          </p>
                          <div>
                            <Badge value={p.data.source_metadata?.technical_passport_complete===false?"Паспорт требует заполнения":"Активна"} />
                            <small>
                              {ru(resource(p.data.home_venue)?.name)}
                            </small>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <>
                    <div className="metrics">
                      <div>
                        <small>{tr("ВЕРСИЯ")}</small>
                        <b>{tr(ru(selected.version))}</b>
                      </div>
                      <div>
                        <small>{tr("ПРОДОЛЖИТЕЛЬНОСТЬ")}</small>
                        <b>{tr(selected.data.duration)}{tr(" мин")}</b>
                      </div>
                      <div>
                        <small>{tr("БАЗОВАЯ ПОДГОТОВКА")}</small>
                        <b>{selected.data.source_metadata?.technical_passport_complete===false?tr("Не указана"):<>{tr(selected.data.preparation)}{tr(" мин")}</>}</b>
                      </div>
                      <div>
                        <small>{tr("ОСНОВНАЯ ПЛОЩАДКА")}</small>
                        <b>{ru(resource(selected.data.home_venue)?.name)}</b>
                      </div>
                    </div>
                    <ImportedData data={selected.data} resource={resource}/>
                    <CastProposal key={`${selected.id}:${selected.version}`} production={selected} api={api} onSaved={async p=>{await load();setSelected(p);setToast(tr('Составы сохранены'));}}/>
                    <div className="segmented big">
                      <button
                        className={tab === "Люди" ? "chosen" : ""}
                        onClick={() => setTab("Люди")}
                      >
                        <Users size={18} />{tr("Люди")}</button>
                      <button
                        className={tab === "Техника" ? "chosen" : ""}
                        onClick={() => setTab("Техника")}
                      >
                        <Boxes size={18} />{tr("Техника")}</button>
                    </div>
                    {tab === "Люди" ? (
                      <div className="accordion-grid">
                        <details open>
                          <summary>{tr("Артисты · составы A / B")}</summary>
                          {selected.data.roles.map((r: Obj) => (
                            <div className="cast-row" key={r.role}>
                              <b>{tr(ru(r.role))}</b>
                              <span>{tr("A · ")}{ru(resource(r.A)?.name)}</span>
                              <span>{tr("B · ")}{ru(resource(r.B)?.name)}</span>
                              <small>{tr("Допущенные исполнители · ")}{(r.eligible||[]).map((id:number)=>resource(id)?.name).filter(Boolean).join(", ")||"—"}
                              </small>
                            </div>
                          ))}
                        </details>
                        <details open>
                          <summary>{tr("Руководство и ответственные")}</summary>
                          {Object.entries(selected.data.responsibles).map(
                            ([d, id]: any) => (
                              <div className="personline" key={d}>
                                <span>{tr(ru(d))}</span>
                                <b>{ru(resource(id)?.name)}</b>
                              </div>
                            ),
                          )}
                        </details>
                        {Object.entries(selected.data.groups).map(
                          ([d, ids]: any) => (
                            <details key={d}>
                              <summary>
                                {tr(ru(d))}
                                <span>{tr(ids.length)}</span>
                              </summary>
                              {tr(d === "Оркестр" &&
                                Object.entries(
                                  selected.data.orchestra_versions,
                                ).map(([v, arr]: any) => (
                                  <p key={v}>
                                    {tr(ru(v))}{tr(": ")}{tr(arr.length)}{tr(" музыкантов")}</p>
                                )))}
                              {selected.data.groups_casts?.[d] ? ["A","B"].map(cast=><section key={cast}><h4>{tr(cast === "A" ? "Первый состав" : "Второй состав")}</h4>{(selected.data.groups_casts[d][cast] ?? ids).map((id:number)=><div className="personline" key={id}><span>{resource(id)?.name}</span><small>{tr(ru(resource(id)?.data.specialization))}</small></div>)}</section>) : ids.map((id: number) => (
                                <div className="personline" key={id}>
                                  <span>{ru(resource(id)?.name)}</span>
                                  <small>
                                    {tr(ru(resource(id)?.data.specialization))}
                                  </small>
                                </div>
                              ))}
                            </details>
                          ),
                        )}
                        {Object.entries(selected.data.crew).map(
                          ([d, ids]: any) => (
                            <details key={d + "crew"}>
                              <summary>{tr("Техническая группа · ")}{tr(ru(d))}
                                <span>{tr(ids.length)}</span>
                              </summary>
                              {selected.data.crew_casts?.[d] ? ["A","B"].map(cast=><section key={cast}><h4>{tr(cast === "A" ? "Первый состав" : "Второй состав")}</h4>{(selected.data.crew_casts[d][cast] ?? ids).map((id:number)=><div className="personline" key={id}><span>{resource(id)?.name}</span><small>{tr(ru(resource(id)?.data.specialization))}</small></div>)}</section>) : ids.map((id: number) => (
                                <div className="personline" key={id}>
                                  {ru(resource(id)?.name)}
                                  <small>{tr("Квалификация ")}{tr(resource(id)?.data.level)}
                                  </small>
                                </div>
                              ))}
                            </details>
                          ),
                        )}
                      </div>
                    ) : (
                      <div className="accordion-grid">
                        {["scenery", "props", "equipment_kits"].map(
                          (key, i) => (
                            <details open key={key}>
                              <summary>
                                {
                                  tr([
                                    "Декорации",
                                    "Реквизит и костюмы",
                                    "Звук · свет · видео",
                                  ][i])
                                }
                              </summary>
                              {selected.data[key].map((id: number) => {
                                let r = resource(id);
                                return (
                                  <div key={id} className="resource-line">
                                    <b>{ru(r?.name)}</b>
                                    {r?.kind === "Scenery" ? (
                                      <p>
                                        {tr(r.data.width)}{tr(" × ")}{tr(r.data.depth)}{tr(" ×")}{tr(" ")}
                                        {tr(r.data.height)}{tr(" м · ")}{tr(r.data.mass)}{tr(" кг ·")}{tr(" ")}
                                        {tr(r.data.installation)}{tr(" · ")}{tr(r.data.crew)}{tr(" ")}{tr("монтажника")}</p>
                                    ) : r?.kind === "Equipment Kit" ? (
                                      <p>
                                        {r.data.items
                                          .map((i: number) => resource(i)?.name)
                                          .join(" · ")}
                                      </p>
                                    ) : (
                                      <p>{tr("Критический · ")}{tr(r?.data.quantity)}{tr(" шт.")}</p>
                                    )}
                                  </div>
                                );
                              })}
                            </details>
                          ),
                        )}
                        <details open>
                          <summary>{tr("Механика и световая инфраструктура")}</summary>
                          {!!selected.data.items?.length && (
                            <div className="panel">
                              <h3>{tr("Поштучное имущество")}</h3>
                              {Object.entries(
                                (selected.data.items as number[]).reduce(
                                  (groups: Obj, id: number) => {
                                    const r = resource(id);
                                    const name =
                                      r?.data.item_name ||
                                      r?.name ||
                                      String(id);
                                    groups[name] = (groups[name] || 0) + 1;
                                    return groups;
                                  },
                                  {},
                                ),
                              ).map(([name, count]) => (
                                <p key={name}>
                                  {tr(ru(name))}{tr(" — ")}{tr(String(count))}{tr(" шт.")}</p>
                              ))}
                            </div>
                          )}
                          {tr(Object.entries(selected.data.requirements).map(
                            ([k, v]: any) => (
                              <div className="personline" key={k}>
                                <span>{tr(ru(k))}</span>
                                <b>{tr(ru(v))}</b>
                              </div>
                            ),
                          ))}
                        </details>
                        <details>
                          <summary>{tr("Этапы подготовки")}</summary>
                          {tr(Object.entries(selected.data.pipeline).map(
                            ([k, v]: any) => (
                              <div className="personline" key={k}>
                                <span>{tr(ru(k))}</span>
                                <b>{tr(ru(v))}{tr(" мин")}</b>
                              </div>
                            ),
                          ))}
                        </details>
                        <details>
                          <summary>{tr("Адаптации площадок")}</summary>
                          {Object.entries(selected.data.overrides).length ? (
                            Object.entries(selected.data.overrides).map(
                              ([id, v]: any) => (
                                <p key={id}>
                                  {ru(resource(+id)?.name)}{tr(" · ")}{tr(ru(v.version))}
                                  <br />
                                  {tr(v.note)}
                                </p>
                              ),
                            )
                          ) : (
                            <p>{tr("Отдельные адаптации не заданы")}</p>
                          )}
                        </details>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
            {tr(page === "Площадки" && venueEditor && (
              <VenueEditor
                initial={venueEditor}
                onCancel={() => setVenueEditor(null)}
                onSave={async (body) => {
                  const v = await api(
                    "/venues" + (body.id ? "/" + body.id : ""),
                    body.id ? "PATCH" : "POST",
                    body,
                  );
                  await load();
                  setVenueEditor(null);
                  setSelected(v);
                  setToast("Площадка сохранена");
                }}
              />
            ))}
            {[
              "Сотрудники",
              "Оркестр",
              "Площадки",
              "Оборудование",
              "Сценическая механика",
            ].includes(page) &&
              !venueEditor && (
                <>
                  <div className="page-title">
                    <div>
                      <div className="eyebrow">{tr("ЕДИНАЯ БАЗА РЕСУРСОВ")}</div>
                      <h1>{tr(page)}</h1>
                    </div>
                    <button
                      onClick={() =>
                        page === "Площадки"
                          ? setVenueEditor({ name: "", data: {} })
                          : setResourceEditor({
                              kind:
                                page === "Сотрудники" || page === "Оркестр"
                                  ? "Person"
                                  : "Equipment",
                              name: "",
                              department:
                                page === "Оркестр" ? "Оркестр" : "",
                              specialization: "",
                            })
                      }
                    >
                      <Plus size={16} />
                      {tr(page === "Площадки"
                        ? "Добавить площадку"
                        : page === "Сотрудники"
                          ? "Добавить сотрудника"
                          : "Добавить ресурс")}
                    </button>
                    <label className="search-inline">
                      <Search size={16} />
                      <input
                        placeholder={tr("Найти ресурс")}
                        value={find}
                        onChange={(e) => setFind(e.target.value)}
                      />
                    </label>
                  </div>
                  {tr(!selected &&
                    ["Сотрудники", "Оборудование"].includes(page) && (
                      <section className="panel">
                        <div className="toolbar">
                          <button
                            onClick={() => {
                              setCatalogDept("");
                              setCatalogCategory("");
                            }}
                          >{tr("Все цеха")}</button>
                          {tr([
                            ...new Set(
                              resources
                                .filter((r) =>
                                  page === "Сотрудники"
                                    ? r.kind === "Person"
                                    : [
                                        "Equipment",
                                        "Equipment Kit",
                                        "Vehicle",
                                        "Scenery",
                                        "Prop",
                                        "Costume",
                                      ].includes(r.kind),
                                )
                                .map((r) => r.department),
                            ),
                          ].map((d) => (
                            <button
                              className={catalogDept === d ? "primary" : ""}
                              key={d}
                              onClick={() => {
                                setCatalogDept(d);
                                setCatalogCategory("");
                              }}
                            >
                              {tr(ru(d))}
                            </button>
                          )))}
                        </div>
                        {tr(page === "Оборудование" && catalogDept && (
                          <div className="toolbar">
                            {tr([
                              ...new Set([
                                ...(catalogDept === "Звук"
                                  ? ["Микрофоны", "Консоли", "Мониторы"]
                                  : catalogDept === "Свет"
                                    ? [
                                        "BSW",
                                        "Wash",
                                        "LED Bar",
                                        "Консоли",
                                        "Дымка",
                                        "Дым",
                                      ]
                                    : []),
                                ...resources
                                  .filter(
                                    (r) =>
                                      r.department === catalogDept &&
                                      ["Equipment", "Equipment Kit"].includes(
                                        r.kind,
                                      ),
                                  )
                                  .map(equipmentCategory),
                              ]),
                            ].map((c) => (
                              <button
                                key={c}
                                className={
                                  catalogCategory === c ? "primary" : ""
                                }
                                onClick={() => setCatalogCategory(c)}
                              >
                                {tr(ru(c))}
                              </button>
                            )))}
                          </div>
                        ))}
                      </section>
                    ))}
                  {selected ? (
                    <section className="panel">
                      <div className="section-title">
                        <h2>{ru(selected.name)}</h2>
                        <button onClick={() => setSelected(null)}>{tr("Назад")}</button>
                      </div>
                      {tr(selected.kind === "Person" && (
                        <>
                          <h3>{tr("Статистика сотрудника · всё расписание")}</h3>
                          {tr(personStats ? (
                            <div className="metrics">
                              {tr(Object.entries({
                                Событий: personStats.events,
                                "Часов занятости": personStats.hours,
                                Спектаклей: personStats.performances,
                                Репетиций: personStats.rehearsals,
                                Замен: personStats.replacements,
                                "Интервалов отсутствия": personStats.absences,
                              }).map(([k, v]) => (
                                <div key={k}>
                                  <small>{tr(ru(k))}</small>
                                  <b>{tr(ru(v))}</b>
                                </div>
                              )))}
                            </div>
                          ) : (
                            <p>{tr("Загрузка статистики…")}</p>
                          ))}
                        </>
                      ))}
                      <div className="row">
                        <Badge value={selected.status} />
                        <button
                          onClick={() =>
                            selected.kind === "Venue"
                              ? setVenueEditor(selected)
                              : setResourceEditor({
                                  ...selected,
                                  specialization:
                                    selected.data.specialization || "",
                                })
                          }
                        >{tr("Редактировать")}</button>
                        <button
                          onClick={() =>
                            run(async () => {
                              await api("/resources/" + selected.id, "DELETE");
                              setSelected(null);
                              await load();
                              setToast("Ресурс удалён");
                            })
                          }
                        >{tr("Удалить")}</button>
                        <button onClick={() => personal(selected)}>{tr("Показать в календаре")}</button>
                        <select
                          aria-label={tr("Состояние ресурса")}
                          value={selected.status}
                          onChange={(e) =>
                            run(async () => {
                              const r = await api(
                                "/resources/" + selected.id,
                                "PATCH",
                                { status: e.target.value },
                              );
                              setSelected(r.resource);
                              await load();
                              setRevision((x) => x + 1);
                              setToast(
                                "Затронутые будущие события: " +
                                  (r.affected_events.join(", ") || "нет"),
                              );
                            })
                          }
                        >
                          {tr([
                            "available",
                            "reserved",
                            "in_use",
                            "in_transit",
                            "maintenance",
                            "broken",
                            "limited_use",
                          ].map((x) => (
                            <option key={x} value={x}>
                              {tr(ru(x))}
                            </option>
                          )))}
                        </select>
                      </div>
                      <div className="property-grid">
                        {Object.entries(selected.data).filter(([k])=>!isImportedMetadata(k)).map(([k, v]) => (
                          <div key={k}>
                            <small>{importedLabel(k)}</small>
                            <DataValue value={v} field={k} resource={resource}/>
                          </div>
                        ))}
                      </div>
                      <ImportedData data={selected.data} resource={resource}/>
                      {selected.kind === "Venue" && (
                        <>
                          <h3>{tr("Механика и позиции")}</h3>
                          <div className="resource-tags">
                            {resources
                              .filter((r) => r.data.venue_id === selected.id)
                              .map((r) => (
                                <button
                                  key={r.id}
                                  onClick={() => setSelected(r)}
                                >
                                  {r.name}{tr(" · ")}{tr(ru(r.status))}
                                </button>
                              ))}
                          </div>
                        </>
                      )}
                      <h3>{tr("Отсутствие / блокировка / обслуживание")}</h3>
                      <form
                        className="row"
                        onSubmit={(e) => {
                          e.preventDefault();
                          const fd = new FormData(e.currentTarget);
                          run(async () => {
                            await api("/blocks", "POST", {
                              resource_id: selected.id,
                              start: fd.get("start"),
                              end: fd.get("end"),
                              label: fd.get("label"),
                              state:
                                selected.kind === "Person"
                                  ? "absence"
                                  : "maintenance",
                            });
                            setRevision((x) => x + 1);
                            setToast("Интервал недоступности сохранён");
                          });
                        }}
                      >
                        <input required name="label" placeholder={tr("Причина")} />
                        <input required name="start" type="datetime-local" />
                        <input required name="end" type="datetime-local" />
                        <button type="submit">{tr("Сохранить")}</button>
                      </form>
                    </section>
                  ) : (
                    <div className="resource-grid">
                      {tr(page === "Оборудование" &&
                        catalogCategory &&
                        !resources.some(
                          (r) =>
                            r.department === catalogDept &&
                            equipmentCategory(r) === catalogCategory,
                        ) && (
                          <p className="notice">{tr("В категории «")}{tr(catalogCategory)}{tr("» пока нет оборудования. Добавьте ресурс и укажите эту категорию.")}</p>
                        ))}
                      {resources
                        .filter(
                          (r) =>
                            !["Сотрудники", "Оборудование"].includes(page) ||
                            ((!catalogDept || r.department === catalogDept) &&
                              (!catalogCategory ||
                                equipmentCategory(r) === catalogCategory)),
                        )
                        .filter((r) =>
                          page === "Сотрудники"
                            ? r.kind === "Person"
                            : page === "Оркестр"
                              ? r.kind === "Person" &&
                                r.department === "Оркестр"
                              : page === "Площадки"
                                ? r.kind === "Venue"
                                : page === "Сценическая механика"
                                  ? [
                                      "Fly Bar",
                                      "Soffit",
                                      "Lighting Position",
                                    ].includes(r.kind)
                                  : [
                                      "Equipment",
                                      "Equipment Kit",
                                      "Vehicle",
                                      "Scenery",
                                      "Prop",
                                      "Costume",
                                    ].includes(r.kind),
                        )
                        .filter((r) =>
                          (
                            r.name +
                            " " +
                            r.department +
                            " " +
                            r.data.specialization
                          )
                            .toLowerCase()
                            .includes(find.toLowerCase()),
                        )
                        .map((r) => (
                          <button
                            className="resource-card"
                            key={r.id}
                            onClick={() => setSelected(r)}
                          >
                            <span className="avatar">
                              {r.kind === "Person" ? (
                                r.name
                                  .split(" ")
                                  .map((x: string) => x[0])
                                  .join("")
                              ) : (
                                <Boxes size={20} />
                              )}
                            </span>
                            <div>
                              <h3>{r.name}</h3>
                              <p>
                                {tr(ru(r.department))}{tr(" ·")}{tr(" ")}
                                {tr(ru(r.data.specialization || r.kind))}
                              </p>
                              {tr(r.kind === "Venue" && (
                                <small>
                                  {tr(r.data.width)}{tr(" × ")}{tr(r.data.depth)}{tr(" м ·")}{tr(" ")}
                                  {tr(r.data.soffits)}{tr(" софитов · ")}{tr(r.data.fly_bars)}{tr(" ")}{tr("штанкетов")}</small>
                              ))}
                            </div>
                            <span className={"dot " + r.status} />
                          </button>
                        ))}
                    </div>
                  )}
                </>
              )}
            {page === "Аналитика" && analytics && (
              <>
                <h1>{tr("Производство в цифрах")}</h1>
                <div className="metrics">
                  <div>
                    <small>{tr("СОБЫТИЙ")}</small>
                    <b>{tr(analytics.events)}</b>
                  </div>
                  <div>
                    <small>{tr("АДАПТАЦИЙ")}</small>
                    <b>{tr(analytics.adaptations)}</b>
                  </div>
                  <div>
                    <small>{tr("ЗАМЕН")}</small>
                    <b>{tr(analytics.replacements)}</b>
                  </div>
                  <div>
                    <small>{tr("ЗАПИСЕЙ ФАКТА")}</small>
                    <b>{tr(analytics.actuals.length)}</b>
                  </div>
                </div>
                <div className="two-col">
                  <section className="panel">
                    <h3>{tr("Средняя нагрузка подразделений · часов на сотрудника")}</h3>
                    <p className="muted">{tr("Всё расписание. Пересечения одного сотрудника не суммируются; обед и отменённые события исключены.")}</p>
                    {tr(Object.entries(analytics.departments)
                      .filter(([k]) => k)
                      .map(([k, v]: any) => (
                        <div className="chart-row" key={k}>
                          <span>{tr(ru(k))}</span>
                          <div>
                            <i
                              style={{
                                width:
                                  (100 * v) /
                                    Math.max(
                                      ...(Object.values(
                                        analytics.departments,
                                      ) as number[]),
                                    ) +
                                  "%",
                              }}
                            />
                          </div>
                          <b>{tr(v)}{tr(" ч")}</b>
                          {analytics.department_stats?.[k] && <small>
                            {tr("Сотрудников:")} {analytics.department_stats[k].people} · {tr("Всего человеко-часов:")} {analytics.department_stats[k].person_hours}
                          </small>}
                        </div>
                      )))}
                  </section>
                  <section className="panel">
                    <h3>{tr("Загрузка сотрудников")}</h3>
                    <div className="scroll-list">
                      {analytics.resources
                        .filter((r: Obj) => r.kind === "Person")
                        .map((r: Obj) => (
                          <div className="personline" key={r.id}>
                            <span>
                              {r.name}
                              <small>{tr(ru(r.kind))}</small>
                            </span>
                            <b>{tr(r.hours)}{tr(" ч")}</b>
                          </div>
                        ))}
                    </div>
                  </section>
                </div>
                <section className="panel">
                  <h3>{tr("План / факт работ")}</h3>
                  {analytics.actuals.length ? (
                    analytics.actuals.map((a: Obj, i: number) => (
                      <p key={i}>
                        {ru(a.name)}{tr(": план ")}{tr(a.planned)}{tr(" мин → факт ")}{a.actual}{tr(" ")}{tr("мин")}</p>
                    ))
                  ) : (
                    <p className="muted">{tr("Фактические интервалы пока не внесены. Откройте событие → Факт работ.")}</p>
                  )}
                </section>
              </>
            )}
            {tr(page === "Stage Assistant" && (
              <section className="assistant panel">
                <div className="assistant-icon">
                  <Sparkles size={30} />
                </div>
                <h1>{tr("Помощник StageOS")}</h1>
                <p>{tr("Задайте вопрос о постановках, сотрудниках или расписании.")}<br />{tr("Помощник отвечает по базе выбранного театра. Для создания события откройте «Назначить».")}</p>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={tr("Кто ведёт звук на Северном ветре?")}
                />
                <button
                  className="primary"
                  disabled={busy || !question}
                  onClick={() =>
                    run(async () => {
                      const a = await api("/assistant", "POST", {
                        language,
                        text: question,
                      });
                      setAnswer(a.answer);
                      if (a.preview) setPreview(a.preview);
                    })
                  }
                >
                  {tr(busy ? "Проверяем данные…" : "Спросить")}
                  <ArrowRight size={17} />
                </button>
                {tr(answer && <div className="answer">{tr(ru(answer))}</div>)}
                <button onClick={() => go("Настройки")}>{tr("Подключить локальную модель")}</button>
              </section>
            ))}
            {page === "Уведомления" && (
              <>
                <h1>{tr("Уведомления и согласования")}</h1>
                <section className="panel">
                  {notes.map((n) => (
                    <details key={n.id}>
                      <summary>
                        <b>{tr(ru(n.action))}</b>
                        <span>
                          {tr(date(n.created))} {tr(time(n.created))}
                        </span>
                        {tr(n.data.state && <Badge value={n.data.state} />)}
                      </summary>
                      {n.action === "PROPOSED" ? (
                        <>
                          <p>
                            {n.data.plan.title}{tr(" · ")}{tr(date(n.data.plan.start))}
                          </p>
                          <button onClick={() => setPreview(n.data.plan)}>{tr("Посмотреть предложение")}</button>
                          {tr(n.data.reason && <p>{tr(ru(n.data.reason))}</p>)}
                          {n.data.state === "Pending Approval" && (canApprove ? (
                            <ApprovalActions plan={n.data.plan} busy={busy}
                              reject={() => run(async () => {
                                await api("/proposals/" + n.id + "/reject", "POST", {reason: "Отклонено пользователем"});
                                setRevision(x => x + 1); setToast("Предложение отклонено");
                              })}
                              approve={body => run(async () => {
                                await api("/proposals/" + n.id + "/approve", "POST", body);
                                setRevision(x => x + 1); setToast("Предложение согласовано");
                              })}/>
                          ) : <p className="notice">{tr("Ожидает согласования администратора или художественного руководителя")}</p>)}
                        </>
                      ) : (
                        <p>
                          {tr(n.event_id
                            ? "Событие № " + n.event_id
                            : "Обновление ресурса")}
                          {tr(n.data.reason && " · " + n.data.reason)}
                        </p>
                      )}
                    </details>
                  ))}
                </section>
              </>
            )}
            {page === "Настройки" && settings && (
              <>
                <button onClick={()=>setShowQualifications(true)}>{tr("Управление квалификациями")}</button>
                <h1>{tr("Настройки")}</h1>
                <section className="panel">
                  <h3>{tr("База театра")}</h3>
                  <div className="row">
                    <button onClick={exportDatabase}>{tr("Скачать резервную копию")}</button>
                    <button
                      onClick={() =>
                        document.getElementById("database-upload")?.click()
                      }
                    >{tr("Открыть существующую базу")}</button>
                  </div>
                </section>
                <div className="two-col">
                  <section className="panel">
                    <h3>{tr("Локальный помощник")}</h3>
                    <label className="row">
                      <input
                        type="checkbox"
                        checked={settings.enabled}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            enabled: e.target.checked,
                          })
                        }
                      />{tr("Включить локального помощника")}</label>
                    {tr(picker(
                      "Провайдер",
                      "provider",
                      ["Ollama", "LM Studio", "llama.cpp", "Custom"].map(
                        (x) => ({ id: x, name: x }),
                      ),
                      settings.provider,
                      (v) =>
                        setSettings({
                          ...settings,
                          provider: v,
                          endpoint:
                            v === "Ollama"
                              ? "http://127.0.0.1:11434/v1"
                              : v === "LM Studio"
                                ? "http://127.0.0.1:1234/v1"
                                : "http://127.0.0.1:8080/v1",
                        }),
                    ))}
                    <label className="field">
                      <span>{tr("Адрес сервера модели")}</span>
                      <input
                        value={settings.endpoint}
                        onChange={(e) =>
                          setSettings({ ...settings, endpoint: e.target.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>{tr("Название модели")}</span>
                      <input
                        value={settings.model}
                        onChange={(e) =>
                          setSettings({ ...settings, model: e.target.value })
                        }
                      />
                    </label>
                    <button
                      className="primary"
                      onClick={() =>
                        run(async () => {
                          await api("/settings/llm", "PUT", settings);
                          setToast("Настройки сохранены");
                          setDiagnostics(await api("/diagnostics"));
                        })
                      }
                    >{tr("Сохранить")}</button>
                    <SmallModelSettings api={api} settings={settings} onSettings={setSettings}/>
                    <p className="muted">{tr("Основные функции не зависят от ИИ. При обращении к модели передаются данные сотрудников и расписания на указанный сервер.")}</p>
                  </section>
                  <section className="panel">
                    <h3>{tr("Диагностика")}</h3>
                    {boot.demo_enabled && <details>
                      <summary>{tr("24 демонстрационных конфликта")}</summary>
                      <p className="muted">{tr("Каждый сценарий рассчитывается ядром в изолированной транзакции. Рабочая база не меняется.")}</p>
                      <div className="resource-tags">
                        {scenarios.map((c) => (
                          <button
                            key={c.id}
                            disabled={busy}
                            onClick={() =>
                              run(async () =>
                                setPreview(
                                  await api("/demo/scenarios/" + c.id, "POST"),
                                ),
                              )
                            }
                          >
                            {ru(c.name)}
                          </button>
                        ))}
                      </div>
                    </details>
                    }
                    {tr(diagnostics &&
                      Object.entries(diagnostics).map(([k, v]) => (
                        <div className="personline" key={k}>
                          <span>{tr(ru(k))}</span>
                          <small>{tr(ru(v))}</small>
                        </div>
                      )))}
                    <button
                      onClick={() =>
                        run(async () =>
                          setDiagnostics(await api("/diagnostics")),
                        )
                      }
                    >{tr("Повторить проверку")}</button>
                  </section>
                </div>
              </>
            )}
          </div>
        )}
      </main>
      {preview && (
        <div className="overlay" onClick={() => setPreview(null)}>
          <section
            className="modal preview-modal"
            role="dialog"
            aria-label={tr("Предварительный план")}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <div className="eyebrow">{tr("ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР · НЕ СОХРАНЕНО")}</div>
                <h2>{preview.title}</h2>
                <p>
                  {tr(date(preview.start))}{tr(" · ")}{tr(time(preview.start))}{tr(" ·")}{tr(" ")}
                  {tr(preview.venue)}{tr(" · Состав")}{tr(" ")}
                  {tr(preview.request.cast === "A" ? "А" : "Б")}
                </p>
              </div>
              <button
                className="icon"
                aria-label={tr("Закрыть Предварительный план")}
                onClick={() => setPreview(null)}
              >
                <X />
              </button>
            </div>
            <div className="modal-body">
              {preview.demo_scenario && (
                <p className="notice">{tr("Демонстрационный сценарий: ")}{ru(preview.demo_scenario.name)}{tr(". Изменения изолированы и не сохраняются.")}</p>
              )}
              {tr(planContent(preview))}
              {!canApprove && preview.conflicts.some((c:Obj) => ["ERROR", "CRITICAL"].includes(c.severity)) && <p className="notice">{tr("Серьёзные конфликты требуют согласования администратора или художественного руководителя. Отправьте план на согласование.")}</p>}
              {tr(!preview.demo_scenario && canApprove && (
                <label className="row">
                  <input
                    type="checkbox"
                    checked={!!preview.request.force}
                    disabled={busy}
                    onChange={(e) =>
                      changePlan(preview, { force: e.target.checked })
                    }
                  />{tr("Назначить принудительно с сохранением конфликтов")}</label>
              ))}
              {tr(canApprove && (preview.status === "CONFLICT" || preview.request.force) && (
                <label className="field">
                  <span>{tr("Обоснование решения администратора или художественного руководителя")}</span>
                  <textarea
                    value={override}
                    onChange={(e) => setOverride(e.target.value)}
                    placeholder={tr("Обязательная причина, не менее 12 символов")}
                  />
                </label>
              ))}
            </div>
            <div className="modal-footer">
              {tr(preview.demo_scenario ? (
                <button onClick={() => setPreview(null)}>{tr("Закрыть проверку")}</button>
              ) : (
                <>
                  <button onClick={() => startEdit(preview.request)}>{tr("Изменить")}</button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const r = await api(
                          "/substitutions",
                          "POST",
                          preview.request,
                        );
                        if (r.plan) {
                          setPreview(r.plan);
                          setToast("Предложены квалифицированные замены");
                        } else
                          setError(
                            "Полный состав замен не найден: " + r.status,
                          );
                      })
                    }
                  >{tr("Найти замены")}</button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const r = await api(
                          "/equipment-substitutions",
                          "POST",
                          preview.request,
                        );
                        if (r.plan) setPreview(r.plan);
                        else setError("Подходящие комплекты не найдены");
                      })
                    }
                  >{tr("Замены техники")}</button>
                  <button disabled={busy || !canEdit} onClick={() => save(true)}>{tr("На согласование")}</button>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      !canEdit ||
                      (!canApprove && preview.conflicts.some((c:Obj) => ["ERROR", "CRITICAL"].includes(c.severity))) ||
                      (!preview.request.force &&
                        preview.conflicts.some(
                          (c: Obj) => c.severity === "CRITICAL",
                        )) ||
                      ((preview.status === "CONFLICT" ||
                        preview.request.force) &&
                        override.trim().length < 12)
                    }
                    onClick={() => save()}
                  >{tr("Подтвердить")}</button>
                </>
              ))}
            </div>
          </section>
        </div>
      )}
      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <section
            className="modal detail-modal"
            role="dialog"
            aria-label={tr("Карточка события")}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <div className="eyebrow">
                  {tr(ru(detail.kind))}{tr(" · ")}{tr(ru(detail.status))}
                </div>
                <h2>{detail.title}</h2>
                <p>
                  {tr(date(detail.start))}{tr(" · ")}{tr(time(detail.start))}{tr("–")}{tr(time(detail.end))}{tr(" ")}{tr("· ")}{tr(detail.current.venue)}
                </p>
              </div>
              <button className="icon" onClick={() => setDetail(null)}>
                <X />
              </button>
            </div>
            <div className="modal-body">
              {tr(detail.current.passport_changed && <p className="notice">{tr("Паспорт постановки изменён. Здесь показаны сохранённые назначения. Для применения нового паспорта нажмите «Изменить» и проверьте новый план.")}</p>)}
              {tr(planContent(detail.current))}
              <details>
                <summary>{tr("Факт работ")}</summary>
                {detail.tasks.map((t: Obj) => (
                  <form
                    className="actual-row"
                    key={t.id}
                    onSubmit={(e) => {
                      e.preventDefault();
                      const fd = new FormData(e.currentTarget);
                      run(async () => {
                        await api("/tasks/" + t.id + "/actual", "PATCH", {
                          start: fd.get("start"),
                          end: fd.get("end"),
                        });
                        setToast("Факт сохранён");
                      });
                    }}
                  >
                    <label>{ru(t.name)}</label>
                    <input
                      type="datetime-local"
                      name="start"
                      defaultValue={t.actual_start || t.start}
                    />
                    <input
                      type="datetime-local"
                      name="end"
                      defaultValue={t.actual_end || t.end}
                    />
                    <button>{tr("Сохранить")}</button>
                  </form>
                ))}
              </details>
              <details>
                <summary>{tr("История изменений")}</summary>
                {tr(detail.history.map((h: Obj) => (
                  <p key={h.id}>
                    {tr(date(h.created))} {tr(time(h.created))}{tr(" · ")}{tr(ru(h.action))}{tr(" ")}
                    {tr(ru(h.data.reason))}
                  </p>
                )))}
              </details>
            </div>
            <div className="modal-footer">
              {tr(["Approved", "In Preparation", "Ready", "In Progress"].includes(
                detail.status,
              ) && (
                <button
                  onClick={() =>
                    run(async () => {
                      const flow = [
                        "Approved",
                        "In Preparation",
                        "Ready",
                        "In Progress",
                        "Completed",
                      ];
                      await api("/events/" + detail.id + "/status", "POST", {
                        status: flow[flow.indexOf(detail.status) + 1],
                        version: detail.version,
                      });
                      setDetail(await api("/events/" + detail.id));
                      setRevision((x) => x + 1);
                    })
                  }
                >{tr("Следующий этап")}</button>
              ))}
              <button
                onClick={() => {
                  const req = detail.current.request;
                  setDetail(null);
                  analyze(req);
                }}
              >{tr("Изменить")}</button>
              <button
                onClick={() => {
                  setSlots([detail]);
                  setCalDate(detail.start.slice(0, 10));
                  setDetail(null);
                  setView("production");
                  go("Календарь");
                }}
              >{tr("Производство")}</button>
              <button
                onClick={() =>
                  run(async () => {
                    await api("/events/" + detail.id + "/status", "POST", {
                      status: "Cancelled",
                      version: detail.version,
                      reason: "Отменено пользователем",
                    });
                    setDetail(null);
                    setRevision((x) => x + 1);
                  })
                }
              >{tr("Отменить событие")}</button>
            </div>
          </section>
        </div>
      )}
      {tr(showExport && <ScheduleExport date={calDate} filters={filter} locale={language} onClose={()=>setShowExport(false)}/>)}
      {showQualifications && <QualificationManager api={api} onClose={()=>{setShowQualifications(false);load();}}/>}
      {resourceEditor && (
        <div className="overlay" onClick={() => setResourceEditor(null)}>
          <section
            className="modal"
            role="dialog" aria-modal="true" aria-label={tr("Редактор ресурса")}
            style={{ maxWidth: 540 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2>
                {tr(resourceEditor.id ? "Редактировать ресурс" : "Новый ресурс")}
              </h2>
              <button className="icon" onClick={() => setResourceEditor(null)}>
                <X />
              </button>
            </div>
            <form
              className="modal-body"
              onSubmit={(e) => {
                e.preventDefault();
                run(async () => {
                  const r = resourceEditor;
                  const department=departments.find(d=>ru(d)===r.department) || r.department;
                  const data = {
                    ...(r.data || {}),
                    ...(["Room","Vehicle"].includes(r.kind) ? {capacity:r.data?.capacity === "" ? 0 : (r.data?.capacity ?? 0)} : {}),
                    specialization: r.specialization || department,
                    qualification: [...new Set([...(r.data?.qualification || []), department, r.specialization || department])],
                  };
                  const result = await api(
                    "/resources" + (r.id ? "/" + r.id : ""),
                    r.id ? "PATCH" : "POST",
                    {
                      kind: r.kind,
                      name: r.name,
                      department,
                      data,
                    },
                  );
                  setResourceEditor(null);
                  if (r.id) setSelected(result.resource);
                  await load();
                  setToast("Ресурс сохранён");
                });
              }}
            >
              <label className="field">
                <span>{tr("Название / ФИО")}</span>
                <input
                  required
                  value={resourceEditor.name}
                  onChange={(e) =>
                    setResourceEditor({
                      ...resourceEditor,
                      name: e.target.value,
                    })
                  }
                />
              </label>
              {tr(!resourceEditor.id &&
                picker(
                  "Тип ресурса",
                  "kind",
                  [
                    { id: "Person", name: "Сотрудник" },
                    { id: "Equipment", name: "Оборудование" },
                    { id: "Prop", name: "Реквизит" },
                    { id: "Costume", name: "Костюм" },
                    { id: "Vehicle", name: "Транспорт" },
                    { id: "Room", name: "Репетиционное помещение" },
                    { id: "Equipment Kit", name: "Комплект оборудования" },
                  ],
                  resourceEditor.kind,
                  (v) => setResourceEditor({ ...resourceEditor, kind: v }),
                ))}
              <label className="field">
                <span>{tr("Подразделение")}</span>
                <input
                  list="staff-departments"
                  required
                  value={resourceEditor.department}
                  onChange={(e) =>
                    setResourceEditor({
                      ...resourceEditor,
                      department: e.target.value,
                    })
                  }
                />
              </label>
              <datalist id="staff-departments">{tr(departments.map(d => <option key={d} value={d}/>))}</datalist>
              <label className="field">
                <span>{tr("Специализация / инструмент")}</span>
                <input
                  value={resourceEditor.specialization || ""}
                  onChange={(e) =>
                    setResourceEditor({
                      ...resourceEditor,
                      specialization: e.target.value,
                    })
                  }
                />
              </label>
              {resourceEditor.kind === "Person" && <fieldset className="qualification-picker">
                <legend>{tr("Квалификации сотрудника")}</legend><button type="button" onClick={()=>setShowQualifications(true)}>{tr("Управление квалификациями")}</button>
                <p className="muted">{tr("Выберите только подтверждённые квалификации. Они определяют доступные назначения.")}</p>
                {[...new Set([...(boot?.qualifications || []), ...(resourceEditor.data?.qualification || [])])].map(q => (
                  <label key={q}><input type="checkbox" aria-label={tr("Квалификация") + " " + tr(ru(q))}
                    checked={q === resourceEditor.department || (resourceEditor.data?.qualification || []).includes(q)}
                    disabled={q === resourceEditor.department}
                    onChange={e => setResourceEditor({...resourceEditor,data:{...resourceEditor.data,qualification:e.target.checked ? [...new Set([...(resourceEditor.data?.qualification || []),q])] : (resourceEditor.data?.qualification || []).filter((x:string)=>x!==q)}})}
                  />{tr(ru(q))}</label>
                ))}
              </fieldset>}
              {resourceEditor.kind === "Room" && <label className="field"><span>{tr("Площадка помещения")}</span><select required value={resourceEditor.data?.venue_id || 0} onChange={e => setResourceEditor({...resourceEditor,data:{...resourceEditor.data,venue_id:+e.target.value}})}><option value="0">{tr("Выберите площадку")}</option>{resources.filter(r=>r.kind==="Venue").map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
              {tr(["Room","Vehicle"].includes(resourceEditor.kind) && <label className="field"><span>{tr("Вместимость")}</span><input type="number" min={0} value={resourceEditor.data?.capacity ?? ""} onChange={e=>setResourceEditor({...resourceEditor,data:{...resourceEditor.data,capacity:e.target.value === "" ? "" : +e.target.value}})}/></label>)}
              {resourceEditor.kind === "Equipment Kit" && <label className="field"><span>{tr("Имущество комплекта")}</span><select multiple size={6} value={(resourceEditor.data?.items || []).map(String)} onChange={e=>setResourceEditor({...resourceEditor,data:{...resourceEditor.data,items:Array.from(e.target.selectedOptions).map(o=>+o.value)}})}>{resources.filter(r=>r.kind==="Equipment").map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
              {tr(resourceEditor.kind === "Equipment" && (
                <label className="field">
                  <span>{tr("Категория оборудования")}</span>
                  <input
                    list="equipment-categories"
                    value={resourceEditor.data?.category || ""}
                    onChange={(e) =>
                      setResourceEditor({
                        ...resourceEditor,
                        data: {
                          ...resourceEditor.data,
                          category: e.target.value,
                        },
                      })
                    }
                  />
                  <datalist id="equipment-categories">
                    {tr([
                      "Микрофоны",
                      "Консоли",
                      "Мониторы",
                      "BSW",
                      "Wash",
                      "LED Bar",
                      "Дымка",
                      "Дым",
                      "Стейджбоксы",
                      "Проекторы",
                      "Медиасерверы",
                    ].map((c) => (
                      <option key={c} value={c} />
                    )))}
                  </datalist>
                </label>
              ))}
              <button className="primary" type="submit">{tr("Сохранить ресурс")}</button>
            </form>
          </section>
        </div>
      )}
      {palette && (
        <div className="overlay" onClick={() => setPalette(false)}>
          <section className="palette" onClick={(e) => e.stopPropagation()}>
            <div className="row">
              <Search />
              <input
                autoFocus
                placeholder={tr("Команда, сотрудник, постановка…")}
                value={find}
                onChange={(e) => setFind(e.target.value)}
              />
              <kbd>{tr("Esc")}</kbd>
            </div>
            <div className="palette-results">
              {[
                ...nav.map(([name]) => ({ name, kind: "page" })),
                ...productions.map((p) => ({ ...p, kind: "production" })),
                ...resources.filter((r) =>
                  ["Person", "Venue", "Equipment Kit"].includes(r.kind),
                ),
              ]
                .filter((r: Obj) =>
                  r.name.toLowerCase().includes(find.toLowerCase()),
                )
                .slice(0, 20)
                .map((r: Obj, i: number) => (
                  <button
                    key={i}
                    onClick={() => {
                      setPalette(false);
                      if (r.kind === "page") go(r.name);
                      else if (r.kind === "production") {
                        go("Постановки");
                        setSelected(r);
                      } else personal(r);
                    }}
                  >
                    <Command size={16} />
                    {r.name}
                    <ArrowRight size={14} />
                  </button>
                ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
const personalMobile = location.pathname.startsWith("/mobile") || (!sessionStorage.getItem("stageos-token") && (window.matchMedia("(max-width: 760px)").matches || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)));
createRoot(document.getElementById("root")!).render(personalMobile ? <MobileApp/> : <AccountGate>{(account,exit)=><App key={account?.theatre.id+":"+account?.user.id} account={account} exit={exit}/>}</AccountGate>);
