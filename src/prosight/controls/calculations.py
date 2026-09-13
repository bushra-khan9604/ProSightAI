"""Pure calculation services. Dates are inclusive; FS successors start next workday."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, timedelta
from math import isfinite


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("A finite number is required")
    result = float(value)
    if not isfinite(result):
        raise ValueError("A finite number is required")
    return result


class Calendar:
    def __init__(self, working_days="Mon,Tue,Wed,Thu,Fri,Sat", exceptions="None"):
        names = {name: i for i, name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}
        if working_days == "Monday-Saturday":
            working_days = "Mon,Tue,Wed,Thu,Fri,Sat"
        tokens = working_days.replace(";", ",").split(",")
        try:
            self.days = {names[t.strip().lower()[:3]] for t in tokens}
        except KeyError as exc:
            raise ValueError("Unsupported working week") from exc
        self.exceptions = set() if not exceptions or str(exceptions).lower().startswith("none") or str(exceptions).lower() == "no holidays assumed" else {
            date.fromisoformat(t.strip()) for t in str(exceptions).split(",")}

    def working(self, day):
        return day.weekday() in self.days and day not in self.exceptions

    def roll(self, day, direction=1):
        for _ in range(3660):
            if self.working(day):
                return day
            day += timedelta(days=direction)
        raise ValueError("Calendar contains no reachable working day")

    def shift(self, day, count):
        if int(count) != count or abs(count) > 20000:
            raise ValueError("Working-day offsets must be bounded integers")
        direction = 1 if count >= 0 else -1
        day = self.roll(day, direction)
        for _ in range(abs(int(count))):
            day = self.roll(day + timedelta(days=direction), direction)
        return day

    def distance(self, start, finish):
        if finish < start:
            return -self.distance(finish, start)
        return sum(self.working(start + timedelta(days=i)) for i in range(1, (finish-start).days+1))


def schedule(activities, relationships, calendars, start, *, forecast=False, reductions=None):
    """Calculate a DAG in calendar dates, preserving zero-duration boundary milestones."""
    if len(activities) > 10000:
        raise ValueError("Schedule exceeds 10,000 activities")
    nodes = {a["activity_id"]: a for a in activities}
    if len(nodes) != len(activities):
        raise ValueError("Duplicate activity IDs")
    if not nodes:
        return {"activities": [], "finish": None, "critical_path": []}
    cals = {c["calendar_id"]: Calendar(c["working_days"], c.get("exceptions")) for c in calendars}
    if not cals:
        raise ValueError("Schedule calendar is missing")
    default = next(iter(cals))
    incoming, outgoing = defaultdict(list), defaultdict(list)
    durations = {}
    for key, activity in nodes.items():
        if activity.get("calendar_id", default) not in cals:
            raise ValueError(f"Unknown calendar for {key}")
        d = number(activity["duration_wd"]) - number((reductions or {}).get(key, 0))
        if d < 0 or int(d) != d:
            raise ValueError(f"Invalid duration for {key}")
        durations[key] = int(d)
    for rel in relationships:
        if rel["type"] != "FS":
            raise ValueError("Only finish-to-start relationships are supported")
        p, s = rel["predecessor_id"], rel["successor_id"]
        if p not in nodes or s not in nodes:
            raise ValueError(f"Broken relationship {p} → {s}")
        lag = number(rel.get("forecast_lag_wd" if forecast else "baseline_lag_wd", 0))
        if int(lag) != lag or abs(lag) > 20000:
            raise ValueError("Relationship lag must be a bounded integer")
        incoming[s].append((p, int(lag)))
        outgoing[p].append((s, int(lag)))
    degree = {k: len(incoming[k]) for k in nodes}
    queue = deque(k for k in nodes if degree[k] == 0)
    order, early = [], {}
    origin = date.fromisoformat(start)
    while queue:
        key = queue.popleft()
        cal = cals[nodes[key].get("calendar_id", default)]
        begins = cal.roll(origin)
        for pred, lag in incoming[key]:
            offset = lag + (1 if durations[pred] and durations[key] else 0)
            begins = max(begins, cal.shift(early[pred][1], offset))
        early[key] = (begins, cal.shift(begins, max(0, durations[key]-1)))
        order.append(key)
        for successor, _ in outgoing[key]:
            degree[successor] -= 1
            if degree[successor] == 0:
                queue.append(successor)
    if len(order) != len(nodes):
        raise ValueError("Schedule contains a cycle")
    finish = max(v[1] for v in early.values())
    late = {}
    for key in reversed(order):
        cal = cals[nodes[key].get("calendar_id", default)]
        ends = cal.roll(finish, -1)
        for successor, lag in outgoing[key]:
            successor_cal = cals[nodes[successor].get("calendar_id", default)]
            offset = lag + (1 if durations[key] and durations[successor] else 0)
            ends = min(ends, cal.roll(successor_cal.shift(late[successor][0], -offset), -1))
        late[key] = (cal.shift(ends, -max(0, durations[key]-1)), ends)
    rows = []
    for key in order:
        cal = cals[nodes[key].get("calendar_id", default)]
        rows.append({"activity_id": key, "start": early[key][0].isoformat(), "finish": early[key][1].isoformat(),
                     "late_start": late[key][0].isoformat(), "late_finish": late[key][1].isoformat(),
                     "float_wd": cal.distance(early[key][0], late[key][0])})
    return {"activities": rows, "finish": finish.isoformat(),
            "critical_path": [r["activity_id"] for r in rows if r["float_wd"] == 0]}


def evm(budgets, periods, measurements, costs, cutoff, *, future=False):
    """EV uses measured quantities, never uploaded EV/CPI/SPI fields."""
    by_activity = {b["activity_id"]: b for b in budgets}
    bac = sum(number(b["budget_usd"]) for b in budgets)
    pv = sum(number(p["planned_value_usd"]) for p in periods if p["period_end"] <= cutoff)
    if future:
        return dict(bac_usd=bac, pv_usd=pv, ev_usd=None, ac_usd=None, cpi=None, spi=None, eac_usd=None)
    qty = defaultdict(float)
    for m in measurements:
        if m["period_end"] <= cutoff:
            b = by_activity.get(m["activity_id"])
            if not b or b["unit"] != m["unit"]:
                raise ValueError("Measurement budget/unit mismatch")
            qty[m["activity_id"]] += number(m["quantity_this_period"])
    ev = 0.0
    for key, quantity in qty.items():
        b = by_activity[key]
        total = number(b["quantity"])
        if total <= 0 or quantity < 0 or quantity > total + 0.001:
            raise ValueError("Measured quantity is outside its approved budget")
        ev += min(1, quantity/total)*number(b["budget_usd"])
    ac = sum(number(c["cost_usd"]) for c in costs if c["date"] <= cutoff)
    cpi, spi = (ev/ac if ac else None), (ev/pv if pv else None)
    return dict(bac_usd=bac, pv_usd=pv, ev_usd=ev, ac_usd=ac, cpi=cpi, spi=spi,
                cv_usd=ev-ac, sv_usd=ev-pv, eac_usd=bac/cpi if cpi else None,
                forecast_basis="EAC = BAC / CPI; assumes current cost efficiency continues")


def resource_conflicts(demand, capacity):
    """Sweep inclusive demand/capacity intervals; report overlaps without daily expansion."""
    resources = {r["resource_id"] for r in demand}
    result = []
    for resource in sorted(resources):
        ds = [r for r in demand if r["resource_id"] == resource]
        cs = [r for r in capacity if r["resource_id"] == resource]
        boundaries = sorted({date.fromisoformat(r[k]) + timedelta(days=k=="finish_date")
                             for r in ds+cs for k in ("start_date", "finish_date")})
        for start, stop in zip(boundaries, boundaries[1:]):
            day = start.isoformat()
            active = [r for r in ds if r["start_date"] <= day <= r["finish_date"]]
            available = [r for r in cs if r["start_date"] <= day <= r["finish_date"]]
            wanted = sum(number(r["requested_teams"]) for r in active)
            supply = sum(number(r["available_teams"]) for r in available) if available else None
            if wanted and (supply is None or wanted > supply):
                result.append(dict(resource_id=resource, start_date=day, finish_date=(stop-timedelta(days=1)).isoformat(),
                                   demand=wanted, capacity=supply, shortage=wanted-supply if supply is not None else None,
                                   projects=sorted({r.get("project_code", "") for r in active})))
    return result


def cash_flow(billing, costs, supplier_days=30):
    """Separate received/planned cash from accrued costs; retention remains unpaid until a release record."""
    events = defaultdict(lambda: {"receipts_usd": 0.0, "payments_usd": 0.0})
    for row in billing:
        when = row.get("paid_date") or row.get("due_date")
        if when:
            events[when]["receipts_usd"] += number(row["net_due_usd"])
    for row in costs:
        when = (date.fromisoformat(row["date"])+timedelta(days=int(supplier_days))).isoformat()
        events[when]["payments_usd"] += number(row["cost_usd"])
    cash, minimum, rows = 0.0, 0.0, []
    for day, values in sorted(events.items()):
        opening = cash
        cash += values["receipts_usd"]-values["payments_usd"]
        minimum = min(minimum, cash)
        rows.append(dict(date=day, opening_cash_usd=opening, **values, closing_cash_usd=cash))
    return {"periods": rows, "funding_requirement_usd": -minimum,
            "basis": "Paid dates when supplied; otherwise contractual due dates. Cost payments use the stated supplier lag."}


def remaining_cost_forecast(tables, cutoff, remaining_cost):
    """Phase an explicitly assumed ETC across remaining forecast work, by unearned budget."""
    quantities=defaultdict(float)
    for m in tables.get('Measurements',[]):
        if m['period_end']<=cutoff:quantities[m['activity_id']]+=number(m['quantity_this_period'])
    weights=[]
    for a in tables.get('Schedule',[]):
        if a.get('actual_finish') or not a.get('remaining_duration_wd'):continue
        fraction=max(0,1-quantities[a['activity_id']]/a['quantity']) if a['quantity'] else 0
        weights.append((a,number(a['budget_usd'])*fraction))
    total=sum(weight for _,weight in weights)
    if not total:return []
    calendars={c['calendar_id']:Calendar(c['working_days'],c.get('exceptions')) for c in tables['Calendars']}
    result=[]
    for a,weight in weights:
        cal=calendars[a['calendar_id']]
        start=cal.roll(max(date.fromisoformat(a['forecast_start']),date.fromisoformat(cutoff)+timedelta(days=1)))
        end=date.fromisoformat(a['forecast_finish'])
        if end<start:raise ValueError('Unfinished work has no forecast duration after the reporting date')
        days=[start+timedelta(days=i) for i in range((end-start).days+1) if cal.working(start+timedelta(days=i))]
        periods=defaultdict(int)
        for day in days:
            month_end=(day.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
            periods[min(month_end,end).isoformat()]+=1
        result.extend({'date':period,'cost_usd':remaining_cost*weight/total*count/len(days),'kind':'ETC forecast'} for period,count in periods.items())
    return result


def risk_exposure(risks):
    rows = []
    for risk in risks:
        probability = number(risk["probability"])
        if not 0 <= probability <= 1:
            raise ValueError("Risk probability must be between zero and one")
        rows.append({**risk, "expected_cost_usd": probability*number(risk["impact_cost_usd"])})
    return {"risks": rows, "open_expected_cost_usd": sum(r["expected_cost_usd"] for r in rows if r.get("status", "").lower() not in {"closed", "resolved"})}
