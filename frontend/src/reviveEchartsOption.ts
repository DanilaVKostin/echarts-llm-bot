/**
 * Опции ECharts из JSON не могут содержать настоящие функции. LLM может кодировать
 * колбэки как `{ "_echarts_fn": "(params) => { ... }" }` (только один ключ).
 * Этот код обходит дерево опций и заменяет такие объекты на вызываемые функции,
 * созданные через `new Function`, чтобы подсказки, метки и т.д. работали как в обычных JS-конфигах.
 *
 * Безопасность: выполняется только код, явно помеченный как `_echarts_fn` от модели.
 */

const FN_KEY = "_echarts_fn";

export function reviveEchartsOption<T>(input: T): T {
  if (input === null || typeof input !== "object") {
    return input;
  }

  if (Array.isArray(input)) {
    return input.map((item) => reviveEchartsOption(item)) as unknown as T;
  }

  const o = input as Record<string, unknown>;

  if (Object.keys(o).length === 1 && typeof o[FN_KEY] === "string") {
    const code = (o[FN_KEY] as string).trim();
    try {
      // eslint-disable-next-line @typescript-eslint/no-implied-eval, no-new-func
      const factory = new Function(`return (${code})`);
      const fn = factory();
      return (typeof fn === "function" ? fn : input) as T;
    } catch {
      return input;
    }
  }

  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) {
    out[k] = reviveEchartsOption(v);
  }
  return out as T;
}
