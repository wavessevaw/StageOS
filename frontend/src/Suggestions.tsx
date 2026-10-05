import React, { useEffect, useRef, useState } from "react";
import { tr } from "./i18n";
type Obj = Record<string, any>;
type Api = (path: string, method?: string, body?: any) => Promise<any>;
export function HistorySuggestions({
  request,
  api,
  onReview,
}: {
  request: Obj;
  api: Api;
  onReview: (r: Obj) => void;
}) {
  const [result, setResult] = useState<Obj | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const key = JSON.stringify(request);
  useEffect(() => {
    const g = ++generation.current;
    setResult(null);
    setError("");
    if (!request.production_id || !request.venue_id) return;
    const timer = setTimeout(() => {
      api("/suggestions", "POST", request)
        .then((r) => {
          if (g === generation.current) setResult(r);
        })
        .catch(() => {
          if (g === generation.current)
            setError("Подсказки временно недоступны");
        });
    }, 700);
    return () => clearTimeout(timer);
  }, [key]);
  async function explain() {
    const g = generation.current;
    setBusy(true);
    try {
      const r = await api("/suggestions/explain", "POST", request);
      if (g === generation.current) setResult(r);
    } catch {
      setError("Подсказки временно недоступны");
    } finally {
      setBusy(false);
    }
  }
  if (!result?.enabled && !error) return null;
  return (
    <section className="history-suggestions panel">
      <h3>{tr("Подсказки по истории театра")}</h3>
      <p className="muted">
        {tr(
          "Предложения основаны на подтверждённых назначениях. Ничего не сохраняется без проверки и подтверждения.",
        )}
      </p>
      {error && <p role="alert">{tr(error)}</p>}
      {result?.suggestions?.length ? (
        <>
          <div className="suggestion-options">
            {result.suggestions.map((s: Obj) => (
              <div key={s.id}>
                <strong>
                  {s.count} / {result.samples} · {Math.round(s.share * 100)}%
                </strong>
                <p>
                  {s.roles
                    .map((r: Obj) => r.role + ": " + r.person)
                    .join(" · ")}
                </p>
                <small>
                  {tr("Этапов")}: {s.stages.length} · {tr("Конфликтов")}:{" "}
                  {s.conflicts}
                </small>
                <button onClick={() => onReview(s.request)}>
                  {tr("Посмотреть предложение")}
                </button>
              </div>
            ))}
          </div>
          <button disabled={busy} onClick={explain}>
            {tr(
              busy
                ? "Модель анализирует…"
                : "Объяснить с помощью локальной модели",
            )}
          </button>
          {result.explanation && <p>{tr(result.explanation)}</p>}
          {result.llm_status === "disabled" && (
            <p className="muted">
              {tr("Локальная модель отключена. Шаблоны по истории доступны.")}
            </p>
          )}
        </>
      ) : (
        <p className="muted">
          {tr(
            "Нужно минимум два похожих подтверждённых назначения для этой постановки и площадки.",
          )}
        </p>
      )}
    </section>
  );
}
export function SmallModelSettings({
  api,
  settings,
  onSettings,
}: {
  api: Api;
  settings: Obj;
  onSettings: (s: Obj) => void;
}) {
  const [job, setJob] = useState<Obj | null>(null),
    [enabled, setEnabled] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api("/settings/learning")
      .then((r) => {
        if (active) setEnabled(r.enabled);
      })
      .catch(() => {});
    api("/settings/llm/small-model")
      .then((r) => {
        if (active) setJob(r);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (job?.status !== "downloading") return;
    let active = true;
    const timer = setInterval(
      () =>
        api("/settings/llm/small-model")
          .then(async (r) => {
            if (!active) return;
            setJob(r);
            if (r.status === "ready") {
              const cfg = await api("/settings/llm");
              if (active) onSettings(cfg);
            }
          })
          .catch(() => {
            if (active) setError("Не удалось проверить загрузку модели");
          }),
      2000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job?.status]);
  async function download() {
    setBusy(true);
    setError("");
    try {
      await api("/settings/llm", "PUT", settings);
      setJob(await api("/settings/llm/small-model", "POST", {}));
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="small-model-settings">
      <h4>{tr("Малая локальная модель")}</h4>
      <p className="muted">
        {tr(
          "Установите и запустите Ollama на компьютере сервера. Кнопка загрузит малую модель и включит её после успешной загрузки. Интернет нужен только для загрузки.",
        )}
      </p>
      <button
        disabled={
          busy ||
          job?.status === "downloading" ||
          settings.provider !== "Ollama"
        }
        onClick={download}
      >
        {tr("Загрузить малую модель")}
      </button>
      {job?.status === "downloading" && (
        <>
          <progress
            aria-label={tr("Загрузка модели")}
            max={100}
            value={job.progress}
          />
          <span>{job.progress}%</span>
        </>
      )}
      {job?.message && <p role="status">{tr(job.message)}</p>}
      {error && <p role="alert">{tr(error)}</p>}
      <label className="row">
        <input
          type="checkbox"
          checked={enabled}
          onChange={async (e) => {
            const v = e.target.checked;
            try {
              await api("/settings/learning", "PUT", { enabled: v });
              setEnabled(v);
            } catch (e) {
              setError(String((e as Error).message));
            }
          }}
        />
        {tr("Учиться на истории подтверждённых назначений")}
      </label>
      <p className="muted">
        {tr(
          "StageOS запоминает повторяющиеся решения в базе театра. Веса нейросети не дообучаются. Отключение модели не отключает планирование.",
        )}
      </p>
    </div>
  );
}
