import { useState, useEffect, FormEvent } from "react";
import styles from "./SearchTest.module.css";

function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "";
  return "http://localhost:8000";
}

const SEARCH_URL = `${apiBase()}/api/search-indicators`;
const STATUS_URL = `${apiBase()}/api/search-indicators/status`;

interface SearchResult {
  id: number;
  name: string;
  score: number;
}

interface CollectionStatus {
  ok: boolean;
  count: number;
  error: string | null;
}

export default function SearchTest({ onBack }: { onBack: () => void }) {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [lastQuery, setLastQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<CollectionStatus | null>(null);

  useEffect(() => {
    fetch(STATUS_URL)
      .then((r) => r.json())
      .then((data) => setStatus(data as CollectionStatus))
      .catch(() => setStatus({ ok: false, count: 0, error: "Backend unreachable" }));
  }, []);

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    setLastQuery(trimmed);

    try {
      const res = await fetch(
        `${SEARCH_URL}?q=${encodeURIComponent(trimmed)}&top_k=${topK}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as SearchResult[];
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function scoreColor(score: number): string {
    if (score >= 0.65) return "#16a34a";
    if (score >= 0.45) return "#d97706";
    return "#dc2626";
  }

  function scoreLabel(score: number): string {
    if (score >= 0.65) return "высокое";
    if (score >= 0.45) return "среднее";
    return "низкое";
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button type="button" onClick={onBack} className={styles.backBtn}>
          ← Назад
        </button>
        <h1 className={styles.title}>Тест поиска индикаторов</h1>
        {status && (
          <div
            className={`${styles.statusBadge} ${status.ok ? styles.statusOk : styles.statusOff}`}
            title={status.error ?? undefined}
          >
            {status.ok
              ? `${status.count} индикаторов проиндексировано`
              : (status.error ?? "Не проиндексировано")}
          </div>
        )}
      </header>

      <div className={styles.body}>
        <form onSubmit={handleSearch} className={styles.searchForm}>
          <textarea
            className={styles.searchInput}
            value={query}
            rows={3}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSearch(e as unknown as FormEvent);
              }
            }}
            placeholder="Введите запрос в свободной форме, например: брошенные поезда, погрузка ДВОСТ, отправление грузов на экспорт..."
            disabled={loading}
          />
          <div className={styles.searchControls}>
            <label className={styles.topKLabel}>
              Результатов:
              <select
                className={styles.topKSelect}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </label>
            <button
              type="submit"
              className={styles.searchBtn}
              disabled={loading || !query.trim()}
            >
              {loading ? "Поиск…" : "Найти"}
            </button>
          </div>
        </form>

        {error && <div className={styles.errorBox}>Ошибка: {error}</div>}

        {results !== null && !error && (
          <div className={styles.results}>
            <div className={styles.resultsHeader}>
              {results.length} результат{results.length === 1 ? "" : results.length < 5 ? "а" : "ов"} для «{lastQuery}»
            </div>
            {results.length === 0 ? (
              <div className={styles.emptyResults}>Ничего не найдено</div>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th className={styles.thRank}>#</th>
                    <th className={styles.thScore}>Релевантность</th>
                    <th className={styles.thId}>ID</th>
                    <th className={styles.thName}>Название индикатора</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => {
                    const color = scoreColor(r.score);
                    return (
                      <tr key={r.id}>
                        <td className={styles.tdRank}>{i + 1}</td>
                        <td className={styles.tdScore}>
                          <span
                            className={styles.scorePill}
                            style={{
                              background: color + "18",
                              color,
                              borderColor: color + "55",
                            }}
                          >
                            {(r.score * 100).toFixed(0)}% · {scoreLabel(r.score)}
                          </span>
                        </td>
                        <td className={styles.tdId}>{r.id}</td>
                        <td className={styles.tdName}>{r.name}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {results === null && !loading && !error && (
          <div className={styles.placeholder}>
            <span>🔍</span>
            <p>Введите запрос, чтобы найти подходящие индикаторы</p>
            {status !== null && !status.ok && (
              <p className={styles.placeholderHint}>
                ⚠ Коллекция не проиндексирована. Запустите из папки{" "}
                <code>backend/</code>:<br />
                <code>python -m scripts.index_indicators</code>
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
