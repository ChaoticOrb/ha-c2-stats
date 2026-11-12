/*
 * Concept2 Logbook card for Home Assistant.
 *
 * Bundled with the concept2_logbook integration, which loads it on every
 * dashboard. No build step and no external dependencies: a plain web
 * component that themes itself from Home Assistant's CSS variables.
 *
 * Unofficial. Not made, endorsed or supported by Concept2, Inc.
 */

const CARD_VERSION = "0.5.1";
const DOMAIN = "concept2_logbook";

const MACHINE_NAMES = {
  rower: "RowErg",
  skierg: "SkiErg",
  bike: "BikeErg",
  dynamic: "Dynamic RowErg",
  slides: "RowErg on slides",
  paddle: "Paddle adapter",
  water: "On water",
  snow: "On snow",
  rollerski: "Rollerski",
  multierg: "MultiErg",
};

const DEFAULTS = {
  title: "Rowing",
  chart_days: 28,
  show_totals: true,
  show_chart: true,
  show_streaks: true,
  show_pbs: true,
};

const STATS_REFRESH_MS = 30 * 60 * 1000;

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

const dayKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** Concept2 seasons run May 1 to April 30. */
const seasonBounds = (now) => {
  const year = now.getMonth() >= 4 ? now.getFullYear() : now.getFullYear() - 1;
  return [new Date(year, 4, 1), new Date(year + 1, 4, 1)];
};

const weekBounds = (now) => {
  const start = startOfDay(now);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // Monday
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return [start, end];
};

/** Find this integration's entities for one device, keyed by translation key. */
function findEntities(hass, deviceId) {
  const entries = Object.values(hass.entities || {}).filter(
    (e) => e.platform === DOMAIN && (!deviceId || e.device_id === deviceId),
  );
  const byKey = {};
  const pbs = [];
  for (const entry of entries) {
    const key = entry.translation_key;
    if (!key) continue;
    if (key.includes("_pb_")) pbs.push(entry.entity_id);
    else byKey[key] = entry.entity_id;
  }
  return { byKey, pbs, deviceId: deviceId || entries[0]?.device_id };
}

function concept2Devices(hass) {
  const ids = new Set(
    Object.values(hass.entities || {})
      .filter((e) => e.platform === DOMAIN && e.device_id)
      .map((e) => e.device_id),
  );
  return [...ids];
}

