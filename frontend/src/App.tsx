import { useState, FormEvent, useRef, useEffect, ChangeEvent, useMemo } from "react";
import ReactECharts from "echarts-for-react";
import Papa from "papaparse";
import { reviveEchartsOption } from "./reviveEchartsOption";
import { getChartSourceCopy } from "./serializeOptionToJs";
import styles from "./App.module.css";
import SearchTest from "./SearchTest";

/** Dev: тот же origin через прокси Vite (/api → backend). Prod: задайте VITE_API_BASE_URL или будет использован дефолт. */
function apiBase(): string {
  const fromEnv = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  if (import.meta.env.DEV) return "";
  return "http://localhost:8000";
}

const API_URL = `${apiBase()}/api/chart`;
const RAG_STATUS_URL = `${apiBase()}/api/rag/status`;
const DB_TEST_URL = `${apiBase()}/api/db/test-query`;

const LLM_MODEL_STORAGE_KEY = "echarts_llm_model";

const LLM_MODEL_OPTIONS = [
  { value: "local_qwen25", label: "Local · qwen2.5" },
  { value: "local_qwen35_9b", label: "Local · qwen3.5 9B" },
  { value: "local_qwen3_coder_30b", label: "Local · qwen3-coder 30B" },
  { value: "openrouter_qwen35_27b", label: "OpenRouter · qwen3.6-27b" },
  { value: "openrouter_gpt4o", label: "OpenRouter · GPT-4o" },
] as const;

type LlmModelValue = (typeof LLM_MODEL_OPTIONS)[number]["value"];

// ── Типы ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chartOption?: object;
  sqlQuery?: string;
}

interface DataContext {
  fileName: string;
  rowCount: number;
  json: string; // компактная JSON-строка, отправляемая на бэкенд
}

interface RagStatus {
  ok: boolean;
  collection_count: number | null;
  error: string | null;
}

type Status = "idle" | "loading" | "success" | "error";

