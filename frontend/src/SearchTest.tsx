import { useState, useEffect, FormEvent } from "react";
import styles from "./SearchTest.module.css";

function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "";
  return "http://localhost:8000";
}

const SEARCH_URL = `${apiBase()}/api/search-indicators`;
const SMART_URL  = `${apiBase()}/api/search-indicators/smart`;
const STATUS_URL = `${apiBase()}/api/search-indicators/status`;

const TABLE_LABELS: Record<string, string> = {
  hcode:       "Показатели",
  org:         "Организации",
  metric_type: "Типы метрики",
  val_type:    "Типы значений",
  date_type:   "Типы периода",
};

const TABLE_ORDER = ["hcode", "org", "metric_type", "val_type", "date_type"];

const LLM_MODEL_OPTIONS = [
  { value: "local_qwen25",              label: "Local · qwen2.5" },
  { value: "local_qwen35_9b",           label: "Local · qwen3.5 9B" },
  { value: "local_qwen3_coder_30b",     label: "Local · qwen3-coder 30B" },
  { value: "openrouter_qwen35_27b",     label: "OpenRouter · qwen3.6-27b" },
  { value: "openrouter_gpt4o",          label: "OpenRouter · GPT-4o" },
  { value: "openrouter_gemini_flash",   label: "OpenRouter · Gemini 2.5 Flash" },
  { value: "openrouter_gemini_flash_lite", label: "OpenRouter · Gemini 2.5 Flash Lite" },
  { value: "openrouter_deepseek_v3",    label: "OpenRouter · DeepSeek V3.2" },
] as const;

type LlmModelValue = (typeof LLM_MODEL_OPTIONS)[number]["value"];