class Concept2LogbookCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("concept2-logbook-card-editor");
  }

  static getStubConfig(hass) {
    const [deviceId] = concept2Devices(hass);
    return deviceId ? { device_id: deviceId } : {};
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._stats = null; // { days: [{date, value}], error }
    this._statsKey = null;
    this._statsFetchedAt = 0;
    this._hoverIndex = null;
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = { ...DEFAULTS, ...config };
    this._config.chart_days = Math.min(90, Math.max(7, Number(this._config.chart_days) || 28));
    this._statsKey = null;
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const signature = this._signature();
    if (first || signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._render();
    }
    this._maybeFetchStats();
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // Re-render only when one of our entities changes.
  _signature() {
    if (!this._hass || !this._config) return "";
    const { byKey, pbs } = findEntities(this._hass, this._config.device_id);
    return [...Object.values(byKey), ...pbs]
      .map((id) => this._hass.states[id]?.last_updated ?? "")
      .join("|");
  }

  _state(key) {
    const id = this._entities?.byKey[key];
    return id ? this._hass.states[id] : undefined;
  }

  _value(key) {
    const s = this._state(key);
    return s && s.state !== "unavailable" && s.state !== "unknown" ? num(s.state) : null;
  }

  _fmt(value, opts = {}) {
    if (value === null || value === undefined) return "–";
    const locale = this._hass?.locale?.language || navigator.language;
    return new Intl.NumberFormat(locale, { maximumFractionDigits: 0, ...opts }).format(value);
  }

  _fmtDate(date, opts) {
    const locale = this._hass?.locale?.language || navigator.language;
    return new Intl.DateTimeFormat(locale, opts).format(date);
  }

  async _maybeFetchStats() {
    if (!this._hass || !this._config?.show_chart) return;
    const lifetime = this._state("lifetime_distance");
    const statId = lifetime?.attributes?.statistic_id;
    if (!statId) return;
    // Refetch when the config or the lifetime total changes, or every 30 min.
    const key = `${statId}|${this._config.chart_days}|${lifetime.state}`;
    const stale = Date.now() - this._statsFetchedAt > STATS_REFRESH_MS;
    if (key === this._statsKey && !stale) return;
    if (this._fetching) return;
    this._fetching = true;
    this._statsKey = key;
    this._statsFetchedAt = Date.now();
    const days = this._config.chart_days;
    const start = startOfDay(new Date());
    start.setDate(start.getDate() - (days - 1));
    try {
      const result = await this._hass.callWS({
        type: "recorder/statistics_during_period",
        start_time: start.toISOString(),
        statistic_ids: [statId],
        period: "day",
        types: ["change"],
      });
      const byDay = {};
      for (const row of result?.[statId] || []) {
        const d = new Date(typeof row.start === "number" ? row.start : Date.parse(row.start));
        byDay[dayKey(d)] = (byDay[dayKey(d)] || 0) + (num(row.change) || 0);
      }
      const series = [];
      for (let i = 0; i < days; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        series.push({ date: d, value: Math.max(0, byDay[dayKey(d)] || 0) });
      }
      this._stats = { days: series };
    } catch (err) {
      this._stats = { days: [], error: err?.message || String(err) };
    } finally {
      this._fetching = false;
      this._render();
    }
  }

  _render() {
    if (!this._config || !this._hass) return;
    this._entities = findEntities(this._hass, this._config.device_id);
    const c = this._config;

    let body;
    if (!this._entities.deviceId) {
      body = `<div class="empty">No Concept2 Logbook account found. Add the Concept2 Logbook integration first.</div>`;
    } else {
      body = [
        c.show_totals ? this._renderTotals() : "",
        c.show_chart ? this._renderChart() : "",
        c.show_streaks ? this._renderStreaks() : "",
        c.show_pbs ? this._renderPbs() : "",
      ]
        .filter(Boolean)
        .join('<div class="divider"></div>');
    }

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <ha-card>
        <div class="header">
          <div class="title">${esc(c.title)}</div>
        </div>
        <div class="content">${body}</div>
      </ha-card>`;
    this._bindChart();
  }

  _renderTotals() {
    const c = this._config;
    const now = new Date();
    const lifetime = this._value("lifetime_distance");
    const chips = [
      ["Season", this._value("season_distance")],
      ["Month", this._value("month_distance")],
      ["Week", this._value("week_distance")],
    ]
      .map(
        ([label, v]) => `
        <div class="chip">
          <div class="chip-label">${label}</div>
          <div class="chip-value">${this._fmt(v)}<span class="unit">m</span></div>
        </div>`,
      )
      .join("");

    const goals = [];
    if (num(c.weekly_goal) > 0) {
      goals.push(this._goalBar("Weekly goal", this._value("week_distance"), num(c.weekly_goal), weekBounds(now), now));
    }
    if (num(c.season_goal) > 0) {
      goals.push(this._goalBar("Season goal", this._value("season_distance"), num(c.season_goal), seasonBounds(now), now));
    }

    return `
      <section class="totals">
        <div class="hero">
          <div class="hero-value">${this._fmt(lifetime)}<span class="unit">m</span></div>
          <div class="hero-label">Lifetime metres</div>
        </div>
        <div class="chips">${chips}</div>
        ${goals.join("")}
      </section>`;
  }

  _goalBar(label, value, goal, [start, end], now) {
    const done = value || 0;
    const pct = Math.min(100, (done / goal) * 100);
    const elapsed = Math.min(1, Math.max(0, (now - start) / (end - start)));
    const expected = goal * elapsed;
    const diff = done - expected;
    let pace;
    if (done >= goal) pace = `<span class="good">Goal reached</span>`;
    else if (diff >= 0) pace = `<span class="good">${this._fmt(diff)} m ahead of pace</span>`;
    else pace = `<span class="behind">${this._fmt(-diff)} m behind pace</span>`;
    return `
      <div class="goal">
        <div class="goal-row">
          <span class="goal-label">${label}</span>
          <span class="goal-numbers">${this._fmt(done)} / ${this._fmt(goal)} m</span>
        </div>
        <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${goal}" aria-valuenow="${done}" aria-label="${esc(label)}">
          <div class="bar-fill" style="width:${pct.toFixed(1)}%"></div>
          <div class="bar-marker" style="left:${(elapsed * 100).toFixed(1)}%" title="Where you'd be at an even pace"></div>
        </div>
        <div class="goal-pace">${Math.round(pct)}% · ${pace}</div>
      </div>`;
  }

  _renderChart() {
    const days = this._config.chart_days;
    const stats = this._stats;
    if (!stats) {
      return `<section class="chart"><div class="section-title">Last ${days} days</div><div class="chart-placeholder">Loading…</div></section>`;
    }
    if (stats.error) {
      return `<section class="chart"><div class="section-title">Last ${days} days</div><div class="chart-placeholder">Couldn't load history: ${esc(stats.error)}</div></section>`;
    }
    const series = stats.days;
    const max = Math.max(...series.map((d) => d.value), 1);
    const total = series.reduce((s, d) => s + d.value, 0);
    const active = series.filter((d) => d.value > 0).length;

    // viewBox units: one slot per day, 100 high.
    const slot = 10;
    const gap = days > 45 ? 1.5 : 2.5;
    const h = 100;
    const todayKey = dayKey(new Date());
    const bars = series
      .map((d, i) => {
        const x = i * slot + gap / 2;
        const w = slot - gap;
        const isToday = dayKey(d.date) === todayKey;
        if (d.value <= 0) {
          return `<rect class="zero${isToday ? " today" : ""}" x="${x}" y="${h - 1.5}" width="${w}" height="1.5" rx="0.75" data-i="${i}"></rect>`;
        }
        const bh = Math.max(3, (d.value / max) * (h - 4));
        return `<rect class="day${isToday ? " today" : ""}" x="${x}" y="${h - bh}" width="${w}" height="${bh}" rx="${Math.min(2, w / 2)}" data-i="${i}"></rect>`;
      })
      .join("");
    // Faint separators at the start of each week (Monday).
    const weekLines = series
      .map((d, i) =>
        i > 0 && d.date.getDay() === 1
          ? `<line class="week-line" x1="${i * slot}" x2="${i * slot}" y1="0" y2="${h}"></line>`
          : "",
      )
      .join("");
    const hits = series
      .map((d, i) => `<rect class="hit" x="${i * slot}" y="0" width="${slot}" height="${h}" data-i="${i}"></rect>`)
      .join("");

    const first = series[0]?.date;
    const last = series[series.length - 1]?.date;
    const short = { day: "numeric", month: "short" };

    return `
      <section class="chart">
        <div class="chart-head">
          <div class="section-title">Last ${days} days</div>
          <div class="readout" aria-live="polite">${this._readout(null, total, active)}</div>
        </div>
        <svg class="bars" viewBox="0 0 ${days * slot} ${h}" preserveAspectRatio="none" role="img"
             aria-label="Metres per day for the last ${days} days, ${this._fmt(total)} metres in total">
          ${weekLines}${bars}${hits}
        </svg>
        <div class="axis">
          <span>${first ? esc(this._fmtDate(first, short)) : ""}</span>
          <span>Today</span>
        </div>
      </section>`;
  }

  _readout(index, total, active) {
    if (index === null || !this._stats?.days[index]) {
      const avg = active ? total / active : 0;
      return `<b>${this._fmt(total)} m</b> · ${active} active day${active === 1 ? "" : "s"}${active ? ` · avg ${this._fmt(avg)} m` : ""}`;
    }
    const d = this._stats.days[index];
    const label = this._fmtDate(d.date, { weekday: "short", day: "numeric", month: "short" });
    return `${esc(label)} · <b>${d.value > 0 ? `${this._fmt(d.value)} m` : "rest day"}</b>`;
  }

  _bindChart() {
    const svg = this.shadowRoot.querySelector("svg.bars");
    const readout = this.shadowRoot.querySelector(".readout");
    if (!svg || !readout || !this._stats?.days) return;
    const series = this._stats.days;
    const total = series.reduce((s, d) => s + d.value, 0);
    const active = series.filter((d) => d.value > 0).length;
    const highlight = (i) => {
      svg.querySelectorAll(".active").forEach((el) => el.classList.remove("active"));
      if (i !== null) svg.querySelectorAll(`[data-i="${i}"]:not(.hit)`).forEach((el) => el.classList.add("active"));
      readout.innerHTML = this._readout(i, total, active);
    };
    svg.addEventListener("pointermove", (ev) => {
      const i = ev.target?.dataset?.i;
      if (i !== undefined) highlight(Number(i));
    });
    svg.addEventListener("pointerleave", () => highlight(null));
  }

  _renderStreaks() {
    const tile = (label, key, unit, bestKey, icon) => {
      const v = this._value(key);
      const best = bestKey ? this._value(bestKey) : null;
      return `
        <div class="tile">
          <div class="tile-label"><ha-icon icon="${icon}"></ha-icon>${label}</div>
          <div class="tile-value">${this._fmt(v)}<span class="unit">${unit}</span></div>
          ${best !== null ? `<div class="tile-sub">Best ${this._fmt(best)}</div>` : ""}
        </div>`;
    };
    const since = this._value("days_since_last_workout");
    const sinceText = since === null ? "–" : since === 0 ? "Today" : since === 1 ? "Yesterday" : `${this._fmt(since)} days ago`;
    return `
      <section class="streaks">
        ${tile("Daily streak", "current_daily_streak", "days", "longest_daily_streak", "mdi:fire")}
        ${tile("Weekly streak", "current_weekly_streak", "wks", "longest_weekly_streak", "mdi:calendar-check")}
        ${tile("This week", "week_count", "rows", null, "mdi:rowing")}
        <div class="tile">
          <div class="tile-label"><ha-icon icon="mdi:calendar-clock"></ha-icon>Last row</div>
          <div class="tile-value small">${esc(sinceText)}</div>
        </div>
      </section>`;
  }

  _renderPbs() {
    const all = this._entities.pbs
      .map((id) => this._hass.states[id])
      .filter((s) => s && s.state !== "unavailable" && s.attributes?.event);
    if (!all.length) {
      return `<section class="pbs"><div class="section-title">Personal bests</div><div class="chart-placeholder">No PBs yet. Single Distance and Single Time pieces show up here.</div></section>`;
    }
    const counts = {};
    for (const s of all) counts[s.attributes.machine] = (counts[s.attributes.machine] || 0) + 1;
    const machine =
      this._config.machine && counts[this._config.machine]
        ? this._config.machine
        : Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
    const [seasonStart] = seasonBounds(new Date());
    const rows = all
      .filter((s) => s.attributes.machine === machine)
      .sort((a, b) => {
        const ka = a.attributes.event_kind === "distance" ? 0 : 1;
        const kb = b.attributes.event_kind === "distance" ? 0 : 1;
        return ka - kb || a.attributes.event_target - b.attributes.event_target;
      })
      .map((s) => {
        const a = s.attributes;
        const date = a.date ? new Date(a.date) : null;
        const thisSeason = date && date >= seasonStart;
        const result = a.event_kind === "distance" ? s.state : `${this._fmt(num(s.state))} m`;
        // A 500m time is its own pace, so don't repeat it.
        const per = machine === "bike" ? "/1000m" : "/500m";
        const repeatsTime = a.event_kind === "distance" && a.event_target === (machine === "bike" ? 1000 : 500);
        const pace = a.pace && !repeatsTime ? `${a.pace} ${per}` : "";
        let season = "";
        if (thisSeason) season = `<span class="badge">This season</span>`;
        else if (a.season_best_date) {
          const sb = a.event_kind === "distance" ? a.season_best_time : `${this._fmt(a.season_best_distance_m)} m`;
          season = `<span class="sb">SB ${esc(sb)}</span>`;
        }
        return `
          <div class="pb-row">
            <div class="pb-event">${esc(a.event)}</div>
            <div class="pb-result">${esc(result)}</div>
            <div class="pb-meta">${pace ? `${esc(pace)} · ` : ""}${date ? esc(this._fmtDate(date, { day: "numeric", month: "short", year: "numeric" })) : ""}</div>
            <div class="pb-season">${season}</div>
          </div>`;
      })
      .join("");
    return `
      <section class="pbs">
        <div class="section-title">Personal bests · ${esc(MACHINE_NAMES[machine] || machine)}</div>
        <div class="pb-list">${rows}</div>
      </section>`;
  }
}

