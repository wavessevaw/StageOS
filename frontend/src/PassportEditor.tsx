import React, { useState } from "react";
import InventoryEditor from "./InventoryEditor";
import PeopleCastEditor from "./PeopleCastEditor";
import { ru } from "./ru";
type O = Record<string, any>;
const labels: O = {
  sound_notes:"Звуковой паспорт и сигнальные маршруты",
  lighting_notes:"Световой паспорт и развеска",
  video_notes:"Видеопаспорт и маршруты сигналов",
  stage_notes:"Сценические работы и механика",
  costume_notes:"Костюмы и переодевания",
  props_notes:"Реквизит и расходные материалы",
  transport_notes:"Транспорт и логистика",
  safety_notes:"Особые условия и меры безопасности",
  genre: "Жанр",
  duration: "Продолжительность, мин",
  preparation: "Подготовка, мин",
  home_venue: "Основная площадка",
  responsibles: "Ответственные",
  roles: "Роли и составы",
  role: "Персонаж",
  A: "Первый состав",
  B: "Второй состав",
  eligible: "Допущенные исполнители / резерв",
  groups: "Хор, балет, оркестр, грим и костюм",
  crew: "Технические команды",
  orchestra_versions: "Версии оркестра",
  equipment_kits: "Комплекты оборудования",
  scenery: "Декорации",
  props: "Реквизит и костюмы",
  vehicle: "Транспорт",
  requirements: "Технические требования",
  scenes: "Сцены репетиции",
  pipeline: "Этапы подготовки, мин",
  overrides: "Адаптации площадок",
  name: "Название",
  width: "Ширина",
  depth: "Глубина",
  height: "Высота",
  soffits: "Минимум софитов",
  preferred_soffits: "Предпочтительно софитов",
  fly_bars: "Штанкеты",
  moving_fly_bars: "Подвижные штанкеты",
  power: "Мощность",
  dmx: "Количество световых линий",
  orchestra: "Оркестр",
  bar_load: "Нагрузка на штанкет",
  gate_width: "Ширина ворот",
  gate_height: "Высота ворот",
  lighting_positions: "Световые позиции",
  pa: "Звуковая система",
  video: "Видео",
  load: "Погрузка",
  unload: "Разгрузка",
  stage: "Монтаж сцены",
  lighting: "Свет",
  sound: "Звук",
  rf: "Проверка радиочастот",
  check: "Проверка",
  teardown: "Демонтаж",
  version: "Версия",
  note: "Примечание",
};
export default function PassportEditor({
  initial,
  resources,
  onSave,
  onCancel,
  onCreate,
}: {
  initial: O;
  resources: O[];
  onSave: (p: O) => Promise<void>;
  onCancel: () => void;
  onCreate: (b: O) => Promise<O[]>;
}) {
  const [draft, setDraft] = useState<O>(() => {
      const p = JSON.parse(JSON.stringify(initial));
      for (const key of ["sound_notes","lighting_notes","video_notes","stage_notes","costume_notes","props_notes","transport_notes","safety_notes"]) p.data[key] ??= "";
      p.data.responsibles = {
        ...Object.fromEntries(
          [
            "Режиссёр",
            "Дирижёр",
            "Помреж",
            "Техдир",
            "Звук",
            "Свет",
            "Видео",
            "Сцена",
          ].map((d) => [d, 0]),
        ),
        ...p.data.responsibles,
      };
      p.data.crew = {
        Сцена: [],
        Звук: [],
        Свет: [],
        Видео: [],
        ...p.data.crew,
      };
      for (const section of ["groups","crew"]) {
        p.data[section+"_casts"] ??= {};
        for (const [dept,ids] of Object.entries(p.data[section]))
          p.data[section+"_casts"][dept] = {A:[...(ids as number[])],B:[...(ids as number[])],...p.data[section+"_casts"][dept]};
      }
      return p;
    }),
    [section, setSection] = useState("Основное"),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  const sections: O = {
    Основное: ["genre", "duration", "home_venue"],
    Люди: ["responsibles", "roles", "groups", "crew", "orchestra_versions"],
    Техника: ["equipment_kits", "scenery", "props", "vehicle", "requirements", "sound_notes", "lighting_notes", "video_notes", "stage_notes", "costume_notes", "props_notes", "transport_notes", "safety_notes"],
    Производство: ["pipeline", "scenes"],
    Адаптации: ["overrides"],
  };
  const change = (path: (string | number)[], value: any) =>
    setDraft((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      let node = next.data;
      for (const k of path.slice(0, -1)) node = node[k];
      node[path[path.length - 1]] = value;
      if (path[0] === "roles" && ["A","B"].includes(String(path[path.length-1])) && value)
        node.eligible = [...new Set([...(node.eligible || []),value])];
      return next;
    });
  const candidates = (path: (string | number)[]) => {
    const root = path[0],
      last = path[path.length - 1];
    let kinds: string[] = [];
    if (
      ["responsibles", "groups", "crew", "orchestra_versions"].includes(
        String(root),
      ) ||
      (root === "roles" &&
        ["A", "B", "eligible", "reserve", "Reserve"].includes(String(last))) ||
      (root === "overrides" && last === "orchestra")
    )
      kinds = ["Person"];
    if (last === "home_venue") kinds = ["Venue"];
    if (last === "vehicle") kinds = ["Vehicle"];
    if (last === "equipment_kits") kinds = ["Equipment Kit"];
    if (last === "scenery") kinds = ["Scenery"];
    if (last === "props") kinds = ["Prop", "Costume"];
    return kinds.length
      ? resources.filter((r) => {
          if (!kinds.includes(r.kind)) return false;
          if (
            ["responsibles", "groups", "crew"].includes(String(root)) &&
            path.length === 2
          )
            return r.department === path[1] || (r.data.qualification || []).includes(path[1]);
          if (
            root === "orchestra_versions" ||
            (root === "overrides" && last === "orchestra")
          )
            return r.department === "Оркестр";
          if (root === "roles") return r.department === "Артисты";
          return true;
        })
      : null;
  };
  function field(value: any, path: (string | number)[]): React.ReactNode {
    const key = String(path[path.length - 1]),
      title = ru(labels[key] || key),
      opts = candidates(path);
    if (path.length === 1 && ["groups","crew"].includes(key)) {
      const casts=draft.data[key+"_casts"];
      return <section key={key}><h3>{title}</h3>
        {Object.keys(value).map(dept=><PeopleCastEditor key={dept} department={dept} resources={resources} casts={casts[dept] || {A:[],B:[]}} onChange={people=>change([key+"_casts"],{...casts,[dept]:people})}/>)}
        <label className="field"><span>Добавить подразделение</span><select value="" onChange={e=>{if(e.target.value){change([key],{...value,[e.target.value]:[]});change([key+"_casts"],{...casts,[e.target.value]:{A:[],B:[]}});}}}>
          <option value="">Выберите цех</option>{[...new Set(resources.filter(r=>r.kind==="Person").map(r=>r.department))].filter(d=>!(d in value)).map(d=><option key={d} value={d}>{d}</option>)}
        </select></label></section>;
    }
    if (path[0] === "scenes" && key === "roles" && Array.isArray(value))
      return (
        <label className="field" key={path.join(".")}>
          <span>Роли сцены</span>
          <select
            multiple
            size={5}
            value={value.map(String)}
            onChange={(e) =>
              change(
                path,
                Array.from(e.target.selectedOptions).map((o) => +o.value),
              )
            }
          >
            {draft.data.roles.map((r: O, i: number) => (
              <option key={i} value={i}>
                {r.role}
              </option>
            ))}
          </select>
          <small>Ctrl + щелчок — несколько ролей</small>
        </label>
      );
    if (opts && (typeof value === "number" || Array.isArray(value)))
      return (
        <label className="field" key={path.join(".")}>
          <span>{title}</span>
          <select
            aria-label={title}
            multiple={Array.isArray(value)}
            size={Array.isArray(value) ? 5 : undefined}
            value={Array.isArray(value) ? value.map(String) : String(value)}
            onChange={(e) =>
              change(
                path,
                Array.isArray(value)
                  ? Array.from(e.target.selectedOptions).map((o) => +o.value)
                  : +e.target.value,
              )
            }
          >
            {!Array.isArray(value) && (
              <option value="0">{key === "vehicle" ? "Без транспорта" : "Не назначен"}</option>
            )}
            {opts.map((r) => (
              <option key={r.id} value={r.id}>
                {ru(r.name)} · {ru(r.department)}
              </option>
            ))}
          </select>
          {Array.isArray(value) && (
            <small>Ctrl + щелчок — выбрать несколько или снять выбор</small>
          )}
        </label>
      );
    if (Array.isArray(value))
      return (
        <section key={path.join(".")} className="panel">
          <h3>{title}</h3>
          {value.map((v, i) => (
            <div className="panel" key={i}>
              {field(v, [...path, i])}
              <button
                type="button"
                onClick={() => {
                  change(path, value.filter((_, j) => j !== i));
                  if (path.length === 1 && key === "roles") change(["scenes"], draft.data.scenes.map((scene: O)=>({...scene,roles:scene.roles.filter((r: number)=>r!==i).map((r: number)=>r>i?r-1:r)})));
                }}
              >
                Удалить пункт
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              change(path, [
                ...value,
                key === "roles" && path.length === 1
                  ? { role: "Новая роль", A: 0, B: 0, eligible: [] }
                  : key === "scenes"
                    ? { name: "Новая сцена", roles: [] }
                    : 0,
              ])
            }
          >
            Добавить пункт
          </button>
        </section>
      );
    if (value && typeof value === "object")
      return (
        <div className="passport-fields" key={path.join(".")}>
          <h3>{title}</h3>
          {Object.entries(value).map(([k, v]) => field(v, [...path, k]))}
          {["groups","crew"].includes(key) && <label className="field"><span>Добавить подразделение</span><select value="" onChange={e=>{if(e.target.value)change(path,{...value,[e.target.value]:[]})}}><option value="">Выберите цех</option>{[...new Set(resources.filter(r=>r.kind==="Person").map(r=>r.department))].filter(d=>!(d in value)).map(d=><option key={d} value={d}>{d}</option>)}</select></label>}
          {key === "overrides" && (
            <label className="field">
              <span>Добавить адаптацию площадки</span>
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value)
                    change(path, {
                      ...value,
                      [e.target.value]: {
                        version: "REDUCED VERSION",
                        requirements: { ...draft.data.requirements },
                        orchestra: [],
                        scenery: [],
                        note: "",
                      },
                    });
                }}
              >
                <option value="">Выберите площадку</option>
                {resources
                  .filter((r) => r.kind === "Venue")
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {path[0] === "overrides" && path.length === 2 && (
            <button
              type="button"
              onClick={() => {
                const d = { ...draft.data.overrides };
                delete d[key];
                change(["overrides"], d);
              }}
            >
              Удалить адаптацию
            </button>
          )}
        </div>
      );
    if (key.endsWith("_notes")) return <label className="field" key={key}><span>{title}</span><textarea value={value || ""} onChange={e=>change(path,e.target.value)} /></label>;
    return (
      <label className="field" key={path.join(".")}>
        <span>{title}</span>
        <input
          type={
            typeof value === "boolean"
              ? "checkbox"
              : typeof value === "number"
                ? "number"
                : "text"
          }
          checked={typeof value === "boolean" ? value : undefined}
          value={typeof value === "boolean" ? undefined : (value ?? "")}
          onChange={(e) =>
            change(
              path,
              typeof value === "boolean"
                ? e.target.checked
                : typeof value === "number"
                  ? Number(e.target.value)
                  : e.target.value,
            )
          }
        />
      </label>
    );
  }
  return (
    <section className="panel">
      <h1>{draft.id ? "Редактировать постановку" : "Добавить спектакль"}</h1>
      <label className="field">
        <span>Название постановки</span>
        <input
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </label>
      <div className="toolbar">
        {Object.keys(sections).map((s) => (
          <button
            className={section === s ? "primary" : ""}
            key={s}
            onClick={() => setSection(s)}
          >
            {s}
          </button>
        ))}
      </div>
      {section === "Техника" && (
        <InventoryEditor
          resources={resources}
          ids={draft.data.items || []}
          onChange={(ids) => change(["items"], ids)}
          onCreate={onCreate}
        />
      )}
      {section === "Основное" && <p className="muted">Подготовка рассчитывается по этапам в разделе «Производство»; время переезда зависит от площадки. Постановку можно сохранить с неполным наполнением и дополнять по мере подготовки. Комплекты, помещения и транспорт можно добавить через каталог ресурсов.</p>}
      {sections[section].map((k: string) => field(draft.data[k], [k]))}
      {error && (
        <p role="alert" className="notice">
          {error}
        </p>
      )}
      <div className="toolbar">
        <button onClick={onCancel}>Отмена</button>
        <button
          className="primary"
          disabled={saving}
          onClick={async () => {
            setSaving(true);
            try {
              await onSave(draft);
            } catch (e: any) {
              setError(e.message);
            } finally {
              setSaving(false);
            }
          }}
        >
          Сохранить постановку
        </button>
      </div>
      <p className="muted">
        Изменения паспорта применяются при следующем расчёте. Уже сохранённые
        события требуют отдельного изменения и подтверждения.
      </p>
    </section>
  );
}
