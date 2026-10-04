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
      <h2>Поштучное имущество постановки</h2>
      <div className="toolbar">
        {["Свет", "Звук", "Видео", "Сцена", "Реквизит", "Костюм"].map((d) => (
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
            {d}
          </button>
        ))}
      </div>
      <label className="field">
        <span>Тип имущества</span>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {["Equipment", "Scenery", "Prop", "Costume"].map((k) => (
            <option value={k} key={k}>
              {ru(k)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Категория</span>
        <input
          list="unit-categories"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <datalist id="unit-categories">
          {[
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
          ))}
        </datalist>
      </label>
      <details>
        <summary>Выбрать существующие единицы · {rows.length}</summary>
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
      <h3>Создать позицию и включить в постановку</h3>
      <div className="row">
        <label className="field">
          <span>Название позиции</span>
          <input
            value={name}
            placeholder="Например: BSW 350 или Стулья для Последнего рейса"
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Количество, шт.</span>
          <input
            type="number"
            min={1}
            max={200}
            value={qty}
            onChange={(e) => setQty(+e.target.value)}
          />
        </label>
      </div>
      {kind === "Scenery" && (
        <div className="row">
          {Object.entries(size).map(([k, v]) => (
            <label className="field" key={k}>
              <span>
                {ru(k)}
                {k === "mass" ? ", кг" : ", м"}
              </span>
              <input
                type="number"
                min={0}
                step={0.1}
                value={v}
                onChange={(e) => setSize({ ...size, [k]: +e.target.value })}
              />
            </label>
          ))}
        </div>
      )}
      {kind === "Scenery" && <div className="row">{[["setup","Время установки, мин"],["crew","Монтажники, чел."],["transport_width","Транспортная ширина, м"],["transport_height","Транспортная высота, м"]].map(([k,label])=><label className="field" key={k}><span>{label}</span><input type="number" min={0} step={k.startsWith("transport_")?0.1:1} value={(sceneryOptions as any)[k]} onChange={e=>setSceneryOptions({...sceneryOptions,[k]:+e.target.value})}/></label>)}<label><input type="checkbox" checked={sceneryOptions.fly} onChange={e=>setSceneryOptions({...sceneryOptions,fly:e.target.checked})}/>Декорация требует верхнего подвеса</label></div>}
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
      >
        Создать и добавить
      </button>
      {error && <p role="alert">{error}</p>}
      <h3>Включено в постановку</h3>
      {Object.entries(groups).map(([n, items]) => (
        <div className="personline" key={n}>
          <b>
            {ru(n)} — {items.length} шт.
          </b>
          <button
            onClick={() =>
              onChange(ids.filter((id) => !items.some((r) => r.id === id)))
            }
          >
            Убрать из постановки
          </button>
        </div>
      ))}
      <p className="muted">
        Каждая штука — отдельная единица в базе. Пересечения проверяются по
        конкретным единицам. Созданное имущество остаётся в каталоге, даже если
        отменить редактирование постановки.
      </p>
    </section>
  );
}
