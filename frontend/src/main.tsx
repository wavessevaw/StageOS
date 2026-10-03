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
import PassportEditor from "./PassportEditor";
import VenueEditor from "./VenueEditor";
import { ru } from "./ru";
type Obj = Record<string, any>;
const initialToken = new URLSearchParams(location.search).get("token");
if (initialToken) {
  sessionStorage.setItem("stageos-token", initialToken);
  history.replaceState({}, "", location.pathname);
}
async function api(path: string, method = "GET", body?: any) {
  const res = await fetch("/api" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-StageOS-Token": sessionStorage.getItem("stageos-token") || "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
  new Date(s).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" });
const date = (s: string) =>
  new Date(s).toLocaleDateString("ru", { day: "numeric", month: "long" });
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
      {value === "READY"
        ? "✓ "
        : value === "CONFLICT"
          ? "× "
          : value === "WARNING"
            ? "⚠ "
            : ""}
      {statusLabels[value] || ru(value)}
    </span>
  );
}
function shiftedStart(req: Obj, start: string): Obj {
  const delta = +new Date(start) - +new Date(req.start);
  const edits = Object.fromEntries(Object.entries(req.task_overrides || {}).map(([name, raw]) => {
    const edit = raw as Obj;
    return [name, {...edit, ...(edit.start && Number.isFinite(delta) ? {start:local(new Date(+new Date(edit.start)+delta))} : {})}];
  }));
  return {...req,start,task_overrides:edits};
}
const today = local(new Date()).slice(0,10);
function App() {
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
      start: today + "T19:00:00",
      duration: 120,
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
  }
  const cal = useRef<FullCalendar>(null);
  const resources: Obj[] = boot?.resources || [],
    productions: Obj[] = boot?.productions || [];
  const resource = (id: number) => resources.find((r) => r.id === id);
  const prod = productions.find((p) => p.id === form.production_id);
  const departments = [
    ...new Set([...(boot?.departments || []),
      ...resources.filter((r) => r.kind === "Person").map((r) => r.department)]),
  ];
  async function load() {
    try {
      const b = await api("/bootstrap");
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
      setBusy(true);
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
          if (!cancelled) setBusy(false);
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
  function go(p: string) {
    setPage(p);
    setVenueEditor(null);
    setSelected(null);
    setFind("");
    setCatalogDept("");
    setCatalogCategory("");
    if (p === "Добавить спектакль") newPassport();
  }
  function update(k: string, v: any) {
    setForm((f) => k === "start" ? shiftedStart(f, v) : ({ ...f, [k]: v, ...(k === "kind" ? { task_overrides:{}, run_through:false, rehearsal_people:null, rehearsal_items:[] } : {}) }));
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
      const res = await fetch("/api/database/import", {
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
      const res = await fetch("/api/database/export", {
        headers: {
          "X-StageOS-Token": sessionStorage.getItem("stageos-token") || "",
        },
      });
      if (!res.ok) throw new Error("Не удалось создать резервную копию");
      const url = URL.createObjectURL(await res.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "StageOS-backup.db";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
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
      const req = { ...preview.request, override_reason: override };
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
      setForm((f) => ({
        ...f,
        event_id: undefined,
        version: undefined,
        replacements: {},
      }));
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
    go("Назначить");
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
        <span>{ru(label)}</span>
        <select
          aria-label={label}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          {opts.map((o) => (
            <option key={o.id} value={o.id}>
              {ru(o.name)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function conflicts(p: Obj) {
    return (
      <div className="conflicts">
        {p.conflicts.length === 0 ? (
          <div className="empty success">
            <Check size={22} />
            Пересечений и технических ограничений не найдено
          </div>
        ) : (
          p.conflicts.map((c: Obj, i: number) => (
            <details className={"conflict " + c.severity.toLowerCase()} key={i}>
              <summary>
                <AlertTriangle size={15} />
                <b>{ru(c.resource)}</b>
                <span>{ru(c.reason)}</span>
                <Badge value={c.severity} />
              </summary>
              <div>
                {c.current_event && (
                  <p>
                    Занят: {c.current_event} · {c.venue}
                  </p>
                )}
                {c.busy && (
                  <p>
                    {date(c.busy[0])} {time(c.busy[0])}–{time(c.busy[1])} ·
                    требуется {time(c.required[0])}–{time(c.required[1])}
                  </p>
                )}
                {c.overlap && (
                  <p>
                    Пересечение: {time(c.overlap[0])}–{time(c.overlap[1])}
                  </p>
                )}
                <p>{ru(c.solutions.join(" · "))}</p>
              </div>
            </details>
          ))
        )}
      </div>
    );
  }
  function timeline(tasks: Obj[]) {
    if (!tasks.length) return <p>Нет задач</p>;
    const min = Math.min(...tasks.map((t) => +new Date(t.start))),
      max = Math.max(...tasks.map((t) => +new Date(t.end)));
    return (
      <div className="timeline">
        <div className="timeline-axis">
          <span>{time(new Date(min).toISOString())}</span>
          <span>{time(new Date((max + min) / 2).toISOString())}</span>
          <span>{time(new Date(max).toISOString())}</span>
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
                title={`${time(t.start)}–${time(t.end)}`}
              />
            </div>
            <small>
              {time(t.start)}–{time(t.end)}
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
            <small>СОСТОЯНИЕ</small>
            <Badge value={p.status} />
          </div>
          <div>
            <small>УЧАСТНИКОВ</small>
            <b>{p.assignments.length}</b>
          </div>
          <div>
            <small>ПОДГОТОВКА С</small>
            <b>{time(p.tasks[0].start)}</b>
          </div>
          <div>
            <small>КОНФИГУРАЦИЯ</small>
            <b>{ru(p.compatibility.version)}</b>
          </div>
        </div>
        {p === preview && !p.demo_scenario ? (
          <label className="field">
            <span>Примечание к событию</span>
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
              <h3>Примечание</h3>
              {p.notes}
            </section>
          )
        )}
        {p.request.force && (
          <p className="notice">
            Принудительное назначение. Конфликты сохранены и требуют решения.
          </p>
        )}
        <h3>Ответственные и состав</h3>
        <div className="accordion-grid">
          {[...new Set(p.assignments.map((a: Obj) => a.department))].map(
            (dep: any) => (
              <details key={dep}>
                <summary>
                  {ru(dep)}
                  <span>
                    {
                      p.assignments.filter((a: Obj) => a.department === dep)
                        .length
                    }
                  </span>
                </summary>
                {p.assignments
                  .filter((a: Obj) => a.department === dep)
                  .map((a: Obj, i: number) => (
                    <div className="personline" key={i}>
                      <span>
                        <b>{ru(a.actual)}</b>
                        <small>
                          {ru(a.role)}
                          {a.responsible_id !== a.actual_id &&
                            " · ответственный: " + a.responsible}
                        </small>
                      </span>
                      <time>{time(a.call)}</time>
                      {p === preview && !p.demo_scenario && (
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
                                {ru(r.name)}
                                {r.id === a.responsible_id ? " · основной" : ""}
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
        <h3>Техническая совместимость</h3>
        <div className="check-grid">
          {p.compatibility.checks.map((c: Obj) => (
            <div key={c.name} className={c.ok ? "ok" : "bad"}>
              <span>
                {c.ok ? "✓" : "×"} {ru(c.name)}
              </span>
              <small>
                {c.required} / {c.available}
              </small>
            </div>
          ))}
        </div>
        {p.compatibility.override && (
          <p className="notice">{p.compatibility.override.note}</p>
        )}
        <details>
          <summary>
            Техника и резервирования <span>{p.bookings.length}</span>
          </summary>
          <div className="resource-tags">
            {p.bookings
              .filter((b: Obj) => b.kind !== "Person")
              .map((b: Obj) => (
                <span key={b.resource_id}>
                  {ru(b.name)} · {time(b.start)}–{time(b.end)}
                </span>
              ))}
          </div>
        </details>
        <h3>Производственный план</h3>
        {p === preview && !p.demo_scenario && (
          <>
            {p.request.kind !== "Репетиция" && (
              <label className="row">
                <input
                  type="checkbox"
                  checked={!!p.request.run_through}
                  disabled={busy}
                  onChange={(e) =>
                    changePlan(p, {
                      run_through: e.target.checked,
                      task_overrides: {},
                    })
                  }
                />
                Прогон в день спектакля: 11:00–14:00, обед, вечерний сбор
              </label>
            )}
            <p className="muted">
              Измените начало или длительность этапа: зависимости и занятость
              пересчитываются. Время спектакля остаётся фиксированным. Явно
              заданные времена отмечены как закреплённые.
            </p>
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
                      if (
                        e.target.value &&
                        e.target.value !== t.start.slice(0, 16)
                      ) {
                        if (["Спектакль", "Репетиция"].includes(t.name))
                          changePlan(p, { start: e.target.value });
                        else
                          changePlan(p, {
                            task_overrides: {
                              ...p.request.task_overrides,
                              [t.name]: {
                                ...p.request.task_overrides?.[t.name],
                                start: e.target.value,
                              },
                            },
                          });
                      }
                    }}
                  />
                  <input
                    aria-label={"Длительность " + t.name}
                    type="number"
                    min="1"
                    max="1440"
                    defaultValue={Math.round(
                      (+new Date(t.end) - +new Date(t.start)) / 60000,
                    )}
                    disabled={busy || t.name === "Спектакль"}
                    onBlur={(e) => {
                      const n = +e.target.value;
                      if (
                        n > 0 &&
                        n !==
                          Math.round(
                            (+new Date(t.end) - +new Date(t.start)) / 60000,
                          )
                      ) {
                        if (t.name === "Репетиция")
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
                  <small>до {time(t.end)}</small>
                  {p.request.task_overrides?.[t.name] && (
                    <button
                      onClick={() => {
                        const o = { ...p.request.task_overrides };
                        delete o[t.name];
                        changePlan(p, { task_overrides: o });
                      }}
                    >
                      Снять закрепление
                    </button>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
        {timeline(p.tasks)}
        <h3>Конфликты и предупреждения · {p.conflicts.length}</h3>
        {conflicts(p)}
        <p className="muted">
          Решатель: {ru(p.solver.status)} · Штраф мягких ограничений:{" "}
          {p.penalty} · Предварительный план не изменяет расписание
        </p>
      </>
    );
  }
  if (!boot)
    return (
      <div className="loading">
        <Layers />
        <h2>StageOS</h2>
        <p>{error || "Подключение к локальному ядру…"}</p>
        <button onClick={load}>Повторить</button>
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
            <Layers size={24} />
          </div>
          <span>
            Stage<span className="thin">OS</span>
            <small>ТЕАТРАЛЬНОЕ ПРОИЗВОДСТВО</small>
          </span>
        </div>
        <div className="theatre">
          <span className="avatar">Т</span>
          <div>
            {boot?.theatre_name || (boot?.demo_enabled ? "Демо театр" : "Рабочий театр")}<small>Локальное пространство</small>
          </div>
          <span className="online" />
        </div>
        <nav>
          {nav.map(([name, Icon], i) => (
            <button
              key={name}
              className={
                (page === name ? "active " : "") + (i === 8 ? "nav-gap" : "")
              }
              onClick={() => go(name)}
            >
              <Icon size={18} />
              {ru(name)}
              {name === "Назначить" && <small>⌘ N</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="online" />
          Локальная база данных<small>StageOS · 1.0.0-rc.1</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <span className="muted">Рабочее пространство</span>
            <ChevronRight size={14} />
            <b>{ru(page)}</b>
          </div>
          <button className="search-btn" onClick={() => setPalette(true)}>
            <Search size={15} />
            Быстрый поиск<kbd>Ctrl K</kbd>
          </button>
          <button
            className="icon"
            aria-label="Уведомления"
            onClick={() => go("Уведомления")}
          >
            <Bell size={19} />
          </button>
          <span className="avatar">АД</span>
        </header>
        {error && (
          <div role="alert" className="error-banner">
            {error}
            <button className="icon" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {toast && (
          <div className="toast">
            <Check size={17} />
            {toast}
          </div>
        )}
        {!boot.initialized && page !== "Настройки" ? (
          <section className="welcome">
            <div className="eyebrow">ТЕАТР. ЛЮДИ. ТЕХНОЛОГИИ.</div>
            <h1>
              Добро пожаловать
              <br />в StageOS.
            </h1>
            <p>
              Всё, что нужно, чтобы поднять занавес.
              <br />
              Люди, площадки и производство — в одном расписании.
            </p>
            {!boot.demo_enabled && <label className="field"><span>Название театра</span><input maxLength={200} value={theatreName} onChange={e=>setTheatreName(e.target.value)} /></label>}
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
              {busy ? "Создаём театр…" : boot.demo_enabled ? "Создать демонстрационный театр" : "Создать рабочую базу"}
              <ArrowRight size={18} />
            </button>
            <div className="row">
              <button
                onClick={() =>
                  document.getElementById("database-upload")?.click()
                }
              >
                Открыть существующую базу
              </button>
              <button onClick={() => go("Настройки")}>
                Настроить локального помощника
              </button>
            </div>
            <p className="muted">
              Данные хранятся на этом компьютере. Основные функции работают без
              интернета и без ИИ.
            </p>
          </section>
        ) : (
          <div className="content">
            {page === "Назначить" && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">ПЛАНИРОВАНИЕ БЕЗ ЛИШНИХ ШАГОВ</div>
                    <h1>
                      {form.event_id ? "Изменить событие" : "Поднимем занавес."}
                    </h1>
                    <p>
                      Выберите главное. StageOS проверит людей, технику и
                      площадку.
                    </p>
                  </div>
                  <span className="pill">
                    <span className="online" />
                    Производственный движок
                  </span>
                </div>
                {(!productions.length || !resources.some(r => r.kind === "Venue")) && <p className="notice">Для назначения создайте площадку и постановку. Сотрудников добавьте в разделе «Сотрудники», затем выберите их в паспорте постановки.</p>}
                <div className="assign-card">
                  <div className="segmented">
                    {["Спектакль", "Репетиция"].map((k) => (
                      <button
                        className={form.kind === k ? "chosen" : ""}
                        key={k}
                        onClick={() => update("kind", k)}
                      >
                        {k === "Спектакль" ? (
                          <Clapperboard size={16} />
                        ) : (
                          <Users size={16} />
                        )}{" "}
                        {ru(k)}
                      </button>
                    ))}
                  </div>
                  <div className="assign-form">
                    <label className="field">
                      <span>Дата</span>
                      <input
                        aria-label="Дата"
                        type="date"
                        value={form.start.slice(0, 10)}
                        onChange={(e) =>
                          update("start", e.target.value + form.start.slice(10))
                        }
                      />
                    </label>
                    {picker(
                      "Постановка",
                      "production_id",
                      productions,
                      form.production_id,
                      (v) => {
                        setForm((f) => ({
                          ...f,
                          production_id: +v,
                          replacements: {},
                          scenes: [],
                          task_overrides: {},
                          rehearsal_people: null,
                          rehearsal_items: [],
                        }));
                      },
                    )}
                    {picker(
                      "Состав",
                      "cast",
                      [
                        { id: "A", name: "Состав А · первый" },
                        { id: "B", name: "Состав Б · второй" },
                      ],
                      form.cast,
                      (v) => update("cast", v),
                    )}
                    {picker(
                      "Площадка",
                      "venue_id",
                      resources.filter(
                        (r) =>
                          r.kind === "Venue" ||
                          (form.kind === "Репетиция" && r.kind === "Room"),
                      ),
                      form.venue_id,
                      (v) => update("venue_id", +v),
                    )}
                    <label className="field">
                      <span>Начало</span>
                      <input
                        type="time"
                        aria-label="Начало"
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
                  {form.kind === "Репетиция" && (
                    <div className="row rehearsal">
                      <label>
                        Длительность, мин{" "}
                        <input
                          type="number"
                          min="15"
                          max="480"
                          value={form.duration}
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
                          {ru(s.name)}
                        </label>
                      ))}
                    </div>
                  )}
                  {form.kind !== "Репетиция" && (
                    <label className="row">
                      <input
                        type="checkbox"
                        checked={!!form.run_through}
                        onChange={(e) =>
                          update("run_through", e.target.checked)
                        }
                      />
                      Прогон на площадке в день спектакля (начало в 11:00)
                    </label>
                  )}
                  <label className="field">
                    <span>Примечание к событию</span>
                    <textarea
                      maxLength={8000}
                      value={form.notes || ""}
                      onChange={(e) => update("notes", e.target.value)}
                      placeholder="Пометки для помрежа и служб"
                    />
                  </label>
                  <div className="assign-footer">
                    <label>
                      <input
                        type="checkbox"
                        checked={form.adaptation}
                        onChange={(e) => update("adaptation", e.target.checked)}
                      />{" "}
                      Использовать согласованную адаптацию площадки
                    </label>
                    <button
                      className="primary"
                      disabled={busy || !live || !form.production_id || !form.venue_id}
                      onClick={() => analyze()}
                    >
                      Проверить и назначить <ArrowRight size={17} />
                    </button>
                  </div>
                </div>
                <div className="section-title">
                  <h3>Всё под контролем</h3>
                  <span className="muted">
                    {live
                      ? "Проверено по локальной базе"
                      : "Проверяем доступность…"}
                  </span>
                </div>
                <div className="validation-grid">
                  {[
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
                        <span>{ru(d)}</span>
                        <span>
                          {st === "wait"
                            ? "…"
                            : st === "ok"
                              ? "✓"
                              : st === "warn"
                                ? "⚠"
                                : "×"}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {form.kind === "Репетиция" && (
                  <section className="panel">
                    <h3>Кто нужен на репетиции</h3>
                    <p>
                      Выберите цех и конкретных людей. В расписание попадут
                      только выбранные участники.
                    </p>
                    <div className="toolbar">
                      {departments.map((d) => (
                        <button
                          key={d}
                          className={d === rehearsalDept ? "primary" : ""}
                          onClick={() => {
                            setRehearsalDept(d);
                            if (form.rehearsal_people == null)
                              update("rehearsal_people", []);
                          }}
                        >
                          {ru(d)}
                        </button>
                      ))}
                    </div>
                    <div className="row">
                      <button onClick={() => update("rehearsal_people", null)}>
                        Состав постановки автоматически
                      </button>
                      <button onClick={() => update("rehearsal_people", [])}>
                        Очистить выбор
                      </button>
                      <b>
                        Выбрано:{" "}
                        {
                          (
                            form.rehearsal_people ??
                            live?.assignments.map((a: Obj) => a.actual_id) ??
                            []
                          ).length
                        }
                      </b>
                    </div>
                    {rehearsalDept && (
                      <div className="resource-grid">
                        {resources
                          .filter(
                            (r) =>
                              r.kind === "Person" &&
                              r.department === rehearsalDept,
                          )
                          .map((r) => (
                            <label className="personline" key={r.id}>
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
                              {ru(r.name)}
                              <small>{ru(r.data.specialization)}</small>
                            </label>
                          ))}
                      </div>
                    )}
                  </section>
                )}
                <div className="two-col">
                  <section className="panel">
                    <div className="section-title">
                      <h3>Производственная версия</h3>
                      {live && <Badge value={live.status} />}
                    </div>
                    <h2>{ru(prod?.name)}</h2>
                    <p className="muted">
                      {prod?.data.genre} · {prod?.data.duration} мин · версия{" "}
                      {ru(prod?.version)}
                    </p>
                    <div className="stats">
                      <div>
                        <b>{live?.assignments.length || "—"}</b>
                        <span>участников</span>
                      </div>
                      <div>
                        <b>{live ? time(live.tasks[0].start) : "—"}</b>
                        <span>начало подготовки</span>
                      </div>
                      <div>
                        <b>{live?.conflicts.length ?? "—"}</b>
                        <span>замечаний</span>
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        go("Постановки");
                        setSelected(prod || null);
                      }}
                    >
                      Открыть постановку <MoveUpRight size={16} />
                    </button>
                  </section>
                  <section className="panel tinted">
                    <div className="eyebrow">ПЛАН БЕЗ РИСКА</div>
                    <h2>А если перенести?</h2>
                    <p>
                      Меняйте время, состав и площадку. Все варианты остаются
                      предварительными до подтверждения.
                    </p>
                    <div className="row">
                      <button onClick={() => analyze()}>
                        Изменить <ArrowRight size={16} />
                      </button>
                      {form.kind === "Репетиция" && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            run(async () =>
                              setWindows(await api("/windows", "POST", form)),
                            )
                          }
                        >
                          Найти 3 окна
                        </button>
                      )}
                    </div>
                    {windows.map((w) => (
                      <button key={w.start} onClick={() => setForm(w.request)}>
                        {date(w.start)} · {time(w.start)}
                      </button>
                    ))}
                  </section>
                </div>
                {live && live.conflicts.length > 0 && (
                  <section className="panel">
                    <h3>Что требует внимания</h3>
                    {conflicts(live)}
                  </section>
                )}
              </>
            )}
            {page === "Календарь" && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">
                      ЛЮДИ И ПРОИЗВОДСТВО В ОДНОМ РИТМЕ
                    </div>
                    <h1>Календарь</h1>
                  </div>
                  <button
                    className="primary"
                    onClick={() => {
                      setForm((f) => ({
                        ...f,
                        event_id: undefined,
                        version: undefined,
                      }));
                      go("Назначить");
                    }}
                  >
                    <Plus size={17} />
                    Создать событие
                  </button>
                </div>
                <div className="calendar-tools">
                  <div className="segmented">
                    {[
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
                          else
                            run(async () =>
                              setSlots(
                                await Promise.all(
                                  events
                                    .filter(
                                      (e) => e.start.slice(0, 10) === calDate,
                                    )
                                    .map((e) => api("/events/" + e.id)),
                                ),
                              ),
                            );
                        }}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                  <label className="search-inline">
                    <Search size={16} />
                    <input
                      placeholder="Найти в расписании"
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
                    />
                    Подготовка и выезды
                  </label>
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
                      <option value="">{ru(label)}</option>
                      {opts.map((o: Obj) => (
                        <option key={o.id} value={o.id}>
                          {ru(o.name)}
                        </option>
                      ))}
                    </select>
                  ))}
                  <button onClick={() => setFilter({})}>Сброс</button>
                </div>
                <div className="calendar-panel">
                  {busy && (
                    <div className="cal-loading">Обновляем расписание…</div>
                  )}
                  {view === "production" ? (
                    <>
                      <div className="row">
                        <input
                          aria-label="Дата производства"
                          type="date"
                          value={calDate}
                          onChange={(e) => {
                            setCalDate(e.target.value);
                            run(async () =>
                              setSlots(
                                await Promise.all(
                                  events
                                    .filter(
                                      (x) =>
                                        x.start.slice(0, 10) === e.target.value,
                                    )
                                    .map((x) => api("/events/" + x.id)),
                                ),
                              ),
                            );
                          }}
                        />
                      </div>
                      {slots.length ? (
                        slots.map((e) => (
                          <section className="panel" key={e.id}>
                            <div className="section-title">
                              <h3>
                                {e.title} · {date(e.start)}
                              </h3>
                              <button onClick={() => openEvent(e.id)}>
                                Открыть
                              </button>
                            </div>
                            {timeline(e.tasks)}
                          </section>
                        ))
                      ) : (
                        <div className="empty">
                          Выберите дату с событиями, чтобы увидеть
                          производственную цепочку.
                        </div>
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
                      locale={ruLocale}
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
                        if (view === "timeGridDay")
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
                          durationEditable: e.kind === "Репетиция",
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
                          setForm((f) => ({
                            ...f,
                            start: local(arg.date),
                            event_id: undefined,
                            version: undefined,
                          }));
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
                <p className="muted">
                  Перенос и изменение длительности сначала открывают
                  Предварительный план. До подтверждения расписание не меняется.
                </p>
              </>
            )}
            {(page === "Добавить спектакль" ||
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
              )}
            {page === "Постановки" && !passport && (
              <>
                <div className="page-title">
                  <div>
                    <div className="eyebrow">
                      РЕПЕРТУАР И ПРОИЗВОДСТВЕННЫЕ ПАСПОРТА
                    </div>
                    <h1>{selected?.name || "Постановки"}</h1>
                  </div>
                  {selected && (
                    <button
                      onClick={() =>
                        setPassport(JSON.parse(JSON.stringify(selected)))
                      }
                    >
                      Редактировать постановку
                    </button>
                  )}
                  <button onClick={() => go("Добавить спектакль")}>
                    Добавить спектакль
                  </button>
                  {selected && (
                    <button onClick={() => setSelected(null)}>
                      Все постановки
                    </button>
                  )}
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
                          <span>СЦЕНА / {String(i + 1).padStart(2, "0")}</span>
                          <div className="poster-orbit" />
                          <b>{ru(p.name)}</b>
                        </div>
                        <div className="production-caption">
                          <span>{p.data.genre}</span>
                          <h3>{ru(p.name)}</h3>
                          <p>
                            {p.data.duration} мин{" "}
                            <span>
                              Подготовка {Math.floor(p.data.preparation / 60)}:
                              {String(p.data.preparation % 60).padStart(2, "0")}
                            </span>
                          </p>
                          <div>
                            <Badge value="Активна" />
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
                        <small>ВЕРСИЯ</small>
                        <b>{ru(selected.version)}</b>
                      </div>
                      <div>
                        <small>ПРОДОЛЖИТЕЛЬНОСТЬ</small>
                        <b>{selected.data.duration} мин</b>
                      </div>
                      <div>
                        <small>БАЗОВАЯ ПОДГОТОВКА</small>
                        <b>{selected.data.preparation} мин</b>
                      </div>
                      <div>
                        <small>ОСНОВНАЯ ПЛОЩАДКА</small>
                        <b>{ru(resource(selected.data.home_venue)?.name)}</b>
                      </div>
                    </div>
                    <div className="segmented big">
                      <button
                        className={tab === "Люди" ? "chosen" : ""}
                        onClick={() => setTab("Люди")}
                      >
                        <Users size={18} />
                        Люди
                      </button>
                      <button
                        className={tab === "Техника" ? "chosen" : ""}
                        onClick={() => setTab("Техника")}
                      >
                        <Boxes size={18} />
                        Техника
                      </button>
                    </div>
                    {tab === "Люди" ? (
                      <div className="accordion-grid">
                        <details open>
                          <summary>Артисты · составы A / B</summary>
                          {selected.data.roles.map((r: Obj) => (
                            <div className="cast-row" key={r.role}>
                              <b>{ru(r.role)}</b>
                              <span>A · {ru(resource(r.A)?.name)}</span>
                              <span>B · {ru(resource(r.B)?.name)}</span>
                              <small>
                                Резерв · {ru(resource(r.reserve)?.name)}
                              </small>
                            </div>
                          ))}
                        </details>
                        <details open>
                          <summary>Руководство и ответственные</summary>
                          {Object.entries(selected.data.responsibles).map(
                            ([d, id]: any) => (
                              <div className="personline" key={d}>
                                <span>{ru(d)}</span>
                                <b>{ru(resource(id)?.name)}</b>
                              </div>
                            ),
                          )}
                        </details>
                        {Object.entries(selected.data.groups).map(
                          ([d, ids]: any) => (
                            <details key={d}>
                              <summary>
                                {ru(d)}
                                <span>{ids.length}</span>
                              </summary>
                              {d === "Оркестр" &&
                                Object.entries(
                                  selected.data.orchestra_versions,
                                ).map(([v, arr]: any) => (
                                  <p key={v}>
                                    {ru(v)}: {arr.length} музыкантов
                                  </p>
                                ))}
                              {ids.map((id: number) => (
                                <div className="personline" key={id}>
                                  <span>{ru(resource(id)?.name)}</span>
                                  <small>
                                    {ru(resource(id)?.data.specialization)}
                                  </small>
                                </div>
                              ))}
                            </details>
                          ),
                        )}
                        {Object.entries(selected.data.crew).map(
                          ([d, ids]: any) => (
                            <details key={d + "crew"}>
                              <summary>
                                Техническая группа · {ru(d)}
                                <span>{ids.length}</span>
                              </summary>
                              {ids.map((id: number) => (
                                <div className="personline" key={id}>
                                  {ru(resource(id)?.name)}
                                  <small>
                                    Квалификация {resource(id)?.data.level}
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
                                  [
                                    "Декорации",
                                    "Реквизит и костюмы",
                                    "Звук · свет · видео",
                                  ][i]
                                }
                              </summary>
                              {selected.data[key].map((id: number) => {
                                let r = resource(id);
                                return (
                                  <div key={id} className="resource-line">
                                    <b>{ru(r?.name)}</b>
                                    {r?.kind === "Scenery" ? (
                                      <p>
                                        {r.data.width} × {r.data.depth} ×{" "}
                                        {r.data.height} м · {r.data.mass} кг ·{" "}
                                        {r.data.installation} · {r.data.crew}{" "}
                                        монтажника
                                      </p>
                                    ) : r?.kind === "Equipment Kit" ? (
                                      <p>
                                        {r.data.items
                                          .map((i: number) => resource(i)?.name)
                                          .join(" · ")}
                                      </p>
                                    ) : (
                                      <p>
                                        Критический · {r?.data.quantity} шт.
                                      </p>
                                    )}
                                  </div>
                                );
                              })}
                            </details>
                          ),
                        )}
                        <details open>
                          <summary>Механика и световая инфраструктура</summary>
                          {!!selected.data.items?.length && (
                            <div className="panel">
                              <h3>Поштучное имущество</h3>
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
                                  {ru(name)} — {String(count)} шт.
                                </p>
                              ))}
                            </div>
                          )}
                          {Object.entries(selected.data.requirements).map(
                            ([k, v]: any) => (
                              <div className="personline" key={k}>
                                <span>{ru(k)}</span>
                                <b>{ru(v)}</b>
                              </div>
                            ),
                          )}
                        </details>
                        <details>
                          <summary>Этапы подготовки</summary>
                          {Object.entries(selected.data.pipeline).map(
                            ([k, v]: any) => (
                              <div className="personline" key={k}>
                                <span>{ru(k)}</span>
                                <b>{ru(v)} мин</b>
                              </div>
                            ),
                          )}
                        </details>
                        <details>
                          <summary>Адаптации площадок</summary>
                          {Object.entries(selected.data.overrides).length ? (
                            Object.entries(selected.data.overrides).map(
                              ([id, v]: any) => (
                                <p key={id}>
                                  {ru(resource(+id)?.name)} · {ru(v.version)}
                                  <br />
                                  {v.note}
                                </p>
                              ),
                            )
                          ) : (
                            <p>Отдельные адаптации не заданы</p>
                          )}
                        </details>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
            {page === "Площадки" && venueEditor && (
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
            )}
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
                      <div className="eyebrow">ЕДИНАЯ БАЗА РЕСУРСОВ</div>
                      <h1>{page}</h1>
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
                                page === "Оркестр" ? "Оркестр" : "Звук",
                              specialization: "",
                            })
                      }
                    >
                      <Plus size={16} />
                      {page === "Площадки"
                        ? "Добавить площадку"
                        : page === "Сотрудники"
                          ? "Добавить сотрудника"
                          : "Добавить ресурс"}
                    </button>
                    <label className="search-inline">
                      <Search size={16} />
                      <input
                        placeholder="Найти ресурс"
                        value={find}
                        onChange={(e) => setFind(e.target.value)}
                      />
                    </label>
                  </div>
                  {!selected &&
                    ["Сотрудники", "Оборудование"].includes(page) && (
                      <section className="panel">
                        <div className="toolbar">
                          <button
                            onClick={() => {
                              setCatalogDept("");
                              setCatalogCategory("");
                            }}
                          >
                            Все цеха
                          </button>
                          {[
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
                              {ru(d)}
                            </button>
                          ))}
                        </div>
                        {page === "Оборудование" && catalogDept && (
                          <div className="toolbar">
                            {[
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
                                {ru(c)}
                              </button>
                            ))}
                          </div>
                        )}
                      </section>
                    )}
                  {selected ? (
                    <section className="panel">
                      <div className="section-title">
                        <h2>{ru(selected.name)}</h2>
                        <button onClick={() => setSelected(null)}>Назад</button>
                      </div>
                      {selected.kind === "Person" && (
                        <>
                          <h3>Статистика сотрудника · всё расписание</h3>
                          {personStats ? (
                            <div className="metrics">
                              {Object.entries({
                                Событий: personStats.events,
                                "Часов занятости": personStats.hours,
                                Спектаклей: personStats.performances,
                                Репетиций: personStats.rehearsals,
                                Замен: personStats.replacements,
                                "Интервалов отсутствия": personStats.absences,
                              }).map(([k, v]) => (
                                <div key={k}>
                                  <small>{ru(k)}</small>
                                  <b>{ru(v)}</b>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p>Загрузка статистики…</p>
                          )}
                        </>
                      )}
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
                        >
                          Редактировать
                        </button>
                        <button
                          onClick={() =>
                            run(async () => {
                              await api("/resources/" + selected.id, "DELETE");
                              setSelected(null);
                              await load();
                              setToast("Ресурс удалён");
                            })
                          }
                        >
                          Удалить
                        </button>
                        <button onClick={() => personal(selected)}>
                          Показать в календаре
                        </button>
                        <select
                          aria-label="Состояние ресурса"
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
                          {[
                            "available",
                            "reserved",
                            "in_use",
                            "in_transit",
                            "maintenance",
                            "broken",
                            "limited_use",
                          ].map((x) => (
                            <option key={x} value={x}>
                              {ru(x)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="property-grid">
                        {Object.entries(selected.data).map(([k, v]: any) => (
                          <div key={k}>
                            <small>{ru(k)}</small>
                            <b>
                              {Array.isArray(v)
                                ? v
                                    .map((x) => resource(x)?.name || x)
                                    .join(", ")
                                : ru(v)}
                            </b>
                          </div>
                        ))}
                      </div>
                      {selected.kind === "Venue" && (
                        <>
                          <h3>Механика и позиции</h3>
                          <div className="resource-tags">
                            {resources
                              .filter((r) => r.data.venue_id === selected.id)
                              .map((r) => (
                                <button
                                  key={r.id}
                                  onClick={() => setSelected(r)}
                                >
                                  {ru(r.name)} · {ru(r.status)}
                                </button>
                              ))}
                          </div>
                        </>
                      )}
                      <h3>Отсутствие / блокировка / обслуживание</h3>
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
                        <input required name="label" placeholder="Причина" />
                        <input required name="start" type="datetime-local" />
                        <input required name="end" type="datetime-local" />
                        <button type="submit">Сохранить</button>
                      </form>
                    </section>
                  ) : (
                    <div className="resource-grid">
                      {page === "Оборудование" &&
                        catalogCategory &&
                        !resources.some(
                          (r) =>
                            r.department === catalogDept &&
                            equipmentCategory(r) === catalogCategory,
                        ) && (
                          <p className="notice">
                            В категории «{catalogCategory}» пока нет
                            оборудования. Добавьте ресурс и укажите эту
                            категорию.
                          </p>
                        )}
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
                              <h3>{ru(r.name)}</h3>
                              <p>
                                {ru(r.department)} ·{" "}
                                {ru(r.data.specialization || r.kind)}
                              </p>
                              {r.kind === "Venue" && (
                                <small>
                                  {r.data.width} × {r.data.depth} м ·{" "}
                                  {r.data.soffits} софитов · {r.data.fly_bars}{" "}
                                  штанкетов
                                </small>
                              )}
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
                <h1>Производство в цифрах</h1>
                <div className="metrics">
                  <div>
                    <small>СОБЫТИЙ</small>
                    <b>{analytics.events}</b>
                  </div>
                  <div>
                    <small>АДАПТАЦИЙ</small>
                    <b>{analytics.adaptations}</b>
                  </div>
                  <div>
                    <small>ЗАМЕН</small>
                    <b>{analytics.replacements}</b>
                  </div>
                  <div>
                    <small>ЗАПИСЕЙ ФАКТА</small>
                    <b>{analytics.actuals.length}</b>
                  </div>
                </div>
                <div className="two-col">
                  <section className="panel">
                    <h3>Занятость подразделений · ресурс-часы</h3>
                    {Object.entries(analytics.departments)
                      .filter(([k]) => k)
                      .map(([k, v]: any) => (
                        <div className="chart-row" key={k}>
                          <span>{ru(k)}</span>
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
                          <b>{Math.round(v)}</b>
                        </div>
                      ))}
                  </section>
                  <section className="panel">
                    <h3>Загрузка сотрудников</h3>
                    <div className="scroll-list">
                      {analytics.resources
                        .filter((r: Obj) => r.kind === "Person")
                        .map((r: Obj) => (
                          <div className="personline" key={r.id}>
                            <span>
                              {ru(r.name)}
                              <small>{ru(r.kind)}</small>
                            </span>
                            <b>{r.hours} ч</b>
                          </div>
                        ))}
                    </div>
                  </section>
                </div>
                <section className="panel">
                  <h3>План / факт работ</h3>
                  {analytics.actuals.length ? (
                    analytics.actuals.map((a: Obj, i: number) => (
                      <p key={i}>
                        {ru(a.name)}: план {a.planned} мин → факт {ru(a.actual)}{" "}
                        мин
                      </p>
                    ))
                  ) : (
                    <p className="muted">
                      Фактические интервалы пока не внесены. Откройте событие →
                      Факт работ.
                    </p>
                  )}
                </section>
              </>
            )}
            {page === "Stage Assistant" && (
              <section className="assistant panel">
                <div className="assistant-icon">
                  <Sparkles size={30} />
                </div>
                <h1>Помощник StageOS</h1>
                <p>
                  Задайте вопрос о театре или предложите новое событие.
                  <br />
                  Модель использует данные StageOS; запись — только после вашего
                  подтверждения.
                </p>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Кто ведёт звук на Северном ветре?"
                />
                <button
                  className="primary"
                  disabled={busy || !question}
                  onClick={() =>
                    run(async () => {
                      const a = await api("/assistant", "POST", {
                        text: question,
                      });
                      setAnswer(a.answer);
                      if (a.preview) setPreview(a.preview);
                    })
                  }
                >
                  {busy ? "Модель думает…" : "Спросить"}
                  <ArrowRight size={17} />
                </button>
                {answer && <div className="answer">{ru(answer)}</div>}
                <button onClick={() => go("Настройки")}>
                  Подключить локальную модель
                </button>
              </section>
            )}
            {page === "Уведомления" && (
              <>
                <h1>Уведомления и согласования</h1>
                <section className="panel">
                  {notes.map((n) => (
                    <details key={n.id}>
                      <summary>
                        <b>{ru(n.action)}</b>
                        <span>
                          {date(n.created)} {time(n.created)}
                        </span>
                        {n.data.state && <Badge value={n.data.state} />}
                      </summary>
                      {n.action === "PROPOSED" ? (
                        <>
                          <p>
                            {n.data.plan.title} · {date(n.data.plan.start)}
                          </p>
                          <button onClick={() => setPreview(n.data.plan)}>
                            Посмотреть предложение
                          </button>
                          {n.data.reason && <p>{ru(n.data.reason)}</p>}
                          {n.data.state === "Pending Approval" && (
                            <button
                              onClick={() =>
                                run(async () => {
                                  await api(
                                    "/proposals/" + n.id + "/reject",
                                    "POST",
                                    { reason: "Отклонено пользователем" },
                                  );
                                  setRevision((x) => x + 1);
                                  setToast("Предложение отклонено");
                                })
                              }
                            >
                              Отклонить
                            </button>
                          )}
                          {n.data.state === "Pending Approval" && (
                            <button
                              onClick={() =>
                                run(async () => {
                                  await api(
                                    "/proposals/" + n.id + "/approve",
                                    "POST",
                                  );
                                  setRevision((x) => x + 1);
                                  setToast("Предложение согласовано");
                                })
                              }
                            >
                              Согласовать
                            </button>
                          )}
                        </>
                      ) : (
                        <p>
                          {n.event_id
                            ? "Событие № " + n.event_id
                            : "Обновление ресурса"}
                          {n.data.reason && " · " + n.data.reason}
                        </p>
                      )}
                    </details>
                  ))}
                </section>
              </>
            )}
            {page === "Настройки" && settings && (
              <>
                <h1>Настройки</h1>
                <section className="panel">
                  <h3>База театра</h3>
                  <div className="row">
                    <button onClick={exportDatabase}>
                      Скачать резервную копию
                    </button>
                    <button
                      onClick={() =>
                        document.getElementById("database-upload")?.click()
                      }
                    >
                      Открыть существующую базу
                    </button>
                  </div>
                </section>
                <div className="two-col">
                  <section className="panel">
                    <h3>Локальный помощник</h3>
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
                      />
                      Включить локального помощника
                    </label>
                    {picker(
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
                    )}
                    <label className="field">
                      <span>Адрес сервера модели</span>
                      <input
                        value={settings.endpoint}
                        onChange={(e) =>
                          setSettings({ ...settings, endpoint: e.target.value })
                        }
                      />
                    </label>
                    <label className="field">
                      <span>Название модели</span>
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
                    >
                      Сохранить
                    </button>
                    <p className="muted">
                      Основные функции не зависят от ИИ. При обращении к модели
                      передаются данные сотрудников и расписания на указанный
                      сервер.
                    </p>
                  </section>
                  <section className="panel">
                    <h3>Диагностика</h3>
                    {boot.demo_enabled && <details>
                      <summary>24 демонстрационных конфликта</summary>
                      <p className="muted">
                        Каждый сценарий рассчитывается ядром в изолированной
                        транзакции. Рабочая база не меняется.
                      </p>
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
                    {diagnostics &&
                      Object.entries(diagnostics).map(([k, v]) => (
                        <div className="personline" key={k}>
                          <span>{ru(k)}</span>
                          <small>{ru(v)}</small>
                        </div>
                      ))}
                    <button
                      onClick={() =>
                        run(async () =>
                          setDiagnostics(await api("/diagnostics")),
                        )
                      }
                    >
                      Повторить проверку
                    </button>
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
            aria-label="Предварительный план"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <div className="eyebrow">
                  ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР · НЕ СОХРАНЕНО
                </div>
                <h2>{preview.title}</h2>
                <p>
                  {date(preview.start)} · {time(preview.start)} ·{" "}
                  {preview.venue} · Состав{" "}
                  {preview.request.cast === "A" ? "А" : "Б"}
                </p>
              </div>
              <button
                className="icon"
                aria-label="Закрыть Предварительный план"
                onClick={() => setPreview(null)}
              >
                <X />
              </button>
            </div>
            <div className="modal-body">
              {preview.demo_scenario && (
                <p className="notice">
                  Демонстрационный сценарий: {ru(preview.demo_scenario.name)}.
                  Изменения изолированы и не сохраняются.
                </p>
              )}
              {planContent(preview)}
              {!preview.demo_scenario && (
                <label className="row">
                  <input
                    type="checkbox"
                    checked={!!preview.request.force}
                    disabled={busy}
                    onChange={(e) =>
                      changePlan(preview, { force: e.target.checked })
                    }
                  />
                  Назначить принудительно с сохранением конфликтов
                </label>
              )}
              {(preview.status === "CONFLICT" || preview.request.force) && (
                <label className="field">
                  <span>Обоснование ручного решения администратора</span>
                  <textarea
                    value={override}
                    onChange={(e) => setOverride(e.target.value)}
                    placeholder="Обязательная причина, не менее 12 символов"
                  />
                </label>
              )}
            </div>
            <div className="modal-footer">
              {preview.demo_scenario ? (
                <button onClick={() => setPreview(null)}>
                  Закрыть проверку
                </button>
              ) : (
                <>
                  <button onClick={() => startEdit(preview.request)}>
                    Изменить
                  </button>
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
                  >
                    Найти замены
                  </button>
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
                  >
                    Замены техники
                  </button>
                  <button disabled={busy} onClick={() => save(true)}>
                    На согласование
                  </button>
                  <button
                    className="primary"
                    disabled={
                      busy ||
                      (!preview.request.force &&
                        preview.conflicts.some(
                          (c: Obj) => c.severity === "CRITICAL",
                        )) ||
                      ((preview.status === "CONFLICT" ||
                        preview.request.force) &&
                        override.trim().length < 12)
                    }
                    onClick={() => save()}
                  >
                    Подтвердить
                  </button>
                </>
              )}
            </div>
          </section>
        </div>
      )}
      {detail && (
        <div className="overlay" onClick={() => setDetail(null)}>
          <section
            className="modal detail-modal"
            role="dialog"
            aria-label="Карточка события"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <div className="eyebrow">
                  {ru(detail.kind)} · {ru(detail.status)}
                </div>
                <h2>{detail.title}</h2>
                <p>
                  {date(detail.start)} · {time(detail.start)}–{time(detail.end)}{" "}
                  · {detail.current.venue}
                </p>
              </div>
              <button className="icon" onClick={() => setDetail(null)}>
                <X />
              </button>
            </div>
            <div className="modal-body">
              {detail.current.passport_changed && <p className="notice">Паспорт постановки изменён. Здесь показаны сохранённые назначения. Для применения нового паспорта нажмите «Изменить» и проверьте новый план.</p>}
              {planContent(detail.current)}
              <details>
                <summary>Факт работ</summary>
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
                    <button>Сохранить</button>
                  </form>
                ))}
              </details>
              <details>
                <summary>История изменений</summary>
                {detail.history.map((h: Obj) => (
                  <p key={h.id}>
                    {date(h.created)} {time(h.created)} · {ru(h.action)}{" "}
                    {ru(h.data.reason)}
                  </p>
                ))}
              </details>
            </div>
            <div className="modal-footer">
              {["Approved", "In Preparation", "Ready", "In Progress"].includes(
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
                >
                  Следующий этап
                </button>
              )}
              <button
                onClick={() => {
                  const req = detail.current.request;
                  setDetail(null);
                  analyze(req);
                }}
              >
                Изменить
              </button>
              <button
                onClick={() => {
                  setSlots([detail]);
                  setCalDate(detail.start.slice(0, 10));
                  setDetail(null);
                  setView("production");
                  go("Календарь");
                }}
              >
                Производство
              </button>
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
              >
                Отменить событие
              </button>
            </div>
          </section>
        </div>
      )}
      {resourceEditor && (
        <div className="overlay" onClick={() => setResourceEditor(null)}>
          <section
            className="modal"
            role="dialog" aria-modal="true" aria-label="Редактор ресурса"
            style={{ maxWidth: 540 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h2>
                {resourceEditor.id ? "Редактировать ресурс" : "Новый ресурс"}
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
                  const data = {
                    ...(r.data || {}),
                    specialization: r.specialization || r.department,
                    qualification: [...new Set([...(r.data?.qualification || []), r.department, r.specialization || r.department])],
                  };
                  const result = await api(
                    "/resources" + (r.id ? "/" + r.id : ""),
                    r.id ? "PATCH" : "POST",
                    {
                      kind: r.kind,
                      name: r.name,
                      department: r.department,
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
                <span>Название / ФИО</span>
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
              {!resourceEditor.id &&
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
                )}
              <label className="field">
                <span>Подразделение</span>
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
              <datalist id="staff-departments">{departments.map(d => <option key={d} value={d}/>)}</datalist>
              <label className="field">
                <span>Специализация / инструмент</span>
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
              {resourceEditor.kind === "Room" && <label className="field"><span>Площадка помещения</span><select required value={resourceEditor.data?.venue_id || 0} onChange={e => setResourceEditor({...resourceEditor,data:{...resourceEditor.data,venue_id:+e.target.value}})}><option value="0">Выберите площадку</option>{resources.filter(r=>r.kind==="Venue").map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
              {["Room","Vehicle"].includes(resourceEditor.kind) && <label className="field"><span>Вместимость</span><input type="number" min={0} value={resourceEditor.data?.capacity || 0} onChange={e=>setResourceEditor({...resourceEditor,data:{...resourceEditor.data,capacity:+e.target.value}})}/></label>}
              {resourceEditor.kind === "Equipment Kit" && <label className="field"><span>Имущество комплекта</span><select multiple size={6} value={(resourceEditor.data?.items || []).map(String)} onChange={e=>setResourceEditor({...resourceEditor,data:{...resourceEditor.data,items:Array.from(e.target.selectedOptions).map(o=>+o.value)}})}>{resources.filter(r=>r.kind==="Equipment").map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></label>}
              {resourceEditor.kind === "Equipment" && (
                <label className="field">
                  <span>Категория оборудования</span>
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
                    {[
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
                    ))}
                  </datalist>
                </label>
              )}
              <button className="primary" type="submit">
                Сохранить ресурс
              </button>
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
                placeholder="Команда, сотрудник, постановка…"
                value={find}
                onChange={(e) => setFind(e.target.value)}
              />
              <kbd>Esc</kbd>
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
                    {ru(r.name)}
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
createRoot(document.getElementById("root")!).render(<App />);