function countSuffix(n: number): string {
  if (n === 1) return "";
  if (n < 5) return "а";
  return "ов";
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

interface SearchResult {
  table: string;
  id: string;
  name: string;
  score: number;
  matched_term?: string;
}

interface CollectionStatus {
  ok: boolean;
  count: number;
  error: string | null;
}

interface SearchTestProps {
  readonly onBack: () => void;
}

type GroupedResults = Record<string, SearchResult[]>;
type SearchMode = "direct" | "smart";

export default function SearchTest({ onBack }: SearchTestProps) {
  const [query, setQuery]       = useState("");
  const [topK, setTopK]         = useState(10);
  const [mode, setMode]         = useState<SearchMode>("direct");
  const [llmModel, setLlmModel] = useState<LlmModelValue>("local_qwen25");
  const [grouped, setGrouped]   = useState<GroupedResults | null>(null);
  const [extractedTerms, setExtractedTerms] = useState<Record<string, string[]> | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [lastQuery, setLastQuery]   = useState("");
  const [expanded, setExpanded]     = useState<Record<string, boolean>>({});
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [status, setStatus]     = useState<CollectionStatus | null>(null);

  useEffect(() => {
    fetch(STATUS_URL)
      .then((r) => r.json())
      .then((data) => setStatus(data as CollectionStatus))
      .catch(() => setStatus({ ok: false, count: 0, error: "Backend unreachable" }));
  }, []);

  function groupAndSetResults(data: SearchResult[]) {
    const groups: GroupedResults = {};
    for (const item of data) {
      if (!groups[item.table]) groups[item.table] = [];
      groups[item.table].push(item);
    }
    setGrouped(groups);
    setTotalCount(Object.values(groups).reduce((s, g) => s + g.length, 0));
    const first = TABLE_ORDER.find((t) => (groups[t]?.length ?? 0) > 0);
    if (first) setExpanded({ [first]: true });
  }

  async function handleSearch(e?: FormEvent) {
    e?.preventDefault();
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    setLastQuery(trimmed);
    setExtractedTerms(null);

    try {
      if (mode === "direct") {
        const res = await fetch(`${SEARCH_URL}?q=${encodeURIComponent(trimmed)}&top_k=${topK}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        groupAndSetResults((await res.json()) as SearchResult[]);
      } else {
        const res = await fetch(SMART_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ q: trimmed, top_k: topK, llm_model: llmModel }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
        }
        const data = (await res.json()) as { results: SearchResult[]; extracted_terms: Record<string, string[]> };
        setExtractedTerms(data.extracted_terms);
        groupAndSetResults(data.results);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  function toggleTable(key: string) {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function searchBtnLabel(): string {
    if (!loading) return "Найти";
    return mode === "smart" ? "Извлечение сущностей…" : "Поиск…";
  }

  const tablesWithResults = grouped
    ? TABLE_ORDER.filter((t) => (grouped[t]?.length ?? 0) > 0)
    : [];

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
                void handleSearch();
              }
            }}
            placeholder="Введите запрос в свободной форме, например: погрузка грузов в вагонах по месяцам 2024 на Северной дороге, факт и план"
            disabled={loading}
          />

          <div className={styles.modeRow}>
            <div className={styles.modeToggle}>
              <button
                type="button"
                className={`${styles.modeBtn} ${mode === "direct" ? styles.modeBtnActive : ""}`}
                onClick={() => setMode("direct")}
              >
                Прямой поиск
              </button>
              <button
                type="button"
                className={`${styles.modeBtn} ${mode === "smart" ? styles.modeBtnActive : ""}`}
                onClick={() => setMode("smart")}
              >
                Умный поиск (LLM)
              </button>
            </div>

            {mode === "smart" && (
              <select
                className={styles.modelSelect}
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value as LlmModelValue)}
                disabled={loading}
              >
                {LLM_MODEL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            )}
          </div>

          <div className={styles.searchControls}>
            <label className={styles.topKLabel}>
              {"На справочник: "}
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
              {searchBtnLabel()}
            </button>
          </div>
        </form>

        {error && <div className={styles.errorBox}>Ошибка: {error}</div>}

        {extractedTerms && (
          <div className={styles.extractedBox}>
            <span className={styles.extractedLabel}>LLM извлёк:</span>
            {TABLE_ORDER.map((key) => {
              const terms = extractedTerms[key];
              if (!terms || terms.length === 0) return null;
              return (
                <span key={key} className={styles.extractedGroup}>
                  <span className={styles.extractedTableName}>{TABLE_LABELS[key]}:</span>
                  {terms.map((t) => (
                    <span key={t} className={styles.termTag}>{t}</span>
                  ))}
                </span>
              );
            })}
          </div>
        )}

        {grouped !== null && !error && (
          <>
            <div className={styles.resultsHeader}>
              {totalCount} результат{countSuffix(totalCount)} для «{lastQuery}»
            </div>

            {tablesWithResults.length === 0 ? (
              <div className={styles.emptyResults}>Ничего не найдено</div>
            ) : (
              <div className={styles.accordion}>
                {tablesWithResults.map((tableKey, idx) => {
                  const items = grouped[tableKey];
                  const label = TABLE_LABELS[tableKey] ?? tableKey;
                  const isOpen = expanded[tableKey] ?? false;
                  const isLast = idx === tablesWithResults.length - 1;
                  return (
                    <div
                      key={tableKey}
                      className={`${styles.accordionItem} ${isLast ? styles.accordionItemLast : ""}`}
                    >
                      <button
                        type="button"
                        className={styles.accordionHeader}
                        onClick={() => toggleTable(tableKey)}
                      >
                        <span className={`${styles.accordionChevron} ${isOpen ? styles.accordionChevronOpen : ""}`}>
                          ›
                        </span>
                        <span className={styles.accordionTitle}>{label}</span>
                        <span className={styles.accordionCount}>{items.length}</span>
                      </button>

                      {isOpen && (
                        <div className={styles.accordionBody}>
                          <table className={styles.table}>
                            <thead>
                              <tr>
                                <th className={styles.thRank}>#</th>
                                <th className={styles.thScore}>Релевантность</th>
                                <th className={styles.thId}>ID</th>
                                <th className={styles.thName}>Название</th>
                                {mode === "smart" && <th className={styles.thTerm}>Термин</th>}
                              </tr>
                            </thead>
                            <tbody>
                              {items.map((r, i) => {
                                const color = scoreColor(r.score);
                                return (
                                  <tr key={`${r.table}__${r.id}`}>
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
                                    {mode === "smart" && (
                                      <td className={styles.tdTerm}>{r.matched_term ?? ""}</td>
                                    )}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {grouped === null && !loading && !error && (
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