const STYLES = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .header { padding: 16px 16px 0; }
  .title { font-size: 1.1rem; font-weight: 500; color: var(--primary-text-color); letter-spacing: 0.01em; }
  .content { padding: 12px 16px 16px; }
  .divider { height: 1px; background: var(--divider-color); margin: 16px 0; }
  .unit { font-size: 0.55em; font-weight: 500; color: var(--secondary-text-color); margin-left: 3px; letter-spacing: 0; }
  .section-title { font-size: 0.8rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: var(--secondary-text-color); }
  .empty, .chart-placeholder { color: var(--secondary-text-color); font-size: 0.9rem; padding: 8px 0; }

  .hero-value { font-size: 2.4rem; font-weight: 600; line-height: 1.1; color: var(--primary-text-color); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .hero-label { font-size: 0.85rem; color: var(--secondary-text-color); margin-top: 2px; }
  .chips { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 14px; }
  .chip { background: var(--secondary-background-color, rgba(127,127,127,0.08)); border-radius: 10px; padding: 8px 10px; min-width: 0; }
  .chip-label { font-size: 0.75rem; color: var(--secondary-text-color); }
  .chip-value { font-size: 1.05rem; font-weight: 600; color: var(--primary-text-color); font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .goal { margin-top: 14px; }
  .goal-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; font-size: 0.85rem; }
  .goal-label { color: var(--primary-text-color); font-weight: 500; }
  .goal-numbers { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .bar { position: relative; height: 8px; border-radius: 4px; background: var(--secondary-background-color, rgba(127,127,127,0.15)); margin-top: 6px; }
  .bar-fill { height: 100%; border-radius: 4px; background: var(--primary-color); transition: width 0.4s ease; }
  .bar-marker { position: absolute; top: -3px; width: 2px; height: 14px; margin-left: -1px; border-radius: 1px; background: var(--primary-text-color); opacity: 0.55; }
  .goal-pace { font-size: 0.78rem; color: var(--secondary-text-color); margin-top: 5px; }
  .good { color: var(--success-color, #43a047); }
  .behind { color: var(--warning-color, #ffa600); }

  .chart-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .readout { font-size: 0.82rem; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; min-height: 1.2em; }
  .readout b { color: var(--primary-text-color); font-weight: 600; }
  svg.bars { display: block; width: 100%; height: 96px; margin-top: 10px; touch-action: pan-y; }
  svg .day { fill: var(--primary-color); opacity: 0.75; transition: opacity 0.15s; }
  svg .day.today { opacity: 1; }
  svg .zero { fill: var(--divider-color); }
  svg .zero.today { fill: var(--primary-color); opacity: 0.5; }
  svg .active { opacity: 1 !important; fill: var(--accent-color, var(--primary-color)); }
  svg .zero.active { fill: var(--secondary-text-color); }
  svg .week-line { stroke: var(--divider-color); stroke-width: 0.5; vector-effect: non-scaling-stroke; stroke-dasharray: 2 3; }
  svg .hit { fill: transparent; cursor: crosshair; }
  .axis { display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--secondary-text-color); margin-top: 4px; }

  .streaks { display: grid; grid-template-columns: repeat(auto-fit, minmax(115px, 1fr)); gap: 8px; }
  .tile { background: var(--secondary-background-color, rgba(127,127,127,0.08)); border-radius: 10px; padding: 10px 12px; min-width: 0; }
  .tile-label { display: flex; align-items: center; gap: 4px; font-size: 0.75rem; color: var(--secondary-text-color); white-space: nowrap; }
  .tile-label ha-icon { --mdc-icon-size: 16px; color: var(--primary-color); }
  .tile-value { font-size: 1.5rem; font-weight: 600; color: var(--primary-text-color); font-variant-numeric: tabular-nums; margin-top: 2px; }
  .tile-value.small { font-size: 1.1rem; padding-top: 6px; }
  .tile-sub { font-size: 0.72rem; color: var(--secondary-text-color); }

  .pb-list { margin-top: 8px; }
  .pb-row { display: grid; grid-template-columns: minmax(64px, 1fr) auto; grid-template-areas: "event result" "meta season"; column-gap: 12px; row-gap: 1px; padding: 8px 0; border-bottom: 1px solid var(--divider-color); }
  .pb-row:last-child { border-bottom: 0; padding-bottom: 0; }
  .pb-event { grid-area: event; font-weight: 500; color: var(--primary-text-color); }
  .pb-result { grid-area: result; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .pb-meta { grid-area: meta; font-size: 0.75rem; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .pb-season { grid-area: season; text-align: right; font-size: 0.72rem; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 8px; background: var(--primary-color); color: var(--text-primary-color, #fff); font-weight: 500; }
  .sb { color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
`;

/* ---------- Visual editor ---------- */

const EDITOR_LABELS = {
  device_id: "Concept2 account",
  title: "Title",
  machine: "Machine for personal bests",
  weekly_goal: "Weekly goal (metres, optional)",
  season_goal: "Season goal (metres, optional)",
  chart_days: "Days in activity chart",
  show_totals: "Show totals and goals",
  show_chart: "Show activity chart",
  show_streaks: "Show streaks",
  show_pbs: "Show personal bests",
};

class Concept2LogbookCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    else this._render();
  }

  _schema() {
    const machines = new Set();
    for (const s of Object.values(this._hass?.states || {})) {
      if (s.attributes?.event_kind && s.attributes?.machine) machines.add(s.attributes.machine);
    }
    const options = [...machines].map((m) => ({ value: m, label: MACHINE_NAMES[m] || m }));
    return [
      { name: "device_id", selector: { device: { integration: DOMAIN } } },
      { name: "title", selector: { text: {} } },
      ...(options.length > 1 ? [{ name: "machine", selector: { select: { options, mode: "dropdown" } } }] : []),
      { name: "weekly_goal", selector: { number: { min: 0, step: 1000, mode: "box", unit_of_measurement: "m" } } },
      { name: "season_goal", selector: { number: { min: 0, step: 10000, mode: "box", unit_of_measurement: "m" } } },
      { name: "chart_days", selector: { number: { min: 7, max: 90, step: 1, mode: "slider" } } },
      { name: "show_totals", selector: { boolean: {} } },
      { name: "show_chart", selector: { boolean: {} } },
      { name: "show_streaks", selector: { boolean: {} } },
      { name: "show_pbs", selector: { boolean: {} } },
    ];
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const k of ["weekly_goal", "season_goal"]) {
          if (config[k] === "" || config[k] === null || config[k] === 0) delete config[k];
        }
        this._config = config;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = this._schema();
    this._form.data = { ...DEFAULTS, ...this._config };
  }
}

if (!customElements.get("concept2-logbook-card")) {
  customElements.define("concept2-logbook-card", Concept2LogbookCard);
  customElements.define("concept2-logbook-card-editor", Concept2LogbookCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "concept2-logbook-card",
    name: "Concept2 Logbook",
    description: "Rowing totals, goals, activity, streaks and personal bests from the Concept2 Logbook (unofficial).",
    preview: true,
    documentationURL: "https://github.com/ChaoticOrb/ha-c2-stats",
  });
  console.info(`%c CONCEPT2-LOGBOOK-CARD %c ${CARD_VERSION} `, "background:#1565c0;color:#fff", "");
}
