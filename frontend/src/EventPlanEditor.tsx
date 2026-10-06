import React, { useState } from "react";
import { tr } from "./i18n";
type Obj = Record<string, any>;
export function EventRoles({
  plan,
  resources,
  busy,
  onChange,
}: {
  plan: Obj;
  resources: Obj[];
  busy: boolean;
  onChange: (changes: Obj) => void;
}) {
  const roles = plan.event_roles || [];
  if (!roles.length) return null;
  const people = resources.filter(
    (r) =>
      r.kind === "Person" &&
      !r.data.retired &&
      (r.department === "Артисты" || r.data.qualification?.includes("Артисты")),
  );
  return (
    <section className="event-role-editor">
      <h3>{tr("Актёры на это событие")}</h3>
      <p className="muted">
        {tr(
          "Состав А или Б — исходный шаблон. Для каждой роли можно выбрать своего исполнителя только на эту дату.",
        )}
      </p>
      {roles.map((role: Obj) => (
        <div className="event-role-row" key={role.index}>
          <label className="field">
            <span>{role.role}</span>
            <select
              aria-label={tr("Исполнитель роли") + " " + role.role}
              value={role.actual_id || ""}
              disabled={busy}
              onChange={(e) =>
                onChange({
                  role_assignments: {
                    ...plan.request.role_assignments,
                    [role.index]: Number(e.target.value),
                  },
                })
              }
            >
              <option value="" disabled>
                {tr("Выберите актёра")}
              </option>
              {[...people].sort((a,b)=>Number(role.eligible_ids.includes(b.id))-Number(role.eligible_ids.includes(a.id)) || a.name.localeCompare(b.name,"ru")).map((person) => (
                <option key={person.id} value={person.id} data-eligible={role.eligible_ids.includes(person.id)} style={role.eligible_ids.includes(person.id) ? {color:"var(--accent)",fontWeight:600}:undefined}>
                  {person.name}{role.eligible_ids.includes(person.id) ? tr(" · допущен к роли") : ""}
                  {person.id === role.baseline_id
                    ? tr(" · исходный состав")
                    : role.eligible_ids.length &&
                        !role.eligible_ids.includes(person.id)
                      ? tr(" · требуется допуск к роли")
                      : ""}
                </option>
              ))}
            </select>
          </label>
          {plan.request.role_assignments?.[role.index] && (
            <button
              disabled={busy}
              onClick={() => {
                const roles = { ...plan.request.role_assignments };
                delete roles[role.index];
                onChange({ role_assignments: roles });
              }}
            >
              {tr("Вернуть из состава")}
            </button>
          )}
        </div>
      ))}
    </section>
  );
}
export function AddStage({
  plan,
  busy,
  onChange,
}: {
  plan: Obj;
  busy: boolean;
  onChange: (changes: Obj) => Promise<any> | void;
}) {
  const [open, setOpen] = useState(false);
  const main = plan.request.kind === "Репетиция" ? "Репетиция" : "Спектакль";
  const [form, setForm] = useState({
    name: "",
    department: "Все",
    start: (() => {
      const d = new Date(plan.start);
      d.setMinutes(d.getMinutes() - 30);
      return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 16);
    })(),
    duration: "30",
    after: "",
    before: main,
  });
  const field = (key: string, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));
  return (
    <div className="extra-stage-editor">
      <div className="stage-toolbar">
        <button disabled={busy} onClick={() => setOpen(!open)}>
          {tr(open ? "Закрыть добавление" : "Добавить этап")}
        </button>
        {(plan.request.removed_tasks || []).map((name: string) => (
          <button
            key={name}
            disabled={busy}
            onClick={() =>
              onChange({
                removed_tasks: plan.request.removed_tasks.filter(
                  (n: string) => n !== name,
                ),
              })
            }
          >
            {tr("Восстановить")}: {name}
          </button>
        ))}
      </div>
      {open && (
        <div className="extra-stage-form">
          <label className="field">
            <span>{tr("Название этапа")}</span>
            <input
              value={form.name}
              maxLength={100}
              onChange={(e) => field("name", e.target.value)}
            />
          </label>
          <label className="field">
            <span>{tr("Подразделение этапа")}</span>
            <select
              value={form.department}
              onChange={(e) => field("department", e.target.value)}
            >
              {[
                "Все",
                "Артисты",
                "Хор",
                "Балет",
                "Оркестр",
                "Сцена",
                "Свет",
                "Звук",
                "Видео",
                "Реквизит",
                "Грим",
                "Костюм",
                "Транспорт",
              ].map((d) => (
                <option key={d} value={d}>
                  {tr(d)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{tr("Начало нового этапа")}</span>
            <input
              type="datetime-local"
              value={form.start}
              onChange={(e) => field("start", e.target.value)}
            />
          </label>
          <label className="field">
            <span>{tr("Длительность нового этапа, мин")}</span>
            <input
              type="number"
              min={1}
              max={10080}
              value={form.duration}
              onChange={(e) => field("duration", e.target.value)}
            />
          </label>
          {[
            ["after", "После этапа"],
            ["before", "До этапа"],
          ].map(([key, label]) => (
            <label className="field" key={key}>
              <span>{tr(label)}</span>
              <select
                value={(form as Obj)[key]}
                onChange={(e) => field(key, e.target.value)}
              >
                <option value="">{tr("Без зависимости")}</option>
                {plan.tasks.map((t: Obj) => (
                  <option value={t.name} key={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button
            className="primary"
            disabled={
              busy ||
              !form.name.trim() ||
              !form.start ||
              Number(form.duration) < 1 ||
              Number(form.duration) > 10080
            }
            onClick={async () => {
              const next = await onChange({
                extra_tasks: [
                  ...(plan.request.extra_tasks || []),
                  {
                    ...form,
                    duration: Number(form.duration),
                    after: form.after || null,
                    before: form.before || null,
                  },
                ],
              });
              if (next) {
                setOpen(false);
                setForm((f) => ({ ...f, name: "" }));
              }
            }}
          >
            {tr("Добавить в план и проверить")}
          </button>
        </div>
      )}
    </div>
  );
}
export function removeStage(plan: Obj, name: string): Obj {
  const edits = { ...plan.request.task_overrides };
  delete edits[name];
  if ((plan.request.extra_tasks || []).some((t: Obj) => t.name === name))
    return {
      task_overrides: edits,
      extra_tasks: plan.request.extra_tasks
        .filter((t: Obj) => t.name !== name)
        .map((t: Obj) => ({
          ...t,
          after: t.after === name ? null : t.after,
          before: t.before === name ? null : t.before,
        })),
    };
  return {
    task_overrides: edits,
    removed_tasks: [...new Set([...(plan.request.removed_tasks || []), name])],
    extra_tasks: (plan.request.extra_tasks || []).map((t: Obj) => ({
      ...t,
      after: t.after === name ? null : t.after,
      before: t.before === name ? null : t.before,
    })),
  };
}
