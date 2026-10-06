"""
composer.py

Turns a tool's structured result into natural-language sentences WITHOUT an LLM. Used only when
no LLM provider is configured (NullProvider) -- when a real provider is available, the LLM
phrases the final answer from the same tool result instead (see orchestrator.py). This composer
is driven entirely by the SHAPE of the result and the intent category, not by the literal
question text, so it is not a per-question template: the same "kpis + items list" shape is
rendered identically whether the question was about MED001, Paracetamol, or O+ blood.
"""


def _n(x, nd=1):
    if x is None:
        return "unknown"
    try:
        return f"{float(x):,.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}"
    except (TypeError, ValueError):
        return str(x)


def compose(intent: str, result: dict, label: str = "") -> str:
    if "error" in result:
        if result["error"] == "not_authorized":
            return f"I can't share {result.get('domain', 'that')} information with your current role."
        return f"I couldn't find that information: {result['error']}"

    label = f" for {label}" if label else ""

    if intent in ("inventory",):
        items = result.get("items", [])
        if not items:
            return f"I couldn't find current inventory data{label}."
        if len(items) == 1:
            it = items[0]
            name = it.get("medicine_name") or f"{it.get('blood_group','')}{'+' if it.get('rh_type')=='Positive' else '-'} {it.get('blood_component','')}"
            return (f"{name.strip()} currently has {_n(it['closing_stock'])} units available, "
                    f"which is classified as {it['stock_status']} stock.")
        counts = {}
        for it in items:
            counts[it["stock_status"]] = counts.get(it["stock_status"], 0) + 1
        parts = ", ".join(f"{v} {k}" for k, v in counts.items())
        return f"Across {len(items)} entries{label}, stock status breaks down as: {parts}."

    if intent == "low_stock_items":
        low, crit = result.get("low", []), result.get("critical", [])
        if not low and not crit:
            return "Nothing is currently at Low or Critical stock."
        names = [i.get("medicine_name") or f"{i.get('blood_group')}{'+' if i.get('rh_type')=='Positive' else '-'}"
                for i in (crit + low)[:8]]
        return (f"{len(crit)} item(s) are Critical and {len(low)} are Low. "
                f"Needing attention first: {', '.join(names)}.")

    if intent == "near_expiry_items":
        items = result.get("items", [])
        if not items:
            return "Nothing is currently near expiry."
        total_units = sum(i.get("units_remaining", 0) for i in items)
        return (f"{len(items)} batch(es) are near expiry, totaling {_n(total_units)} units. "
                f"The soonest expires in {items[0]['days_remaining']} day(s).")

    if intent == "shortage_risk":
        items = result.get("items", [])
        if not result.get("available", True):
            return result.get("message", "No forecast is available yet to assess shortage risk.")
        if not items:
            return "No potential shortages are indicated by the current forecast."
        return "Potential shortage risk: " + "; ".join(i["why"] for i in items[:5])

    if intent in ("future_forecast",):
        if not result.get("available", True):
            return result.get("message", "No forecast has been generated yet.")
        run = result.get("run", {})
        items = result.get("items", [])
        if not items:
            return f"I don't have forecast rows{label} for that filter."
        total = sum(i["predicted_demand"] for i in items)
        trend = result.get("trend", {}).get("direction")
        trend_txt = f" The forecast trend is {trend.lower()}." if trend else ""
        return (f"The {run.get('model_name', 'selected')} model projects about {_n(total)} units of demand{label} "
                f"over the next {len(items)} day(s) shown (model-generated forecast, not historical).{trend_txt}")

    if intent == "backtest":
        o = result.get("overall", {})
        if not o.get("n"):
            return f"I don't have backtest results{label} for that filter."
        return (f"Over {o['n']} historical predictions{label}, the model's RMSE was {_n(o['rmse'],2)}, "
                f"MAE was {_n(o['mae'],2)}, and R² was {_n(o['r2'],3)}. This is a historical backtest, not a future forecast.")

    if intent == "model_comparison":
        items = result.get("items", result.get("items"))
        selected = result.get("selected_model")
        if not items:
            return "No model comparison data is available."
        return (f"The {selected} model is selected (lowest RMSE: "
                f"{next((i['rmse'] for i in items if i['model_name']==selected), None)}). "
                f"Compared models: " + ", ".join(f"{i['model_name']} (RMSE {_n(i['rmse'],2)})" for i in items) + ".")

    if intent == "explain_metric":
        return result.get("definition", "I don't have a definition for that metric.")

    if intent in ("trend", "growth"):
        items = result.get("items", [])
        overall = result.get("overall")
        if overall:
            return (f"Overall, demand went from {_n(overall['previous_units_requested'])} to "
                    f"{_n(overall['current_units_requested'])} units ({overall['direction']}, "
                    f"{_n(overall['change_percent'],1)}% change).")
        if not items:
            return f"I don't have enough history to compute a trend{label}."
        counts = {}
        for it in items:
            key = it.get("trend_direction") or it.get("direction")
            counts[key] = counts.get(key, 0) + 1
        return "Trend breakdown: " + ", ".join(f"{v} {k}" for k, v in counts.items() if k)

    if intent == "movement_classification":
        items = result.get("items", [])
        counts = result.get("counts", {})
        return "Movement classification: " + ", ".join(f"{v} {k}" for k, v in counts.items()) + (
            f" (e.g. {items[0].get('medicine_name') or items[0].get('blood_group')})" if items else "")

    if intent == "expiry":
        items = result.get("items", [])
        if not items:
            return f"No batches matched that expiry filter{label}."
        return f"{result.get('total', len(items))} batch(es) match that expiry status{label}."

    if intent == "alerts":
        items = result.get("items", [])
        if not items:
            return f"No active alerts{label}."
        return (f"{result.get('total', len(items))} alert(s){label}. Most pressing: "
                f"{items[0]['alert_type']} ({items[0]['severity']}) - {items[0]['reason']}")

    if intent in ("recommendations", "explain_recommendation"):
        items = result.get("items", [])
        if not items:
            return f"No active recommendations{label}."
        it = items[0]
        return f"{it.get('recommendation_type')}: {it.get('why')}"

    if intent in ("demand", "supply"):
        items = result.get("items", [])
        if not items:
            return f"I couldn't find {intent} data{label} for that period."
        metric = "units_requested" if intent == "demand" else "donation_volume"
        total = sum(i.get(metric, 0) or 0 for i in items)
        return f"Total {intent}{label} across {len(items)} period(s) was {_n(total)} units."

    if intent == "supply_vs_demand":
        items = result.get("items", [])
        if not items:
            return "No supply/demand data is available for that range."
        parts = []
        for i in items[:4]:
            if i["total_demand_requested"] is not None and i["total_supply_donation_volume"] is not None:
                parts.append(f"{i['blood_type']}: {_n(i['total_supply_donation_volume'])} supplied vs "
                            f"{_n(i['total_demand_requested'])} requested")
        return ("Supply vs demand by blood type: " + "; ".join(parts) +
                f". {result.get('limitation', '')}")

    if intent == "top_demand_items":
        items = result.get("highest", [])
        if not items:
            return "I couldn't rank demand for that filter."
        names = [i.get("medicine_name") or f"{i.get('blood_group')}{'+' if i.get('rh_type')=='Positive' else '-'}"
                for i in items[:5]]
        return "Highest demand: " + ", ".join(names) + "."

    if intent.endswith("_report"):
        return f"Report generated with {result.get('row_count', 0)} row(s). Summary: {result.get('summary')}"

    return "Here's what I found: " + str(result)[:400]
