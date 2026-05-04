# Line chart: category axis + extra fields in tooltip

When `xAxis.type` is `"category"` and `xAxis.data` lists months or labels, each line point
that must show **more than one column** (e.g. revenue + orders + avg_order_value) should be
an **object** in `series[].data`, not `[index, value]` pairs.

## Correct `series.data` shape

Use the numeric field that is drawn on the Y axis as `"value"` (ECharts convention for
custom datum objects). Add every other column as extra keys for the tooltip:

```json
"data": [
  { "value": 12450, "orders": 166, "avg_order_value": 75.0 },
  { "value": 13820, "orders": 172, "avg_order_value": 80.3 }
]
```

Wrong for tooltips that need extra keys:

```json
"data": [[0, 12450], [1, 13820]]
```

Those arrays have no `orders` or `avg_order_value` on `params[0].data`.

## `tooltip.trigger: "axis"` formatter

With axis trigger, ECharts passes an **array** to `formatter`, one entry per series at that
category. Use `params[0]` for the first series and read `p.data` for the datum object.

Encode the function with `_echarts_fn` (single expression returning a function):

```json
"tooltip": {
  "trigger": "axis",
  "formatter": {
    "_echarts_fn": "(params) => { const p = params[0]; const d = p.data; return p.axisValue + '<br/>Revenue: ' + d.value + '<br/>Orders: ' + d.orders + '<br/>Avg: ' + d.avg_order_value; }"
  }
}
```

Do **not** use `params.seriesName` / `params.value[1]` / `params.data` without `params[0]`
when `trigger` is `"axis"` — that produces `undefined` in the UI.
