var __defProp = Object.defineProperty;
var __defProps = Object.defineProperties;
var __getOwnPropDescs = Object.getOwnPropertyDescriptors;
var __getOwnPropSymbols = Object.getOwnPropertySymbols;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __propIsEnum = Object.prototype.propertyIsEnumerable;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __spreadValues = (a, b) => {
  for (var prop in b || (b = {}))
    if (__hasOwnProp.call(b, prop))
      __defNormalProp(a, prop, b[prop]);
  if (__getOwnPropSymbols)
    for (var prop of __getOwnPropSymbols(b)) {
      if (__propIsEnum.call(b, prop))
        __defNormalProp(a, prop, b[prop]);
    }
  return a;
};
var __spreadProps = (a, b) => __defProps(a, __getOwnPropDescs(b));
const { useState, useEffect, useRef, useCallback } = React;
const api = {
  async upload(formData) {
    const r = await fetch("/api/v1/upload", { method: "POST", body: formData });
    return r.json();
  },
  async uploadJSON(payload) {
    const r = await fetch("/api/v1/upload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return r.json();
  },
  async analyze(pid, demo = true) {
    const r = await fetch(`/api/v1/analyze/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ demo_mode: demo })
    });
    return r.json();
  },
  async generate(pid, ids = null) {
    const r = await fetch(`/api/v1/generate/${pid}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_ids: ids })
    });
    return r.json();
  },
  async patchApproval(pid, aid, data) {
    const r = await fetch(`/api/v1/project/${pid}/approval/${aid}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return r.json();
  }
};
const PRI_LABELS = { critical: "\u25CF \u041A\u0440\u0438\u0442\u0438\u0447\u043D\u043E", important: "\u25CF \u0412\u0430\u0436\u043D\u043E", recommended: "\u25CB \u0420\u0435\u043A\u043E\u043C\u0435\u043D\u0434." };
const PRI_CLASS = { critical: "priority-critical", important: "priority-important", recommended: "priority-recommended" };
const OWN_COLORS = { private: "#F9F1DC", municipal: "#E8F0E0", federal: "#EDE8D8", state: "#EDE8D8" };
const OWN_LABELS = { private: "\u0427\u0430\u0441\u0442\u043D\u0430\u044F", municipal: "\u041C\u0443\u043D\u0438\u0446\u0438\u043F\u0430\u043B\u044C\u043D\u0430\u044F", federal: "\u0413\u043E\u0441. (\u0444\u0435\u0434\u0435\u0440.)", state: "\u0413\u043E\u0441. (\u0440\u0435\u0433\u0438\u043E\u043D.)" };
const SEV_COLORS = { critical: "#E24545", warning: "#E0A32B", info: "#1F5FBF" };
const DATA_SOURCE_INFO = {
  pkk_live: { text: "Живой запрос к ПКК Росреестра", type: "ok" },
  demo_fallback: { text: "PKK API недоступен — использованы демо-данные", type: "warn" },
  demo: { text: "Демо-режим (без запроса к ПКК Росреестра)", type: "info" }
};
const ROI_HOURS_PER_APPROVAL = 3;
const ALERT_ICONS = {
  info: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4.5"/><path d="M12 8h.01"/></svg>',
  ok: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  err: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>',
  warn: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'
};
function Alert({ type = "info", children }) {
  const icon = ALERT_ICONS[type] || ALERT_ICONS.info;
  return /* @__PURE__ */ React.createElement("div", { className: `alert alert-${type}` }, /* @__PURE__ */ React.createElement("span", { style: { display: "flex", flexShrink: 0 }, dangerouslySetInnerHTML: { __html: icon } }), /* @__PURE__ */ React.createElement("span", null, children));
}
function Spin() {
  return /* @__PURE__ */ React.createElement("span", { className: "spin" });
}
function MapView({ route, parcels, intersections, onParcelClick }) {
  const mapRef = useRef(null);
  const leafRef = useRef(null);
  const layersRef = useRef({ route: null, parcels: null, intersections: null });
  const [activeLayers, setActiveLayers] = useState({ route: true, parcels: true, intersections: true });
  useEffect(() => {
    if (leafRef.current) return;
    leafRef.current = L.map(mapRef.current, { zoomControl: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "",
      maxZoom: 19
    }).addTo(leafRef.current);
    L.control.zoom({ position: "bottomright" }).addTo(leafRef.current);
  }, []);
  useEffect(() => {
    const map = leafRef.current;
    if (!map || !route.length) return;
    if (layersRef.current.route) map.removeLayer(layersRef.current.route);
    const pts = route.filter((p) => p.lat && p.lon).map((p) => [p.lat, p.lon]);
    if (!pts.length) return;
    const grp = L.layerGroup();
    L.polyline(pts, { color: (window.THEME||{}).routeColor||"#FF6A2B", weight: 3, opacity: 0.9 }).addTo(grp);
    pts.forEach((pt, i) => {
      const p = route[i];
      const isEnd = i === 0 || i === pts.length - 1;
      const circle = L.circleMarker(pt, {
        radius: isEnd ? 7 : 4,
        fillColor: (window.THEME||{}).markerFill||"#FF6A2B",
        color: "white",
        weight: 1.5,
        fillOpacity: 1
      }).addTo(grp);
      circle.bindPopup(`<div class="parcel-popup">
        <b>${p.description || "\u0422-" + (i + 1)}</b><br/>
        \u041F\u041A: ${(p.pk / 1e3).toFixed(3).replace(".", "+")}<br/>
        lon: ${p.lon.toFixed(6)}, lat: ${p.lat.toFixed(6)}<br/>
        \u0413\u043B\u0443\u0431\u0438\u043D\u0430: ${p.depth} \u043C
      </div>`);
    });
    layersRef.current.route = grp;
    if (activeLayers.route) grp.addTo(map);
    map.fitBounds(pts, { padding: [40, 40] });
  }, [route]);
  useEffect(() => {
    const map = leafRef.current;
    if (!map) return;
    if (layersRef.current.parcels) map.removeLayer(layersRef.current.parcels);
    const grp = L.layerGroup();
    parcels.forEach((p) => {
      if (!p.polygon || p.polygon.length < 3) return;
      const latlngs = p.polygon.map(([lon, lat]) => [lat, lon]);
      const color = OWN_COLORS[p.owner_type] || "#E0E0E0";
      const poly = L.polygon(latlngs, {
        color: "#5B8DB8",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.45
      }).addTo(grp);
      poly.bindPopup(`<div class="parcel-popup">
        <b>${p.cn}</b><br/>
        \u041A\u0430\u0442\u0435\u0433\u043E\u0440\u0438\u044F: ${p.category}<br/>
        \u0421\u043E\u0431\u0441\u0442\u0432\u0435\u043D\u043D\u043E\u0441\u0442\u044C: <b>${OWN_LABELS[p.owner_type] || p.owner_type}</b><br/>
        ${p.owner_name ? `\u041F\u0440\u0430\u0432\u043E\u043E\u0431\u043B\u0430\u0434\u0430\u0442\u0435\u043B\u044C: ${p.owner_name}<br/>` : ""}
        \u041F\u043B\u043E\u0449\u0430\u0434\u044C: ${(p.area / 1e4).toFixed(2)} \u0433\u0430
      </div>`);
      poly.on("click", () => onParcelClick && onParcelClick(p));
    });
    layersRef.current.parcels = grp;
    if (activeLayers.parcels) grp.addTo(map);
  }, [parcels]);
  useEffect(() => {
    const map = leafRef.current;
    if (!map) return;
    if (layersRef.current.intersections) map.removeLayer(layersRef.current.intersections);
    const grp = L.layerGroup();
    intersections.forEach((ix, i) => {
      const pk = (ix.pk_start + ix.pk_end) / 2;
      const nearest = route.reduce((a, b) => Math.abs(b.pk - pk) < Math.abs(a.pk - pk) ? b : a, route[0] || {});
      if (!nearest || !nearest.lat) return;
      const col = SEV_COLORS[ix.severity] || "#2E5C8A";
      const marker = L.circleMarker([nearest.lat, nearest.lon], {
        radius: 10,
        fillColor: col,
        color: "white",
        weight: 2,
        fillOpacity: 0.95
      }).addTo(grp);
      const icon = L.divIcon({
        html: `<div style="color:white;font-weight:700;font-size:12px;line-height:1;
          margin-top:-1px">!</div>`,
        className: "",
        iconSize: [0, 0],
        iconAnchor: [0, 0]
      });
      L.marker([nearest.lat, nearest.lon], { icon }).addTo(grp);
      marker.bindPopup(`<div class="parcel-popup">
        <b>${ix.object_name}</b><br/>
        \u0422\u0438\u043F: ${ix.object_type}<br/>
        \u041F\u041A: ${(ix.pk_start / 1e3).toFixed(3).replace(".", "+")}<br/>
        \u0414\u043B\u0438\u043D\u0430 \u043F\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043D\u0438\u044F: ${ix.length_m} \u043C<br/>
        \u041F\u0440\u0438\u043E\u0440\u0438\u0442\u0435\u0442: <b style="color:${col}">${ix.severity}</b>
      </div>`);
    });
    layersRef.current.intersections = grp;
    if (activeLayers.intersections) grp.addTo(map);
  }, [intersections]);
  const toggle = (name) => {
    const map = leafRef.current;
    if (!map) return;
    const layer = layersRef.current[name];
    if (!layer) return;
    const next = !activeLayers[name];
    if (next) layer.addTo(map);
    else map.removeLayer(layer);
    setActiveLayers((p) => __spreadProps(__spreadValues({}, p), { [name]: next }));
  };
  return /* @__PURE__ */ React.createElement("div", { className: "map-wrap" }, /* @__PURE__ */ React.createElement("div", { id: "map", ref: mapRef }), /* @__PURE__ */ React.createElement("div", { className: "map-overlay" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      className: `map-btn${activeLayers.route ? " active" : ""}`,
      onClick: () => toggle("route")
    },
    "\u{1F536} \u0422\u0440\u0430\u0441\u0441\u0430 \u041A\u041B"
  ), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: `map-btn${activeLayers.parcels ? " active" : ""}`,
      onClick: () => toggle("parcels")
    },
    "\u{1F4E6} \u041A\u0430\u0434\u0430\u0441\u0442\u0440"
  ), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: `map-btn${activeLayers.intersections ? " active" : ""}`,
      onClick: () => toggle("intersections")
    },
    "\u26A0 \u041F\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043D\u0438\u044F"
  )));
}
function UploadTab({ onUploaded }) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [projectName, setProjectName] = useState("\u041A\u041B-10\u043A\u0412 \xAB\u0422\u041F-1 \u2014 \u0422\u041F-2\xBB");
  const [useDemo, setUseDemo] = useState(true);
  const fileRef = useRef();
  const DEMO_POINTS = [
    { x: 471234.52, y: 241011834e-2, depth: 1.2, description: "\u0422\u041F-1 (\u043D\u0430\u0447\u0430\u043B\u043E)" },
    { x: 471358.91, y: 241011834e-2, depth: 1.2, description: "\u041F\u043E\u0432\u043E\u0440\u043E\u0442 \u0422-2" },
    { x: 471358.91, y: 241052978e-2, depth: 1.5, description: "\u041E\u0445\u0440. \u0437\u043E\u043D\u0430 \u0433\u0430\u0437\u0430" },
    { x: 471586.22, y: 241082345e-2, depth: 1.5, description: "\u041F\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043D\u0438\u0435 \u0434\u043E\u0440\u043E\u0433\u0438" },
    { x: 471712.45, y: 241128411e-2, depth: 1.2, description: "\u041F\u0440\u044F\u043C\u043E\u043B\u0438\u043D\u0435\u0439\u043D\u044B\u0439" },
    { x: 471712.45, y: 241191289e-2, depth: 1.2, description: "\u041F\u043E\u0432\u043E\u0440\u043E\u0442 \u0422-6" },
    { x: 471938.67, y: 241219432e-2, depth: 1.2, description: "\u041F\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043D\u0438\u0435 \u0441\u0432\u044F\u0437\u0438" },
    { x: 472054.11, y: 241219432e-2, depth: 1.2, description: "\u0422\u041F-2 (\u043A\u043E\u043D\u0435\u0446)" }
  ];
  async function handleFile(file) {
    setLoading(true);
    setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("project", projectName);
    const data = await api.upload(fd);
    setLoading(false);
    if (data.success) {
      onUploaded(data);
    } else setMsg({ type: "err", text: (data.errors || [data.error || "\u041E\u0448\u0438\u0431\u043A\u0430"]).join("; ") });
  }
  async function handleDemo() {
    setLoading(true);
    setMsg(null);
    const data = await api.uploadJSON({ project: projectName, points: DEMO_POINTS });
    setLoading(false);
    if (data.success) onUploaded(data);
    else setMsg({ type: "err", text: data.error || "\u041E\u0448\u0438\u0431\u043A\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043A\u0438" });
  }
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "card" }, /* @__PURE__ */ React.createElement("div", { className: "card-title" }, "\u0418\u0441\u0445\u043E\u0434\u043D\u044B\u0435 \u0434\u0430\u043D\u043D\u044B\u0435 \u043F\u0440\u043E\u0435\u043A\u0442\u0430"), /* @__PURE__ */ React.createElement("label", null, "\u041D\u0430\u0437\u0432\u0430\u043D\u0438\u0435 \u043F\u0440\u043E\u0435\u043A\u0442\u0430"), /* @__PURE__ */ React.createElement(
    "input",
    {
      value: projectName,
      onChange: (e) => setProjectName(e.target.value),
      placeholder: "\u041A\u041B-10\u043A\u0412 \xAB\u0422\u041F-1 \u2014 \u0422\u041F-2\xBB"
    }
  )), /* @__PURE__ */ React.createElement(
    "div",
    {
      className: `upload-zone${dragging ? " drag" : ""}`,
      onClick: () => fileRef.current.click(),
      onDragOver: (e) => {
        e.preventDefault();
        setDragging(true);
      },
      onDragLeave: () => setDragging(false),
      onDrop: (e) => {
        e.preventDefault();
        setDragging(false);
        const f = e.dataTransfer.files[0];
        if (f) handleFile(f);
      }
    },
    /* @__PURE__ */ React.createElement("div", { className: "icon", dangerouslySetInnerHTML: { __html: '<svg viewBox="0 0 24 24" width="38" height="38" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14.9A7 7 0 1 1 15.7 8h1.8a4.5 4.5 0 0 1 2.5 8.2"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>' } }),
    /* @__PURE__ */ React.createElement("strong", null, "\u041F\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0444\u0430\u0439\u043B \u0438\u043B\u0438 \u043A\u043B\u0438\u043A\u043D\u0438\u0442\u0435"),
    /* @__PURE__ */ React.createElement("p", null, "DXF / DWG (AutoCAD) \xB7 CSV \u0441 \u043A\u043E\u043E\u0440\u0434\u0438\u043D\u0430\u0442\u0430\u043C\u0438"),
    /* @__PURE__ */ React.createElement(
      "input",
      {
        ref: fileRef,
        type: "file",
        accept: ".dxf,.dwg,.csv",
        style: { display: "none" },
        onChange: (e) => e.target.files[0] && handleFile(e.target.files[0])
      }
    )
  ), msg && /* @__PURE__ */ React.createElement(Alert, { type: msg.type }, msg.text), /* @__PURE__ */ React.createElement("div", { className: "card" }, /* @__PURE__ */ React.createElement("div", { className: "card-title" }, "\u0414\u0435\u043C\u043E-\u0440\u0435\u0436\u0438\u043C"), /* @__PURE__ */ React.createElement(Alert, { type: "info" }, "\u041A\u041B-10\u043A\u0412 \xAB\u0422\u041F-1\u2014\u0422\u041F-2\xBB, \u041C\u043E\u0441\u043A\u0432\u0430 \u0412\u0410\u041E \xB7 8 \u0442\u043E\u0447\u0435\u043A \xB7 \u041C\u0421\u041A-77 \xB7 5 400 \u043C"), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "btn btn-green",
      style: { width: "100%" },
      onClick: handleDemo,
      disabled: loading
    },
    loading ? /* @__PURE__ */ React.createElement(Spin, null) : "\u26A1",
    " \u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C \u0434\u0435\u043C\u043E-\u043C\u0430\u0440\u0448\u0440\u0443\u0442"
  )));
}
function AnalysisTab({ project, onAnalyzed }) {
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [demoMode, setDemoMode] = useState(true);
  async function run() {
    setLoading(true);
    setMsg(null);
    const data = await api.analyze(project.project_id, demoMode);
    setLoading(false);
    if (data.success) onAnalyzed(data);
    else setMsg({ type: "err", text: (data.errors || [data.error || "\u041E\u0448\u0438\u0431\u043A\u0430"]).join("; ") });
  }
  const s = project.route_summary || {};
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "card" }, /* @__PURE__ */ React.createElement("div", { className: "card-title" }, "\u0417\u0430\u0433\u0440\u0443\u0436\u0435\u043D\u043D\u044B\u0439 \u043C\u0430\u0440\u0448\u0440\u0443\u0442"), /* @__PURE__ */ React.createElement("div", { className: "stats" }, /* @__PURE__ */ React.createElement("div", { className: "stat info" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, s.points_count || 0), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u0442\u043E\u0447\u0435\u043A")), /* @__PURE__ */ React.createElement("div", { className: "stat info" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, ((s.total_length_m || 0) / 1e3).toFixed(1)), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u043A\u043C \u0442\u0440\u0430\u0441\u0441\u044B"))), /* @__PURE__ */ React.createElement("p", { style: { fontSize: 12, color: "var(--muted)" } }, "\u0421\u041A: ", /* @__PURE__ */ React.createElement("b", { style: { color: "var(--light)" } }, s.crs_detected || "\u2014"))), /* @__PURE__ */ React.createElement("div", { className: "card" }, /* @__PURE__ */ React.createElement("div", { className: "card-title" }, "\u041A\u0430\u0434\u0430\u0441\u0442\u0440\u043E\u0432\u0430\u044F \u0441\u0432\u0435\u0440\u043A\u0430"), /* @__PURE__ */ React.createElement("label", { style: { display: "flex", alignItems: "center", gap: 8, cursor: "pointer" } }, /* @__PURE__ */ React.createElement(
    "input",
    {
      type: "checkbox",
      checked: demoMode,
      onChange: (e) => setDemoMode(e.target.checked),
      style: { width: "auto" }
    }
  ), "\u0414\u0435\u043C\u043E-\u0440\u0435\u0436\u0438\u043C (\u0431\u0435\u0437 \u0437\u0430\u043F\u0440\u043E\u0441\u0430 \u043A PKK API \u0420\u043E\u0441\u0440\u0435\u0435\u0441\u0442\u0440\u0430)"), !demoMode && /* @__PURE__ */ React.createElement(Alert, { type: "warn" }, "\u0420\u0435\u0430\u043B\u044C\u043D\u044B\u0439 \u0437\u0430\u043F\u0440\u043E\u0441 \u043A PKK API \u0420\u043E\u0441\u0440\u0435\u0435\u0441\u0442\u0440\u0430. \u0422\u0440\u0435\u0431\u0443\u0435\u0442\u0441\u044F \u0438\u043D\u0442\u0435\u0440\u043D\u0435\u0442."), msg && /* @__PURE__ */ React.createElement(Alert, { type: msg.type }, msg.text), /* @__PURE__ */ React.createElement("div", { className: "btn-row" }, /* @__PURE__ */ React.createElement("button", { className: "btn", style: { flex: 1 }, onClick: run, disabled: loading }, loading ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement(Spin, null), " \u0410\u043D\u0430\u043B\u0438\u0437\u0438\u0440\u0443\u0435\u043C...") : "\u{1F5FA} \u0417\u0430\u043F\u0443\u0441\u0442\u0438\u0442\u044C \u043A\u0430\u0434\u0430\u0441\u0442\u0440\u043E\u0432\u0443\u044E \u0441\u0432\u0435\u0440\u043A\u0443"))));
}
function ApprovalsTab({ project, cadResult, onGenerate }) {
  const [selected, setSelected] = useState(/* @__PURE__ */ new Set());
  const [loading, setLoading] = useState(false);
  const [statuses, setStatuses] = useState({});
  const approvals = (cadResult == null ? void 0 : cadResult.approvals) || [];
  const summary = (cadResult == null ? void 0 : cadResult.summary) || {};
  const dsInfo = DATA_SOURCE_INFO[summary.data_source] || null;
  const roiHours = (summary.total_approvals || 0) * ROI_HOURS_PER_APPROVAL;
  const roiDays = Math.round(roiHours / 8 * 10) / 10;
  const toggleSel = (id) => {
    setSelected((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };
  const selectAll = () => setSelected(new Set(approvals.map((a) => a.id)));
  const clearSel = () => setSelected(/* @__PURE__ */ new Set());
  async function generate() {
    setLoading(true);
    const ids = selected.size ? [...selected] : null;
    const data = await api.generate(project.project_id, ids);
    setLoading(false);
    if (data.success) onGenerate(data);
  }
  async function updateStatus(approval, status) {
    setStatuses((s) => __spreadProps(__spreadValues({}, s), { [approval.id]: status }));
    await api.patchApproval(project.project_id, approval.id, { status });
  }
  return /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("div", { className: "stats" }, /* @__PURE__ */ React.createElement("div", { className: "stat crit" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, summary.critical_approvals || 0), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u043A\u0440\u0438\u0442\u0438\u0447\u043D\u043E")), /* @__PURE__ */ React.createElement("div", { className: "stat imp" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, summary.important_approvals || 0), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u0432\u0430\u0436\u043D\u043E")), /* @__PURE__ */ React.createElement("div", { className: "stat ok" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, summary.total_approvals || 0), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u0432\u0441\u0435\u0433\u043E")), /* @__PURE__ */ React.createElement("div", { className: "stat info" }, /* @__PURE__ */ React.createElement("div", { className: "stat-val" }, summary.critical_path_days || 0), /* @__PURE__ */ React.createElement("div", { className: "stat-lbl" }, "\u0434\u043D\u0435\u0439 \u043A\u0440\u0438\u0442.\u043F\u0443\u0442\u044C"))), dsInfo && /* @__PURE__ */ React.createElement(Alert, { type: dsInfo.type }, dsInfo.text), summary.total_approvals > 0 && /* @__PURE__ */ React.createElement("div", { className: "card", style: { borderLeft: "3px solid var(--olive)" } }, /* @__PURE__ */ React.createElement("div", { className: "card-title" }, "\u042D\u043A\u043E\u043D\u043E\u043C\u0438\u044F \u0432\u0440\u0435\u043C\u0435\u043D\u0438 (\u043E\u0446\u0435\u043D\u043E\u0447\u043D\u043E)"), /* @__PURE__ */ React.createElement("div", { style: { display: "flex", alignItems: "baseline", gap: 8 } }, /* @__PURE__ */ React.createElement("span", { style: { fontSize: 26, fontWeight: 700, fontFamily: "'Montserrat',sans-serif", color: "var(--olive)" } }, "~" + roiHours + " \u0447"), /* @__PURE__ */ React.createElement("span", { style: { fontSize: 12, color: "var(--muted)" } }, "(~" + roiDays + " \u0440\u0430\u0431. \u0434\u043D. \u0438\u043D\u0436\u0435\u043D\u0435\u0440\u0430)")), /* @__PURE__ */ React.createElement("p", { style: { fontSize: 11, color: "var(--muted)", marginTop: 6 } }, "\u041D\u0430 \u0440\u0443\u0447\u043D\u043E\u0439 \u043F\u043E\u0434\u0431\u043E\u0440 \u0438\u043D\u0441\u0442\u0430\u043D\u0446\u0438\u0439, \u0441\u0432\u0435\u0440\u043A\u0443 \u0442\u0440\u0435\u0431\u043E\u0432\u0430\u043D\u0438\u0439 \u0438 \u043F\u043E\u0434\u0433\u043E\u0442\u043E\u0432\u043A\u0443 \u043F\u0438\u0441\u0435\u043C \u0434\u043B\u044F " + summary.total_approvals + " \u0441\u043E\u0433\u043B\u0430\u0441\u043E\u0432\u0430\u043D\u0438\u0439")), /* @__PURE__ */ React.createElement("div", { className: "btn-row", style: { marginBottom: 10 } }, /* @__PURE__ */ React.createElement("button", { className: "btn btn-sm btn-ghost", onClick: selectAll }, "\u2713 \u0412\u0441\u0435"), /* @__PURE__ */ React.createElement("button", { className: "btn btn-sm btn-ghost", onClick: clearSel }, "\u2717 \u0421\u043D\u044F\u0442\u044C"), /* @__PURE__ */ React.createElement("span", { style: { fontSize: 11, color: "var(--muted)", marginLeft: "auto", alignSelf: "center" } }, "\u0412\u044B\u0431\u0440\u0430\u043D\u043E: ", selected.size || "\u0432\u0441\u0435")), approvals.map((a) => {
    var _a;
    return /* @__PURE__ */ React.createElement(
      "div",
      {
        key: a.id,
        className: `approval-item pri-${a.priority}${selected.has(a.id) ? " selected" : ""}`,
        onClick: () => toggleSel(a.id)
      },
      /* @__PURE__ */ React.createElement("div", { className: "ai-header" }, /* @__PURE__ */ React.createElement("span", { className: `priority-badge ${PRI_CLASS[a.priority] || ""}` }, PRI_LABELS[a.priority] || a.priority), /* @__PURE__ */ React.createElement("span", { className: "ai-name" }, a.instance_name), /* @__PURE__ */ React.createElement("span", { className: "ai-basis" }, a.legal_basis)),
      /* @__PURE__ */ React.createElement("div", { className: "ai-ref" }, a.intersection_ref),
      /* @__PURE__ */ React.createElement("div", { className: "ai-footer" }, /* @__PURE__ */ React.createElement("span", { className: "status-badge" }, statuses[a.id] || a.status), a.review_days && /* @__PURE__ */ React.createElement("span", { style: { fontSize: 10, color: "var(--muted)" } }, "\u23F1 ", a.review_days, " \u0434\u043D."), /* @__PURE__ */ React.createElement("span", { style: { fontSize: 10, color: "var(--muted)", marginLeft: "auto" } }, "\u{1F4CE} ", ((_a = a.attachments) == null ? void 0 : _a.length) || 0, " \u043F\u0440\u0438\u043B."), /* @__PURE__ */ React.createElement(
        "select",
        {
          style: { width: "auto", padding: "2px 6px", fontSize: 11 },
          value: statuses[a.id] || a.status,
          onChange: (e) => {
            e.stopPropagation();
            updateStatus(a, e.target.value);
          },
          onClick: (e) => e.stopPropagation()
        },
        /* @__PURE__ */ React.createElement("option", { value: "pending" }, "\u041E\u0436\u0438\u0434\u0430\u043D\u0438\u0435"),
        /* @__PURE__ */ React.createElement("option", { value: "sent" }, "\u041E\u0442\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u043E"),
        /* @__PURE__ */ React.createElement("option", { value: "approved" }, "\u0421\u043E\u0433\u043B\u0430\u0441\u043E\u0432\u0430\u043D\u043E"),
        /* @__PURE__ */ React.createElement("option", { value: "rejected" }, "\u041E\u0442\u043A\u043B\u043E\u043D\u0435\u043D\u043E")
      ))
    );
  }), /* @__PURE__ */ React.createElement(
    "button",
    {
      className: "btn btn-green",
      style: { width: "100%", marginTop: 10 },
      onClick: generate,
      disabled: loading || !approvals.length
    },
    loading ? /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement(Spin, null), " \u0413\u0435\u043D\u0435\u0440\u0438\u0440\u0443\u0435\u043C...") : "\u{1F4C4} \u0421\u0433\u0435\u043D\u0435\u0440\u0438\u0440\u043E\u0432\u0430\u0442\u044C PDF-\u043A\u043E\u043C\u043F\u043B\u0435\u043A\u0442\u044B"
  ));
}
function App() {
  const [tab, setTab] = useState("upload");
  const [project, setProject] = useState(null);
  const [cadResult, setCadResult] = useState(null);
  const [genResult, setGenResult] = useState(null);
  const [step, setStep] = useState(0);
  const route = (project == null ? void 0 : project.route) || [];
  const parcels = (cadResult == null ? void 0 : cadResult.parcels) || [];
  const intersections = (cadResult == null ? void 0 : cadResult.intersections) || [];
  function onUploaded(data) {
    setProject(data);
    setCadResult(null);
    setGenResult(null);
    setStep(1);
    setTab("analyze");
  }
  function onAnalyzed(data) {
    setCadResult(data);
    setStep(2);
    setTab("approvals");
  }
  function onGenerate(data) {
    setGenResult(data);
    setStep(3);
  }
  const TABS = [
    { key: "upload", label: "1 \u0417\u0430\u0433\u0440\u0443\u0437\u043A\u0430" },
    { key: "analyze", label: "2 \u0410\u043D\u0430\u043B\u0438\u0437" },
    { key: "approvals", label: "3 \u0421\u043E\u0433\u043B\u0430\u0441\u043E\u0432\u0430\u043D\u0438\u044F" }
  ];
  return /* @__PURE__ */ React.createElement("div", { className: "app" }, /* @__PURE__ */ React.createElement("div", { className: "header" }, /* @__PURE__ */ React.createElement("span", { className: "logo" }, "\u0410\u0421 \u0421\u041A\u041B"), /* @__PURE__ */ React.createElement("span", { className: "badge" }, "v2.0"), /* @__PURE__ */ React.createElement("span", { style: { color: "var(--header-muted)", fontSize: 13 } }, "\u041E\u0442 \u0442\u0440\u0430\u0441\u0441\u044B \u0434\u043E \u043F\u0430\u043A\u0435\u0442\u0430 \u0441\u043E\u0433\u043B\u0430\u0441\u043E\u0432\u0430\u043D\u0438\u0439 \u2014 \u0437\u0430 \u043C\u0438\u043D\u0443\u0442\u044B \u0432\u043C\u0435\u0441\u0442\u043E \u043D\u0435\u0434\u0435\u043B\u044C"), /* @__PURE__ */ React.createElement("div", { className: "header-right" }, project && /* @__PURE__ */ React.createElement("span", { style: { fontSize: 12, color: "var(--header-muted)" } }, "\u{1F4CB} ", project.project_name), genResult && /* @__PURE__ */ React.createElement(
    "a",
    {
      href: genResult.download_url,
      target: "_blank",
      className: "btn btn-green btn-sm"
    },
    "\u2B07 \u0421\u043A\u0430\u0447\u0430\u0442\u044C PDF"
  ), /* @__PURE__ */ React.createElement("span", { className: "status-dot" }))), /* @__PURE__ */ React.createElement("div", { className: "main" }, /* @__PURE__ */ React.createElement("div", { className: "sidebar" }, /* @__PURE__ */ React.createElement("div", { className: "sidebar-tabs" }, TABS.map((t) => /* @__PURE__ */ React.createElement(
    "div",
    {
      key: t.key,
      className: `tab${tab === t.key ? " active" : ""}`,
      onClick: () => tab !== t.key && (step >= TABS.findIndex((x) => x.key === t.key) || true) && setTab(t.key)
    },
    t.label
  ))), /* @__PURE__ */ React.createElement("div", { className: "sidebar-content" }, /* @__PURE__ */ React.createElement("div", { className: "steps" }, [0, 1, 2, 3].map((i) => /* @__PURE__ */ React.createElement("div", { key: i, className: `step${i < step ? " done" : i === step ? " active" : ""}` }))), tab === "upload" && /* @__PURE__ */ React.createElement(UploadTab, { onUploaded }), tab === "analyze" && (project ? /* @__PURE__ */ React.createElement(AnalysisTab, { project, onAnalyzed }) : /* @__PURE__ */ React.createElement(Alert, { type: "info" }, "\u0421\u043D\u0430\u0447\u0430\u043B\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u0435 \u043C\u0430\u0440\u0448\u0440\u0443\u0442")), tab === "approvals" && (cadResult ? /* @__PURE__ */ React.createElement(ApprovalsTab, { project, cadResult, onGenerate }) : /* @__PURE__ */ React.createElement(Alert, { type: "info" }, "\u0421\u043D\u0430\u0447\u0430\u043B\u0430 \u0432\u044B\u043F\u043E\u043B\u043D\u0438\u0442\u0435 \u043A\u0430\u0434\u0430\u0441\u0442\u0440\u043E\u0432\u0443\u044E \u0441\u0432\u0435\u0440\u043A\u0443")))), /* @__PURE__ */ React.createElement(
    MapView,
    {
      route,
      parcels,
      intersections
    }
  )));
}
ReactDOM.createRoot(document.getElementById("root")).render(/* @__PURE__ */ React.createElement(App, null));
