import React, { useState } from "react";
const defaults: Record<string, any> = {
  seats: 300,
  width: 12,
  depth: 10,
  height: 8,
  power: 80,
  dmx: 8,
  orchestra: 35,
  fly_system: true,
  movement: false,
  bar_load: 300,
  gate_width: 3,
  gate_height: 3,
  travel: 30,
  soffits: 3,
  fly_bars: 8,
  lighting_positions: 5,
  pa: true,
  video: true,
  rooms: 4,
  opening: 8,
  closing: 24,
};
const labels: Record<string, string> = {
  seats: "Мест в зрительном зале",
  width: "Ширина сцены, м",
  depth: "Глубина сцены, м",
  height: "Рабочая высота, м",
  power: "Доступная мощность, кВт",
  dmx: "Количество световых линий",
  orchestra: "Мест для оркестра",
  fly_system: "Верхняя механика",
  movement: "Движение подвесов во время спектакля",
  bar_load: "Предельная нагрузка штанкета, кг",
  gate_width: "Ширина грузовых ворот, м",
  gate_height: "Высота грузовых ворот, м",
  travel: "Время переезда от базы, мин",
  soffits: "Количество софитов",
  fly_bars: "Количество штанкетов",
  lighting_positions: "Количество световых позиций",
  pa: "Стационарная звуковая система",
  video: "Стационарная видеосистема",
  rooms: "Количество гримёрных",
  opening: "Открытие площадки, час",
  closing: "Закрытие площадки, час",
};
export default function VenueEditor({
  initial,
  onSave,
  onCancel,
}: {
  initial: any;
  onSave: (p: any) => Promise<void>;
  onCancel: () => void;
}) {
  const [d, setD] = useState({
      ...initial,
      data: { ...defaults, ...initial.data },
    }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <section className="panel">
      <h1>{d.id ? "Редактировать площадку" : "Добавить площадку"}</h1>
      <label className="field">
        <span>Название площадки</span>
        <input
          value={d.name || ""}
          onChange={(e) => setD({ ...d, name: e.target.value })}
        />
      </label>
      <div className="check-grid">
        {Object.entries(defaults).map(([k, v]) => (
          <label className="field" key={k}>
            <span>{labels[k]}</span>
            <input
              type={typeof v === "boolean" ? "checkbox" : "number"}
              min={0}
              step={
                [
                  "width",
                  "depth",
                  "height",
                  "gate_width",
                  "gate_height",
                  "bar_load",
                ].includes(k)
                  ? 0.1
                  : 1
              }
              checked={typeof v === "boolean" ? d.data[k] : undefined}
              value={typeof v === "boolean" ? undefined : d.data[k]}
              onChange={(e) =>
                setD({
                  ...d,
                  data: {
                    ...d.data,
                    [k]:
                      typeof v === "boolean"
                        ? e.target.checked
                        : +e.target.value,
                  },
                })
              }
            />
          </label>
        ))}
      </div>
      <p className="muted">
        Штанкеты, софиты и световые позиции создаются как отдельные ресурсы. При
        уменьшении количества лишние позиции выводятся из эксплуатации; их
        история сохраняется.
      </p>
      {error && <p role="alert">{error}</p>}
      <button onClick={onCancel}>Отмена</button>
      <button
        className="primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onSave(d);
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Сохранить площадку
      </button>
    </section>
  );
}
