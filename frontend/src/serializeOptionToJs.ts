/**
 * Преобразовать JSON-опцию из API в готовый к вставке JavaScript-сниппет.
 * Объекты `{ "_echarts_fn": "(params) => ..." }` превращаются в настоящие функциональные выражения.
 */

const IDENT_RE = /^[a-zA-Z_$][a-zA-Z0-9_$]*$/;

function jsKey(k: string): string {
  return IDENT_RE.test(k) ? k : JSON.stringify(k);
}

function toJsLiteral(value: unknown, depth: number): string {
  const ind = "  ".repeat(depth);

  if (value === null) return "null";
  const t = typeof value;
  if (t === "boolean" || t === "number") return String(value);
  if (t === "string") return JSON.stringify(value);

  if (Array.isArray(value)) {
    if (value.length === 0) return "[]";
    const inner = value
      .map((v) => `${ind}  ${toJsLiteral(v, depth + 1)}`)
      .join(",\n");
    return `[\n${inner}\n${ind}]`;
  }

  if (t === "object") {
    const o = value as Record<string, unknown>;
    const keys = Object.keys(o);
    if (keys.length === 1 && typeof o._echarts_fn === "string") {
      return o._echarts_fn.trim();
    }
    if (keys.length === 0) return "{}";
    const inner = keys
      .map((k) => `${ind}  ${jsKey(k)}: ${toJsLiteral(o[k], depth + 1)}`)
      .join(",\n");
    return `{\n${inner}\n${ind}}`;
  }

  return "undefined";
}

/** Полный сниппет: `const option = { ... };` и опциональная строка setOption. */
export function serializeEchartsOptionToJs(option: object): string {
  const body = toJsLiteral(option, 0);
  return `const option = ${body};\n\nchart.setOption(option);\n`;
}

/** True, если *value* содержит `{ "_echarts_fn": "..." }` где угодно (рекурсивно). */
export function optionHasEchartsCallbacks(value: unknown): boolean {
  if (value === null || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some(optionHasEchartsCallbacks);
  const o = value as Record<string, unknown>;
  const keys = Object.keys(o);
  if (keys.length === 1 && typeof o._echarts_fn === "string") return true;
  return Object.values(o).some(optionHasEchartsCallbacks);
}

/**
 * Что поместить в буфер обмена: красивый JSON если нет колбэков, иначе JS с настоящими функциями.
 */
export function getChartSourceCopy(option: object): {
  text: string;
  mode: "json" | "javascript";
} {
  if (optionHasEchartsCallbacks(option)) {
    return { text: serializeEchartsOptionToJs(option), mode: "javascript" };
  }
  return { text: JSON.stringify(option, null, 2), mode: "json" };
}