async function runDbTestQuery() {
  console.log("Fetching DB test query…");
  try {
    const res = await fetch(DB_TEST_URL);
    const data = await res.json();
    console.log("DB test query result:", data);
  } catch (err) {
    console.error("DB test query error:", err);
  }
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [page, setPage] = useState<"chat" | "search">("chat");
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [activeChart, setActiveChart] = useState<object | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [dataCtx, setDataCtx] = useState<DataContext | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [llmModel, setLlmModel] = useState<LlmModelValue>(() => {
    try {
      const raw = localStorage.getItem(LLM_MODEL_STORAGE_KEY);
      if (raw && LLM_MODEL_OPTIONS.some((o) => o.value === raw)) {
        return raw as LlmModelValue;
      }
    } catch {
      /* ignore */
    }
    return "local_qwen25";
  });

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const historyEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    historyEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  // Получить статус RAG один раз при монтировании
  useEffect(() => {
    fetch(RAG_STATUS_URL)
      .then((r) => r.json())
      .then((data) => setRagStatus(data as RagStatus))
      .catch(() => setRagStatus({ ok: false, collection_count: null, error: "Backend unreachable" }));
  }, []);

  function handleLlmModelChange(e: ChangeEvent<HTMLSelectElement>) {
    const v = e.target.value as LlmModelValue;
    setLlmModel(v);
    try {
      localStorage.setItem(LLM_MODEL_STORAGE_KEY, v);
    } catch {
      /* ignore */
    }
  }

  // ── Загрузка файла ───────────────────────────────────────────────────────────

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ""; // разрешить повторную загрузку того же файла
    setFileError(null);

    const ext = file.name.split(".").pop()?.toLowerCase();

    if (ext === "json") {
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const parsed = JSON.parse(ev.target?.result as string);
          const rows = Array.isArray(parsed) ? parsed : [parsed];
          setDataCtx({
            fileName: file.name,
            rowCount: rows.length,
            json: JSON.stringify(rows),
          });
        } catch {
          setFileError("Invalid JSON file.");
        }
      };
      reader.readAsText(file);
    } else if (ext === "csv") {
      Papa.parse<Record<string, string>>(file, {
        header: true,
        skipEmptyLines: true,
        complete(results) {
          if (results.errors.length > 0) {
            setFileError(`CSV parse error: ${results.errors[0].message}`);
            return;
          }
          setDataCtx({
            fileName: file.name,
            rowCount: results.data.length,
            json: JSON.stringify(results.data),
          });
        },
        error(err) {
          setFileError(`CSV parse error: ${err.message}`);
        },
      });
    } else {
      setFileError("Only .csv and .json files are supported.");
    }
  }

  // ── Отправка ─────────────────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = message.trim();
    if (!trimmed || status === "loading") return;

    setMessage("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setStatus("loading");
    setErrorMsg("");

    const llmHistory = history.map(({ role, content }) => ({ role, content }));

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
    };
    setHistory((prev) => [...prev, userMsg]);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          history: llmHistory,
          current_chart: activeChart ?? null,
          data_context: dataCtx?.json ?? null,
          llm_model: llmModel,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = (body as { detail?: unknown }).detail;
        if (detail && typeof detail === "object") {
          const d = detail as { message?: string; entity_extraction?: unknown; sql_query?: string; sql_result?: unknown[] };
          if (d.entity_extraction) console.log("1. Entity extraction:", d.entity_extraction);
          if (d.sql_query)         console.log("2. SQL query:", d.sql_query);
          console.log("3. SQL result:", d.sql_result ?? []);
          console.error("4. Error:", d.message ?? `HTTP ${res.status}`);
          throw new Error(d.message ?? `HTTP ${res.status}`);
        }
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }

      const data = (await res.json()) as {
        chart_option: object;
        sql_query?: string;
        sql_result?: unknown[];
        entity_extraction?: unknown;
        rag_chunks?: string[];
      };
      if (data.entity_extraction) console.log("1. Entity extraction:", data.entity_extraction);
      if (data.sql_query)         console.log("2. SQL query:", data.sql_query);
      if (data.sql_result)        console.log("3. SQL result:", data.sql_result);
      if (data.rag_chunks)        console.log("4. RAG chunks:", data.rag_chunks);
      const newChart = data.chart_option;

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "График обновлён.",
        chartOption: newChart,
        sqlQuery: data.sql_query ?? undefined,
      };

      setHistory((prev) => [...prev, assistantMsg]);
      setActiveChart(newChart);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Unknown error");
      setStatus("error");
    }
  }

  const isLoading = status === "loading";

  const chartOptionForRender = useMemo(
    () => (activeChart !== null ? reviveEchartsOption(activeChart) : null),
    [activeChart]
  );

  const chartCopy = useMemo(
    () =>
      activeChart !== null
        ? getChartSourceCopy(activeChart)
        : { text: "", mode: "json" as const },
    [activeChart]
  );

  // ── Рендер ───────────────────────────────────────────────────────────────────

  if (page === "search") {
    return <SearchTest onBack={() => setPage("chat")} />;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerLogo}>📊</span>
        <span className={styles.headerTitle}>ECharts Chatbot</span>

        <RagIndicator status={ragStatus} />

        <button type="button" className={styles.clearBtn} onClick={() => setPage("search")}>
          🔍 Поиск индикаторов
        </button>

        <button type="button" onClick={runDbTestQuery} className={styles.clearBtn}>
          Test DB Query
        </button>

        <div className={styles.headerRight}>
          <label className={styles.modelPicker}>
            <span className={styles.modelPickerLabel}>Model</span>
            <select
              className={styles.modelSelect}
              value={llmModel}
              onChange={handleLlmModelChange}
              title="Select AI model for chart generation"
              disabled={isLoading}
            >
              {LLM_MODEL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          {history.length > 0 && (
            <button
              type="button"
              className={styles.clearBtn}
              onClick={() => {
                setHistory([]);
                setActiveChart(null);
                setStatus("idle");
                setErrorMsg("");
              }}
            >
              Очистить чат
            </button>
          )}
        </div>
      </header>

      {fileError && (
        <div className={styles.fileBanner}>
          ⚠ {fileError}
          <button type="button" className={styles.fileBannerClose} onClick={() => setFileError(null)}>
            ✕
          </button>
        </div>
      )}

      <main className={styles.main}>
        <aside className={styles.leftPanel}>
          <div className={styles.messageList}>
            {history.length === 0 && (
              <div className={styles.emptyChat}>
                <span className={styles.emptyChatIcon}>💬</span>
                <p className={styles.emptyChatText}>
                  {dataCtx
                    ? `«${dataCtx.fileName}» загружен. Опишите нужный график.`
                    : "Опишите график или загрузите данные."}
                </p>
              </div>
            )}

            {history.map((msg) => (
              <div
                key={msg.id}
                className={`${styles.bubble} ${msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant}`}
              >
                <span className={styles.bubbleRole}>{msg.role === "user" ? "You" : "Assistant"}</span>
                <p className={styles.bubbleText}>{msg.content}</p>
                {msg.role === "assistant" && msg.chartOption && (
                  <div className={styles.bubbleActions}>
                    <button
                      type="button"
                      className={styles.viewBtn}
                      onClick={() => setActiveChart(msg.chartOption!)}
                    >
                      Показать график ↗
                    </button>
                    {msg.sqlQuery && (
                      <CopyButton text={msg.sqlQuery} title="Скопировать SQL запрос" label="⎘ SQL" labelCopied="✓ Скопирован" className={styles.viewBtn} />
                    )}
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className={`${styles.bubble} ${styles.bubbleAssistant}`}>
                <span className={styles.bubbleRole}>Assistant</span>
                <div className={styles.typingDots}>
                  <span className={styles.typingDot} />
                  <span className={styles.typingDot} />
                  <span className={styles.typingDot} />
                </div>
              </div>
            )}

            <div ref={historyEndRef} />
          </div>

          {status === "error" && (
            <div className={styles.errorBox}>
              <strong>Error:</strong> {errorMsg}
            </div>
          )}

          {dataCtx && (
            <div className={styles.dataBadgeRow}>
              <div className={styles.dataBadge}>
                <span className={styles.dataBadgeIcon}>📄</span>
                <span className={styles.dataBadgeText}>
                  {dataCtx.fileName} · {dataCtx.rowCount} rows
                </span>
                <button
                  type="button"
                  className={styles.dataClearBtn}
                  onClick={() => setDataCtx(null)}
                  title="Удалить данные"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className={styles.inputRow}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.json"
              className={styles.hiddenInput}
              onChange={handleFileChange}
            />

            <button
              type="button"
              className={`${styles.attachBtn} ${dataCtx ? styles.attachBtnActive : ""}`}
              onClick={() => fileInputRef.current?.click()}
              title="Прикрепить CSV или JSON"
            >
              📎
            </button>

            <textarea
              ref={inputRef}
              value={message}
              rows={2}
              onChange={(e) => {
                setMessage(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as unknown as FormEvent);
                }
              }}
              placeholder={activeChart ? "Изменить график…" : "Опишите график…"}
              className={styles.input}
              disabled={isLoading}
            />
            <button
              type="submit"
              className={`${styles.sendBtn} ${isLoading || !message.trim() ? styles.sendBtnDisabled : ""}`}
              disabled={isLoading || !message.trim()}
              title="Send"
            >
              ➤
            </button>
          </form>
        </aside>

        <section className={styles.rightPanel}>
          {isLoading && activeChart === null && (
            <div className={styles.centeredFill}>
              <Spinner />
              <p className={styles.loadingText}>Генерация графика…</p>
            </div>
          )}

          {activeChart !== null && (
            <div className={styles.chartWrapper}>
              {isLoading && (
                <div className={styles.chartOverlay}>
                  <Spinner />
                  <p className={styles.loadingText}>Обновление…</p>
                </div>
              )}
              <div className={styles.copyBar}>
                <CopyButton
                  text={chartCopy.text}
                  title={
                    chartCopy.mode === "javascript"
                      ? "Будет скопирован JavaScript: _echarts_fn превращаются в функции, в конце chart.setOption(option)"
                      : "Будет скопирован JSON (без _echarts_fn — только данные)"
                  }
                />
              </div>
              <ReactECharts
                option={chartOptionForRender ?? {}}
                className={styles.chartCanvas}
                style={{ height: "100%", minHeight: 0 }}
                notMerge
              />
            </div>
          )}

          {activeChart === null && !isLoading && (
            <div className={styles.centeredFill}>
              <span className={styles.placeholder}>📈</span>
              <p className={styles.placeholderText}>Здесь появится ваш график.</p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

// ── Спиннер ───────────────────────────────────────────────────────────────────

function Spinner() {
  return <div className={styles.spinner} />;
}

// ── Кнопка копирования ────────────────────────────────────────────────────────

function CopyButton({
  text,
  title,
  label = "⎘ Копировать код",
  labelCopied = "✓ Скопировано",
  className,
}: {
  text: string;
  title: string;
  label?: string;
  labelCopied?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={title}
      className={className ?? `${styles.copyBtn} ${copied ? styles.copyBtnCopied : ""}`}
    >
      {copied ? labelCopied : label}
    </button>
  );
}

// ── Индикатор RAG ─────────────────────────────────────────────────────────────

function RagIndicator({ status }: { status: RagStatus | null }) {
  const isActive = status?.ok === true;
  const isLoading = status === null;

  let tooltip = "Проверка статуса RAG…";
  if (!isLoading) {
    if (isActive) {
      tooltip = `RAG активен · ${status!.collection_count ?? "?"} фрагментов проиндексировано`;
    } else {
      tooltip = `RAG недоступен${status!.error ? `: ${status!.error}` : ""}`;
    }
  }

  const dotClass =
    styles.ragDot +
    " " +
    (isLoading ? styles.ragDotLoading : isActive ? styles.ragDotActive : styles.ragDotOff);

  return (
    <div className={styles.ragIndicator} title={tooltip}>
      <span className={dotClass} />
      <span className={styles.ragLabel}>
        {isLoading ? "RAG…" : isActive ? "RAG" : "RAG выкл"}
      </span>
      {isActive && status!.collection_count !== null && (
        <span className={styles.ragCount}>{status!.collection_count}</span>
      )}
    </div>
  );
}
