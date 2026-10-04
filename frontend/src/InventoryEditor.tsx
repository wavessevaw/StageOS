import { tr } from "./i18n";
import React, { useState } from "react";
import { ru } from "./ru";
export default function InventoryEditor({
  resources,
  ids,
  onChange,
  onCreate,
}: {
  resources: any[];
  ids: number[];
  onChange: (ids: number[]) => void;
  onCreate: (b: any) => Promise<any[]>;
}) {
  const [sceneryOptions, setSceneryOptions] = useState({setup:10,crew:2,fly:false,transport_width:0,transport_height:0});
  const [dept, setDept] = useState("Свет"),
    [category, setCategory] = useState(""),
    [name, setName] = useState(""),
    [kind, setKind] = useState("Equipment"),
    [qty, setQty] = useState(1),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [size, setSize] = useState({ width: 1, height: 1, depth: 1, mass: 1 });
  const rows = resources.filter(
    (r) =>
      r.department === dept &&
      r.kind === kind &&
      (!category || r.data.category === category),
  );
  const groups: Record<string, any[]> = {};
  for (const r of resources.filter((r) => ids.includes(r.id))) {
    const key = r.data.item_name || r.name;
    (groups[key] ??= []).push(r);
  }
  return (
    <section className="panel">
      <h2>{tr("Поштучное имущество постановки")}</h2>
      <div className="toolbar">
        {tr(["Свет", "Звук", "Видео", "Сцена", "Реквизит", "Костюм"].map((d) => (
          <button
            key={d}
            className={dept === d ? "primary" : ""}
            onClick={() => {
              setDept(d);
              setCategory("");
              setKind(
                d === "Сцена"
                  ? "Scenery"
                  : d === "Реквизит"
                    ? "Prop"
                    : d === "Костюм"
                      ? "Costume"
                      : "Equipment",
              );
            }}
          >
            {tr(d)}
          </button>
        )))}
      </div>
      <label className="field">
        <span>{tr("Тип имущества")}</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {tr(["Equipment", "Scenery", "Prop", "Costume"].map((k) => (
            <option value={k} key={k}>
              {tr(ru(k))}
            </option>
          )))}
        </select>
      </label>
      <label className="field">
        <span>{tr("Категория")}</span>
        <input
          list="unit-categories"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <datalist id="unit-categories">
          {tr([
            "Микрофоны",
            "Консоли",
            "Мониторы",
            "BSW",
            "Wash",
            "LED Bar",
            "Дымка",
            "Дым",
            "Проекторы",
            "Декорации",
            "Стулья",
            "Задники",
          ].map((c) => (
            <option value={c} key={c} />
          )))}
        </datalist>
      </label>
      <details>
        <summary>{tr("Выбрать существующие единицы · ")}{tr(rows.length)}</summary>
        {rows.map((r) => (
          <label className="personline" key={r.id}>
            <input
              type="checkbox"
              checked={ids.includes(r.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...ids, r.id]
                    : ids.filter((i) => i !== r.id),
                )
              }
            />
            {ru(r.name)}
          </label>
        ))}
      </details>
      <h3>{tr("Создать позицию и включить в постановку")}</h3>
      <div className="row">
        <label className="field">
          <span>{tr("Название позиции")}</span>
          <input
            value={name}
            placeholder={tr("Например: BSW 350 или Стулья для Последнего рейса")}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{tr("Количество, шт.")}</span>
          <input
            type="number"
            min={1}
            max={200}
            value={qty}
            onChange={(e) => setQty(+e.target.value)}
          />
        </label>
      </div>
      {tr(kind === "Scenery" && (
        <div className="row">
          {tr(Object.entries(size).map(([k, v]) => (
            <label className="field" key={k}>
              <span>
                {tr(ru(k))}
                {tr(k === "mass" ? ", кг" : ", м")}
              </span>
              <input
                type="number"
                min={0}
                step={0.1}
                value={v}
                onChange={(e) => setSize({ ...size, [k]: +e.target.value })}
              />
            </label>
          )))}
        </div>
      ))}
      {tr(kind === "Scenery" && <div className="row">{tr([["setup","Время установки, мин"],["crew","Монтажники, чел."],["transport_width","Транспортная ширина, м"],["transport_height","Транспортная высота, м"]].map(([k,label])=><label className="field" key={k}><span>{tr(label)}</span><input type="number" min={0} step={k.startsWith("transport_")?0.1:1} value={(sceneryOptions as any)[k]} onChange={e=>setSceneryOptions({...sceneryOptions,[k]:+e.target.value})}/></label>))}<label><input type="checkbox" checked={sceneryOptions.fly} onChange={e=>setSceneryOptions({...sceneryOptions,fly:e.target.checked})}/>{tr("Декорация требует верхнего подвеса")}</label></div>)}
      <button
        disabled={busy || !name.trim()}
        onClick={async () => {
          setBusy(true);
          try {
            const created = await onCreate({
              name,
              kind,
              department: dept,
              quantity: qty,
              data: { category, ...(kind === "Scenery" ? {...size,...sceneryOptions} : {}) },
            });
            onChange([...ids, ...created.map((r) => r.id)]);
            setName("");
            setError("");
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >{tr("Создать и добавить")}</button>
      {tr(error && <p role="alert">{tr(error)}</p>)}
      <h3>{tr("Включено в постановку")}</h3>
      {tr(Object.entries(groups).map(([n, items]) => (
        <div className="personline" key={n}>
          <b>
            {tr(ru(n))}{tr(" — ")}{tr(items.length)}{tr(" шт.")}</b>
          <button
            onClick={() =>
              onChange(ids.filter((id) => !items.some((r) => r.id === id)))
            }
          >{tr("Убрать из постановки")}</button>
        </div>
      )))}
      <p className="muted">{tr("Каждая штука — отдельная единица в базе. Пересечения проверяются по конкретным единицам. Созданное имущество остаётся в каталоге, даже если отменить редактирование постановки.")}</p>
    </section>
  );
}
