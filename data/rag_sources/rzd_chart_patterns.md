# RZD Railway Data — ECharts Patterns

## Data structure from DB queries

Queries return rows with these typical columns:
- `date` — ISO date string (x-axis for time series)
- `value` — numeric indicator value (y-axis)
- `indicator` / `hcode_name` — indicator name (series name or category label)
- `unit` / `hcode_unit_name` — unit of measurement (e.g. "тыс. тонн/сутки", "км", "%")
- `org` — railway name (e.g. "Дальневосточная", "СЕТЬ")
- `metric` — metric type id: '1'=Факт, '2'=План (use for multi-series fact vs plan charts)

## Time series: monthly indicator dynamics (line chart)

Data shape: `[{ date: "2023-01-01", value: 3.05 }, ...]`

```json
{
  "title": { "text": "Показатель 00001, Дальневосточная, 2023" },
  "tooltip": { "trigger": "axis" },
  "legend": {},
  "xAxis": { "type": "category", "data": ["2023-01", "2023-02", "..."] },
  "yAxis": { "type": "value", "name": "тыс. тонн/сутки" },
  "series": [{ "name": "Факт", "type": "line", "data": [3.05, 3.12, "..."] }]
}
```

## Fact vs Plan comparison (two-series line chart)

When `metric` column contains '1' (Факт) and '2' (План), split into two series.

```json
{
  "series": [
    { "name": "Факт", "type": "line", "data": ["..."] },
    { "name": "План", "type": "line", "data": ["..."], "lineStyle": { "type": "dashed" } }
  ]
}
```

## Cross-road bar chart (one date, multiple orgs)

Data shape: `[{ org: "Дальневосточная", value: 3.05 }, ...]`

```json
{
  "xAxis": { "type": "category", "data": ["Дальневосточная", "Забайкальская", "..."], "axisLabel": { "rotate": 30 } },
  "yAxis": { "type": "value" },
  "series": [{ "type": "bar", "data": [3.05, 4.2, "..."] }]
}
```

## Top-N indicators bar chart

Data shape: `[{ indicator: "...", unit: "...", value: 3.05 }, ...]` (already ordered DESC)

Use horizontal bar for long indicator names:
```json
{
  "xAxis": { "type": "value" },
  "yAxis": { "type": "category", "data": ["Indicator A", "Indicator B", "..."] },
  "series": [{ "type": "bar", "data": [3.05, 2.8, "..."] }]
}
```

## Tooltip with unit

Always include the unit in the tooltip:
```json
{
  "tooltip": {
    "trigger": "axis",
    "formatter": {
      "_echarts_fn": "(params) => { const p = params[0]; return p.axisValue + '<br/>' + p.seriesName + ': ' + p.value + ' тыс. тонн/сутки'; }"
    }
  }
}
```

## Date formatting on xAxis

For monthly data, show only year-month:
```json
{
  "xAxis": {
    "type": "category",
    "axisLabel": {
      "formatter": { "_echarts_fn": "(val) => val.slice(0, 7)" }
    }
  }
}
```

## Metric type labels (metric column values)

When the data has a `metric` column, map it to human-readable names:
- '1'  → "Факт"
- '2'  → "План"
- '11' → "Директивный план"
- '18' → "План с корректировкой"
- '7'  → "Ожидаемый факт"
