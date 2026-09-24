/* TRADING_AI front end. Plain JavaScript, no framework, no CDN. */
(function () {
  "use strict";

  var S = {};                 // last /api/status payload
  var pollTimer = null;

  /* ------------------------------------------------------------ util */
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  function esc(s) {
    return String(s === null || s === undefined ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function rupee(v) {
    if (v === null || v === undefined || isNaN(v)) return "-";
    return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  function pct(v, d) {
    if (v === null || v === undefined || isNaN(v)) return "-";
    return (v > 0 ? "+" : "") + Number(v).toFixed(d === undefined ? 2 : d) + "%";
  }
  function cls(v) { return v > 0 ? "up" : v < 0 ? "down" : "neu"; }

  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok) {
          var err = new Error(j.error || j.message || ("HTTP " + r.status));
          err.suggestions = j.suggestions || [];
          throw err;
        }
        return j;
      });
    });
  }
  function post(path, body) {
    return api(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
  }
  function toast(msg, kind) {
    var t = el("div", "tm " + (kind || ""), esc(msg));
    $("#toast").appendChild(t);
    setTimeout(function () { t.remove(); }, kind === "err" ? 9000 : 5000);
  }
  function modal(html) { $("#modalBody").innerHTML = html; $("#modal").classList.remove("hidden"); }
  $("#modalClose").onclick = function () { $("#modal").classList.add("hidden"); };

  function table(cols, rows, rowFn) {
    var h = "<table><thead><tr>" + cols.map(function (c) {
      return "<th" + (c.num ? " class='num'" : "") + ">" + esc(c.label) + "</th>";
    }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (r) { h += rowFn(r); });
    return h + "</tbody></table>";
  }

  /* ------------------------------------------------------ navigation */
  $$(".nav").forEach(function (n) {
    n.onclick = function () {
      $$(".nav").forEach(function (x) { x.classList.remove("active"); });
      $$(".page").forEach(function (x) { x.classList.remove("active"); });
      n.classList.add("active");
      $("#page-" + n.dataset.page).classList.add("active");
      load(n.dataset.page);
    };
  });
  function go(page) {
    var n = $$(".nav").filter(function (x) { return x.dataset.page === page; })[0];
    if (n) n.click();
  }

  function load(page) {
    if (page === "dashboard") refreshStatus();
    if (page === "heatmap") loadHeatmap();
    if (page === "trades") loadTrades();
    if (page === "backtest") loadBacktest();
    if (page === "sources") loadSources();
    if (page === "settings") loadSettings();
    if (page === "telegram") loadTelegram();
    if (page === "backups") loadBackups();
    if (page === "logs") loadLogs("app");
  }

  setInterval(function () {
    $("#clock").textContent = new Date().toLocaleString("en-IN",
      { dateStyle: "medium", timeStyle: "short" });
  }, 1000);

  /* ---------------------------------------------------------- status */
  function refreshStatus() {
    api("/api/status").then(function (s) {
      S = s;
      renderGate(s.gate);
      var n = s.nifty;
      $("#c-nifty").textContent = n ? Number(n.value).toLocaleString("en-IN",
        { maximumFractionDigits: 2 }) : "—";
      $("#c-nifty").className = "v " + (n ? cls(n.change_pct) : "");
      $("#c-niftysub").textContent = n ? (pct(n.change_pct) + " · " + n.as_of)
        : "No index data yet";

      $("#c-market").textContent = s.market || "Unknown";
      $("#c-market").className = "v small " + (
        /bull/i.test(s.market || "") ? "up" : /bear/i.test(s.market || "") ? "down" : "neu");
      $("#c-marketsub").textContent = "Based on NIFTY 50 21-session trend";

      var b = s.breadth;
      $("#c-breadth").textContent = b ? (b.advances + " / " + b.declines) : "—";
      $("#c-breadth").className = "v " + (b ? cls(b.advances - b.declines) : "");
      $("#c-breadthsub").textContent = b
        ? (b.pct_advancing + "% advancing of " + b.total) : "Needs two sessions";

      var st = s.strongest_sector, wk = s.weakest_sector;
      $("#c-strong").textContent = st ? st.index_name.replace("NIFTY ", "") : "—";
      $("#c-strong").className = "v small up";
      $("#c-strongsub").textContent = st ? pct(st.ret_21d) + " (21 sessions)" : "";
      $("#c-weak").textContent = wk ? wk.index_name.replace("NIFTY ", "") : "—";
      $("#c-weak").className = "v small down";
      $("#c-weaksub").textContent = wk ? pct(wk.ret_21d) + " (21 sessions)" : "";

      $("#c-update").textContent = s.last_update || "Never";
      $("#c-updatesub").textContent = s.coverage.sessions + " confirmed sessions";

      var dbh = s.database.healthy;
      $("#c-db").textContent = dbh ? "Healthy" : "Problem";
      $("#c-db").className = "v small " + (dbh ? "ok" : "bad");
      $("#c-dbsub").textContent = s.database.size_mb + " MB · " +
        (s.disk && s.disk.free_gb !== undefined ? s.disk.free_gb + " GB free" : "");

      var blocked = s.gate.status !== "ok";
      $("#c-signal").textContent = blocked ? "DISABLED" : "ACTIVE";
      $("#c-signal").className = "v small " + (blocked ? "bad" : "ok");
      $("#c-signalsub").textContent = blocked
        ? "Recommendations are switched off" : "Data checks passed";

      if (s.app_version) {
        $("#appVersion").textContent = "Version " + s.app_version;
      }
      var c = s.coverage;
      $("#coverage").innerHTML =
        kv("Price rows", Number(c.rows).toLocaleString("en-IN")) +
        kv("Stocks", c.symbols) +
        kv("History", (c.start || "—") + "  to  " + (c.end || "—")) +
        kv("Confirmed sessions", c.sessions) +
        kv("Index rows", Number(c.index_rows).toLocaleString("en-IN") +
          " across " + c.indices + " indices") +
        (c.depth_note ? kv("How much history",
          "<span class='muted'>" + esc(c.depth_note) + "</span>") : "") +
        (s.synthetic_rows ? kv("Practice rows",
          "<span class='wrn'>" + s.synthetic_rows + " (never tradeable)</span>") : "");

      var cal = s.calibration;
      $("#calib").innerHTML = cal.ready
        ? kv("Out-of-sample observations", Number(cal.observations).toLocaleString("en-IN")) +
        kv("Score buckets", cal.buckets) +
        kv("Buckets with enough data", cal.usable_buckets + " of " + cal.buckets) +
        kv("Minimum per bucket", cal.min_required) +
        kv("Status", cal.note)
        : kv("Status", "<span class='wrn'>" + esc(cal.note) + "</span>");

      $("#miniheat").innerHTML = (s.heatmap || []).slice(0, 12).map(function (r) {
        return hcell(r, band(r.ret_21d));
      }).join("") || "<div class='empty'>No index data yet.</div>";
    }).catch(function (e) { toast(e.message, "err"); });
  }

  function kv(k, v) {
    return "<div class='kk'>" + esc(k) + "</div><div>" + v + "</div>";
  }

  function renderGate(g) {
    var box = $("#gateBanner");
    if (!g || g.status === "ok") {
      box.innerHTML = "<div class='banner good'><h4>Data checks passed</h4>" +
        "<p>Price history is continuous across confirmed NSE sessions. " +
        "Trade ideas are available.</p></div>";
      return;
    }
    var h = "";
    (g.reasons || []).forEach(function (r) {
      h += "<div class='banner " + (r.level === "ERROR" ? "error" : "warn") + "'>" +
        "<h4>" + esc(r.title) + "</h4><p>" + esc(r.detail) + "</p>" +
        "<div class='bbtns'>" + actionBtn(r.action) +
        "<button class='btn ghost' data-details='1'>VIEW DETAILS</button>" +
        "<button class='btn ghost' data-retry='1'>RETRY</button></div></div>";
    });
    box.innerHTML = h;
    $$("[data-details]", box).forEach(function (b) {
      b.onclick = function () { go("logs"); loadLogs("gaps"); };
    });
    $$("[data-retry]", box).forEach(function (b) {
      b.onclick = function () { refreshStatus(); toast("Re-checked."); };
    });
    $$("[data-run]", box).forEach(bindRun);
  }

  function actionBtn(a) {
    if (a === "REPAIR DATA") return "<button class='btn' data-run='repair'>REPAIR DATA</button>";
    if (a === "UPDATE NOW") return "<button class='btn' data-run='update'>UPDATE NOW</button>";
    if (a === "REVIEW CORPORATE ACTIONS")
      return "<button class='btn' data-log-jump='corporate'>REVIEW CORPORATE ACTIONS</button>";
    return "";
  }

  /* ------------------------------------------------------------ jobs */
  function bindRun(b) {
    b.onclick = function () {
      post("/api/run/" + b.dataset.run)
        .then(function (j) { toast("Started: " + j.name); watch(); })
        .catch(function (e) { toast(e.message, "err"); });
    };
  }
  $$("[data-run]").forEach(bindRun);
  $("#bigButton").onclick = function () {
    post("/api/run/update").then(function (j) {
      toast("Started: " + j.name); watch();
    }).catch(function (e) { toast(e.message, "err"); });
  };
  $("#cancelJob").onclick = function () {
    var id = $("#jobBox").dataset.job;
    if (id) post("/api/job/" + id + "/cancel").then(function () { toast("Stopping..."); });
  };

  function watch() {
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      api("/api/job").then(function (j) {
        if (!j || j.status === "idle") { hideJob(); return; }
        showJob(j);
        if (j.status !== "running") {
          clearInterval(pollTimer); pollTimer = null;
          setTimeout(hideJob, 3500);
          if (j.status === "error") {
            toast(j.message, "err");
          } else if (j.status === "done") {
            toast(j.name + " finished.", "ok");
            refreshStatus();
            var p = $$(".page.active")[0];
            if (p) load(p.id.replace("page-", ""));
          }
        }
      }).catch(function () { });
    }, 900);
  }
  function showJob(j) {
    var box = $("#jobBox");
    box.classList.remove("hidden");
    box.dataset.job = j.id || "";
    $("#jobName").textContent = j.name || "";
    $("#jobFill").style.width = (j.percent || 0) + "%";
    $("#jobMsg").textContent = j.message || "";
    $("#jobCount").textContent = j.total
      ? ("Step " + j.current + " of " + j.total + "  ·  " + j.percent + "%") : "";
    $("#bigButton").disabled = (j.status === "running");
  }
  function hideJob() {
    $("#jobBox").classList.add("hidden");
    $("#bigButton").disabled = false;
  }

  /* --------------------------------------------------------- heatmap */
  function band(v) {
    if (v === null || v === undefined || isNaN(v)) return "unknown";
    if (v >= 5) return "strong_bull";
    if (v >= 1.5) return "bull";
    if (v > -1.5) return "neutral";
    if (v > -5) return "bear";
    return "strong_bear";
  }
  function hcell(r, b) {
    return "<div class='hcell " + (r.band || b) + "' data-idx='" + esc(r.index_name) + "'>" +
      "<div class='n'>" + esc(r.label || r.index_name) + "</div>" +
      "<div class='p'>" + pct(r.ret_21d, 1) + "</div>" +
      "<div class='d'>1d " + pct(r.ret_1d, 1) + " · 5d " + pct(r.ret_5d, 1) + "</div></div>";
  }
  function loadHeatmap() {
    api("/api/heatmap").then(function (h) {
      if (h.message) {
        $("#heatgrid").innerHTML = "<div class='empty'>" + esc(h.message) + "</div>";
        $("#broadgrid").innerHTML = ""; return;
      }
      $("#heatgrid").innerHTML = h.sectors.map(function (r) { return hcell(r); }).join("")
        || "<div class='empty'>" + esc(h.message ||
          "No sector indices downloaded yet.") + "</div>";
      $("#broadgrid").innerHTML = h.broad.map(function (r) { return hcell(r); }).join("");
      $$(".hcell").forEach(function (c) {
        c.onclick = function () { sectorStocks(c.dataset.idx); };
      });
    }).catch(function (e) { toast(e.message, "err"); });
  }
  function sectorStocks(name) {
    api("/api/sector/" + encodeURIComponent(name) + "/stocks").then(function (d) {
      $("#sectorStocksPanel").style.display = "block";
      $("#sectorStocksTitle").textContent = name + " — strongest to weakest";
      if (!d.stocks.length) {
        $("#sectorStocks").innerHTML = "<div class='empty'>" +
          esc(d.message || "No ranked stocks in this sector yet.") + "</div>";
        return;
      }
      $("#sectorStocks").innerHTML = table(
        [{ label: "#" }, { label: "Stock" }, { label: "Sector" },
        { label: "Price", num: 1 }, { label: "Score", num: 1 },
        { label: "21d", num: 1 }, { label: "63d", num: 1 },
        { label: "RSI", num: 1 }, { label: "Trend" }],
        d.stocks, function (r) {
          return "<tr><td>" + r.rank + "</td>" +
            "<td class='clickable' data-sym='" + esc(r.symbol) + "'>" + esc(r.symbol) + "</td>" +
            "<td>" + esc(r.sector || "-") + "</td>" +
            "<td class='num'>" + (r.close ? r.close.toFixed(2) : "-") + "</td>" +
            "<td class='num'>" + (r.score === null ? "-" : r.score.toFixed(2)) + "</td>" +
            "<td class='num " + cls(r.ret_21 * 100) + "'>" + pct(r.ret_21 * 100, 1) + "</td>" +
            "<td class='num " + cls(r.ret_63 * 100) + "'>" + pct(r.ret_63 * 100, 1) + "</td>" +
            "<td class='num'>" + (r.rsi14 ? r.rsi14.toFixed(0) : "-") + "</td>" +
            "<td>" + (r.above_sma50 && r.above_sma200 ? "Up"
              : (!r.above_sma50 && !r.above_sma200 ? "Down" : "Side")) + "</td></tr>";
        });
      bindSymbols();
      $("#sectorStocksPanel").scrollIntoView({ behavior: "smooth" });
    }).catch(function (e) { toast(e.message, "err"); });
  }

  function bindSymbols() {
    $$("[data-sym]").forEach(function (t) {
      t.onclick = function () { go("chart"); $("#chartSym").value = t.dataset.sym; drawChart(); };
    });
  }

  /* ---------------------------------------------------------- trades */
  function loadTrades() {
    api("/api/settings").then(function (s) {
      var v = s.settings;
      $("#r-capital").value = v.capital; $("#r-risk").value = v.risk_per_trade_pct;
      $("#r-pos").value = v.max_positions; $("#r-daily").value = v.max_daily_loss_pct;
      $("#r-dir").value = v.direction; $("#r-stop").value = v.stop_method;
    });
    loadConfirmationEvidence();
    api("/api/recommendations").then(function (d) {
      if (d.blocked) {
        $("#tradeBlocked").innerHTML = "<div class='banner error'>" +
          "<h4>" + esc(d.reason) + "</h4><p>" +
          ((d.issues || []).map(function (i) { return esc(i.detail); }).join(" ")
            || "No trade ideas can be produced from incomplete data.") +
          "</p><div class='bbtns'><button class='btn' data-run='repair'>REPAIR DATA</button>" +
          "<button class='btn ghost' data-run='update'>UPDATE NOW</button></div></div>";
        $$("[data-run]", $("#tradeBlocked")).forEach(bindRun);
        $("#longs").innerHTML = ""; $("#shorts").innerHTML = "";
        $("#portfolio").innerHTML = "";
        return;
      }
      var q = d.quarantined || {};
      $("#tradeBlocked").innerHTML = q.count
        ? "<div class='banner warn'><h4>" + q.count +
          " stock(s) left out today</h4><p>" + esc(q.note) +
          "</p><p class='muted small'>" +
          esc(Object.keys(q.reasons || {}).sort().map(function (k) {
            return k + ": " + q.reasons[k];
          }).join(" · ")) + "</p></div>"
        : "";
      $("#longs").innerHTML = d.long.length ? d.long.map(tcard).join("")
        : "<div class='empty'>No long candidate passes the filters today.</div>";
      $("#shorts").innerHTML = d.short.length ? d.short.map(tcard).join("")
        : "<div class='empty'>No short candidate passes the filters today.</div>";
      var p = d.portfolio || {};
      $("#portfolio").innerHTML =
        item("Capital", rupee(p.capital)) +
        item("Positions", p.positions) +
        item("Deployed", rupee(p.capital_deployed) + " (" + p.capital_deployed_pct + "%)") +
        item("Cash left", rupee(p.cash_remaining)) +
        item("At risk", rupee(p.capital_at_risk) + " (" + p.capital_at_risk_pct + "%)") +
        item("Worst-case loss", rupee(p.max_planned_loss)) +
        item("If targets hit", rupee(p.expected_profit)) +
        item("Portfolio return", pct(p.expected_portfolio_return_pct)) +
        (p.warning ? "<div class='banner warn' style='grid-column:1/-1'><p>" +
          esc(p.warning) + "</p></div>" : "");
      bindSymbols();
    }).catch(function (e) { toast(e.message, "err"); });
  }
  function item(l, v) {
    return "<div class='item'><span class='kk'>" + esc(l) + "</span><b>" + v + "</b></div>";
  }
  function tcard(c) {
    var pr = c.probability;
    var probHtml = pr.available
      ? "<div class='x'>" + pr.display + "</div><div class='evi'>" + esc(pr.evidence) + "</div>"
      : "<div class='insuff'>Insufficient data</div><div class='evi'>" + esc(pr.evidence) + "</div>";
    return "<div class='tcard " + c.side + "'><div class='hd'>" +
      "<span class='sym' data-sym='" + esc(c.symbol) + "'>" + esc(c.symbol) + "</span>" +
      "<span class='tag " + c.signal + "'>" + c.signal + "</span>" +
      "<span class='sec'>" + esc(c.sector) + " · sector " + esc(c.sector_strength) +
      " · market " + esc(c.market_alignment) + "</span></div>" +
      "<div class='tgrid'>" +
      cell("Last price", "₹" + c.last_price) +
      cell("Entry", "₹" + c.entry) +
      cell("Stop loss", "₹" + c.stop) +
      cell("Target", "₹" + c.target) +
      cell("R : R", "1 : " + c.rr) +
      cell("Quantity", c.quantity) +
      cell("Position", rupee(c.position_value)) +
      cell("Capital at risk", rupee(c.capital_at_risk)) +
      cell("If target hit", "<span class='up'>" + rupee(c.expected_profit) + "</span>") +
      cell("If stopped out", "<span class='down'>-" + rupee(c.expected_loss) + "</span>") +
      "<div><div class='l'>Probability</div>" + probHtml + "</div>" +
      cell("Expected move", c.expected_move_pct === null ? "—" : pct(c.expected_move_pct)) +
      cell("RSI", c.rsi === null ? "-" : c.rsi) +
      cell("Trend", c.trend) +
      cell("Rel. volume", c.relative_volume === null ? "-" : c.relative_volume + "x") +
      cell("Volume change", c.volume_change_pct === null ? "-" : pct(c.volume_change_pct, 0)) +
      cell("Delivery %", c.delivery_pct === null || c.delivery_pct === undefined
        ? "-" : Number(c.delivery_pct).toFixed(1) + "%") +
      cell("Score", c.score) +
      "</div>" + confirmHtml(c) + "</div>";
  }

  // Confirmation checks. Shown as evidence you can read, never folded into
  // the probability number.
  function confirmHtml(c) {
    var list = c.confirmations || [];
    if (!list.length) return "";
    var s = c.confirmation_summary || {};
    var icon = { PASS: "✓", FAIL: "✗", UNKNOWN: "?" };
    var rows = list.map(function (k) {
      return "<li class='chk " + k.status.toLowerCase() + "'>" +
        "<span class='ic'>" + icon[k.status] + "</span>" +
        "<span class='lb'>" + esc(k.label) + "</span>" +
        "<span class='dt'>" + esc(k.detail) + "</span></li>";
    }).join("");
    return "<details class='confirms'><summary>" +
      esc(s.text || "Confirmation checks") +
      (s.failed_labels && s.failed_labels.length
        ? " — missing: " + esc(s.failed_labels.join(", ")) : "") +
      "</summary><ul>" + rows + "</ul>" +
      "<p class='muted small'>These checks are shown as evidence. They do " +
      "not change the probability above, which comes only from measured " +
      "out-of-sample results.</p></details>";
  }
  function loadConfirmationEvidence() {
    api("/api/confirmations").then(function (d) {
      if (!d.available) {
        $("#confEvidence").innerHTML = "<div class='empty'>" +
          esc(d.message) + "</div>";
        return;
      }
      var h = "<p class='muted small'>" + esc(d.summary) + " Measured " +
        esc(String(d.built_at || "")) + ".</p>";
      ["LONG", "SHORT"].forEach(function (side) {
        var rows = (d.sides || {})[side] || [];
        if (!rows.length) return;
        h += "<h4 class='" + side.toLowerCase() + "'>" + side + "</h4>" +
          "<table class='tbl'><thead><tr><th>Check</th>" +
          "<th>Worked when it passed</th><th>When it failed</th>" +
          "<th>Difference</th><th>Times seen</th><th>Verdict</th>" +
          "</tr></thead><tbody>";
        rows.forEach(function (r) {
          var e = r.edge_pct;
          var klass = e === null ? "" : (e > 1 ? "up" : e < -1 ? "down" : "");
          h += "<tr><td>" + esc(r.label) + "</td>" +
            "<td>" + (r.hit_pass_pct === null ? "—" :
              Number(r.hit_pass_pct).toFixed(1) + "%") + "</td>" +
            "<td>" + (r.hit_fail_pct === null ? "—" :
              Number(r.hit_fail_pct).toFixed(1) + "%") + "</td>" +
            "<td class='" + klass + "'>" + (e === null ? "—" :
              (e > 0 ? "+" : "") + Number(e).toFixed(1) + " pts") + "</td>" +
            "<td>" + Number(r.n_pass).toLocaleString("en-IN") + " / " +
              Number(r.n_fail).toLocaleString("en-IN") + "</td>" +
            "<td>" + esc(r.verdict) + "</td></tr>";
        });
        h += "</tbody></table>";
      });
      h += "<p class='muted small'>" + esc(d.note) + "</p>";
      $("#confEvidence").innerHTML = h;
    }).catch(function () { });
  }

  function cell(l, v) {
    return "<div><div class='l'>" + esc(l) + "</div><div class='x'>" + v + "</div></div>";
  }
  $("#saveRisk").onclick = function () {
    post("/api/settings", {
      capital: +$("#r-capital").value, risk_per_trade_pct: +$("#r-risk").value,
      max_positions: +$("#r-pos").value, max_daily_loss_pct: +$("#r-daily").value,
      direction: $("#r-dir").value, stop_method: $("#r-stop").value
    }).then(function (r) {
      (r.warnings || []).forEach(function (w) { toast(w, "err"); });
      toast("Risk settings applied.", "ok"); loadTrades();
    }).catch(function (e) { toast(e.message, "err"); });
  };

  /* ---------------------------------------------------------- charts */
  var chartRange = "1Y";
  $$(".rb").forEach(function (b) {
    b.onclick = function () {
      $$(".rb").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active"); chartRange = b.dataset.r; drawChart();
    };
  });
  $("#loadChart").onclick = drawChart;
  var symbolsLoaded = false;
  function loadSymbolList() {
    if (symbolsLoaded) return;
    symbolsLoaded = true;
    api("/api/symbols").then(function (d) {
      $("#symbolList").innerHTML = (d.symbols || []).map(function (s) {
        return "<option value='" + esc(s.symbol) + "'>";
      }).join("");
    }).catch(function () { symbolsLoaded = false; });
  }
  loadSymbolList();

  $("#chartSym").addEventListener("keydown", function (e) {
    if (e.key === "Enter") drawChart();
  });
  function drawChart() {
    var sym = ($("#chartSym").value || "").trim().toUpperCase();
    if (!sym) { toast("Type a stock symbol first."); return; }
    api("/api/chart/" + encodeURIComponent(sym) + "?range=" + chartRange)
      .then(function (d) {
        $("#chartInfo").innerHTML =
          item("Symbol", esc(d.symbol)) +
          item("Last close", "₹" + d.close[d.close.length - 1]) +
          item("Suggested entry", "₹" + d.entry) +
          item("Stop loss", "₹" + d.stop) +
          item("Target", "₹" + d.target) +
          item("Sessions shown", d.dates.length) +
          item("Prices", d.price_note || "As reported by NSE");
        window.drawCandles($("#cPrice"), d);
        window.drawVolume($("#cVol"), d);
        window.drawRsi($("#cRsi"), d);
        window.drawMacd($("#cMacd"), d);
        window._lastChart = d;
      }).catch(function (e) {
        var sg = e.suggestions || [];
        toast(sg.length ? e.message + " Try: " + sg.slice(0, 5).join(", ")
                        : e.message, "err");
      });
  }
  window.addEventListener("resize", function () {
    if (window._lastChart && $("#page-chart").classList.contains("active")) {
      var d = window._lastChart;
      window.drawCandles($("#cPrice"), d); window.drawVolume($("#cVol"), d);
      window.drawRsi($("#cRsi"), d); window.drawMacd($("#cMacd"), d);
    }
  });

  /* -------------------------------------------------------- backtest */
  function loadBacktest() {
    api("/api/backtest/latest").then(function (b) {
      if (!b.available) {
        $("#btResult").innerHTML = "<div class='empty'>" + esc(b.message) + "</div>";
        return;
      }
      var order = ["period", "trading_days", "rebalances", "trades",
        "initial_capital", "final_equity", "total_return_pct", "cagr_pct",
        "ann_vol_pct", "sharpe", "sortino", "max_drawdown_pct",
        "win_rate_pct", "avg_win_pct", "avg_loss_pct", "profit_factor",
        "expectancy_pct", "worst_day_pct", "worst_day_date",
        "total_costs", "cost_drag_pct",
        "benchmark_return_pct", "excess_vs_bench_pct"];
      var LABEL = {
        profit_factor: "Profit Factor (before costs)",
        total_costs: "Total Costs (₹)",
        cost_drag_pct: "Cost Drag % of Capital",
        total_return_pct: "Total Return % (after costs)",
        cagr_pct: "Return Per Year % (after costs)",
        max_drawdown_pct: "Worst Fall From Peak %",
        win_rate_pct: "Winning Trades %",
        worst_day_pct: "Worst Single Day %",
        worst_day_date: "Worst Single Day"
      };
      var h = "<div class='kv wide'>";
      order.forEach(function (k) {
        if (b[k] === undefined || b[k] === null) return;
        var v = typeof b[k] === "number" ? Number(b[k]).toLocaleString("en-IN",
          { maximumFractionDigits: 2 }) : b[k];
        h += item(LABEL[k] || k.replace(/_/g, " ").replace(/\b\w/g, function (m) {
          return m.toUpperCase();
        }), v);
      });
      h += "</div>";
      // Say out loud whether this strategy actually made money.
      if (typeof b.total_return_pct === "number") {
        var lost = b.total_return_pct <= 0;
        h = "<div class='banner " + (lost ? "warn" : "good") + "'><h4>" +
          (lost ? "This strategy lost money over the test period"
                : "This strategy made money over the test period") +
          "</h4><p>" +
          Number(b.total_return_pct).toFixed(2) + "% after all costs" +
          (typeof b.cost_drag_pct === "number"
            ? ", with costs alone taking " + Number(b.cost_drag_pct).toFixed(2) +
              "% of your capital" : "") +
          ". " + (lost ? "Do not trade it as it stands." : "") +
          "</p></div>" + h;
      }
      if (b.excluded_note) {
        h += "<p class='muted small'>" + esc(b.excluded_note) + "</p>";
      }
      if (b.is_synthetic) {
        h = "<div class='banner error'><h4>Practice data</h4><p>These numbers " +
          "come from synthetic data and mean nothing about the real market.</p></div>" + h;
      }
      $("#btResult").innerHTML = h;
      window.drawEquity($("#cEquity"), b.equity || []);
    }).catch(function (e) { toast(e.message, "err"); });
  }

  /* --------------------------------------------------------- sources */
  $("#probeBtn").onclick = function () {
    post("/api/sources/probe").then(function () {
      toast("Testing sources..."); watch();
    }).catch(function (e) { toast(e.message, "err"); });
  };
  function loadSources() {
    api("/api/sources").then(function (d) {
      var sm = d.summary || {};
      var when = d.generated_at ? d.generated_at.slice(0, 19).replace("T", " ")
        : "Never";
      if (d.age_hours !== null && d.age_hours !== undefined) {
        when += d.age_hours < 1 ? " (just now)"
          : d.age_hours < 48 ? " (" + Math.round(d.age_hours) + "h ago)"
            : " (" + Math.round(d.age_hours / 24) + " days ago)";
      }
      $("#srcSummary").innerHTML =
        item("Last tested", when) +
        item("Working", sm.ok !== undefined ? sm.ok : "—") +
        item("Failing", sm.fail !== undefined ? sm.fail : "—") +
        item("Blocked / refused", sm.blocked !== undefined ? sm.blocked : "—");

      $("#srcStale").innerHTML = d.stale
        ? "<div class='banner warn'><h4>These results are out of date</h4>" +
        "<p>This test last ran " + when + ". A source shown as FAILED here " +
        "may be working now — and if your downloads are running, it is. " +
        "Click TEST ALL SOURCES for the current picture.</p></div>"
        : "";

      if (!d.sources.length) {
        $("#srcTable").innerHTML = "<div class='empty'>No source test has been " +
          "run yet. Click TEST ALL SOURCES.</div>";
      } else {
        $("#srcTable").innerHTML = table(
          [{ label: "Source" }, { label: "Status" }, { label: "Latency", num: 1 },
          { label: "HTTP", num: 1 }, { label: "Purpose" }, { label: "Fallback" },
          { label: "Last checked" }],
          d.sources, function (r) {
            var k = /ok|success/i.test(r.status) ? "ok"
              : /block|403|forbidden/i.test(r.status) ? "wrn" : "bad";
            return "<tr><td>" + esc(r.source) + "</td>" +
              "<td class='" + k + "'>" + esc(r.status) + "</td>" +
              "<td class='num'>" + (r.latency_ms ? r.latency_ms + " ms" : "-") + "</td>" +
              "<td class='num'>" + (r.http || "-") + "</td>" +
              "<td>" + esc(r.purpose) + "</td><td>" + esc(r.fallback) + "</td>" +
              "<td>" + esc((r.checked_at || "").slice(0, 19)) + "</td></tr>";
          });
      }
      $("#srcFails").innerHTML = d.failures.length ? table(
        [{ label: "When" }, { label: "Source" }, { label: "What for" },
        { label: "Error" }, { label: "Fallback used" }],
        d.failures, function (r) {
          return "<tr><td>" + esc((r.time_utc || "").slice(0, 19)) + "</td><td>" +
            esc(r.source) + "</td><td>" + esc(r.capability) + "</td><td>" +
            esc(String(r.error).slice(0, 110)) + "</td><td>" +
            esc(r.fallback_used || "none") + "</td></tr>";
        }) : "<div class='empty'>No failures recorded.</div>";
    }).catch(function (e) { toast(e.message, "err"); });
  }

  /* -------------------------------------------------------- settings */
  var FIELDS = {
    setMoney: [
      ["capital", "Trading capital (₹)", "number"],
      ["risk_per_trade_pct", "Max risk per trade (%)", "number"],
      ["max_daily_loss_pct", "Max daily loss (%)", "number"],
      ["max_positions", "Max open positions", "number"],
      ["max_position_pct", "Max single position (% of capital)", "number"],
      ["atr_multiple", "Stop distance (× ATR)", "number"],
      ["stop_percent", "Stop distance (fixed %)", "number"],
      ["reward_multiple", "Target (× risk)", "number"],
      ["direction", "Trade direction", "select", ["both", "long", "short"]],
      ["stop_method", "Stop-loss method", "select", ["atr", "percent"]]
    ],
    setData: [
      ["history_period", "History to keep", "select",
        ["3m", "6m", "1y", "2y", "3y", "5y", "max"]],
      ["universe", "Universe", "select", ["nifty50", "nifty100", "nifty200"]],
      ["auto_backup", "Automatic backups", "select", [true, false]]
    ]
  };
  function loadSettings() {
    api("/api/settings").then(function (d) {
      Object.keys(FIELDS).forEach(function (box) {
        $("#" + box).innerHTML = FIELDS[box].map(function (f) {
          var v = d.settings[f[0]];
          if (f[2] === "select") {
            return "<label>" + esc(f[1]) + "<select data-k='" + f[0] + "'>" +
              f[3].map(function (o) {
                return "<option value='" + o + "'" + (String(v) === String(o)
                  ? " selected" : "") + ">" + String(o) + "</option>";
              }).join("") + "</select></label>";
          }
          return "<label>" + esc(f[1]) + "<input data-k='" + f[0] +
            "' type='number' step='any' value='" + esc(v) + "'></label>";
        }).join("");
      });
    });
  }
  $("#saveSettings").onclick = function () {
    var body = {};
    $$("[data-k]").forEach(function (i) {
      var v = i.value;
      if (v === "true") v = true; else if (v === "false") v = false;
      else if (i.tagName === "INPUT") v = parseFloat(v);
      body[i.dataset.k] = v;
    });
    post("/api/settings", body).then(function (r) {
      $("#setMsg").innerHTML = "<div class='banner good'><p>Settings saved.</p></div>";
      (r.warnings || []).forEach(function (w) { toast(w, "err"); });
      loadSettings();
    }).catch(function (e) { toast(e.message, "err"); });
  };
  $("#resetSettings").onclick = function () {
    if (!confirm("Reset every setting to the safe defaults?")) return;
    post("/api/settings/reset").then(function () {
      toast("Settings reset to safe defaults.", "ok"); loadSettings();
    });
  };

  /* -------------------------------------------------------- telegram */
  function loadTelegram() {
    api("/api/telegram/status").then(function (s) {
      $("#tgMsg").innerHTML = s.configured
        ? "<div class='banner good'><p>Telegram is configured (chat " +
        esc(s.chat_id_masked) + "). Your token is never displayed.</p></div>"
        : "<div class='banner warn'><p>Telegram is not set up. It is optional " +
        "— everything else works without it.</p></div>";
    });
  }
  $("#tgSave").onclick = function () {
    post("/api/telegram/save", {
      token: $("#tgToken").value, chat_id: $("#tgChat").value
    }).then(function () {
      $("#tgToken").value = ""; toast("Saved.", "ok"); loadTelegram();
    }).catch(function (e) { toast(e.message, "err"); });
  };
  $("#tgTest").onclick = function () {
    post("/api/telegram/test").then(function (r) {
      toast(r.message, r.ok ? "ok" : "err");
    }).catch(function (e) { toast(e.message, "err"); });
  };

  /* --------------------------------------------------------- backups */
  function loadBackups() {
    api("/api/backups").then(function (d) {
      $("#backupList").innerHTML = d.backups.length ? table(
        [{ label: "File" }, { label: "Created" }, { label: "Size", num: 1 },
        { label: "Checksum" }, { label: "Verified" }, { label: "" }],
        d.backups, function (b) {
          return "<tr><td>" + esc(b.file) + "</td><td>" + esc(b.created) + "</td>" +
            "<td class='num'>" + (b.size_mb !== undefined ? b.size_mb + " MB"
              : ((b.size_bytes / 1048576) || 0).toFixed(1) + " MB") + "</td>" +
            "<td style='font-family:monospace;font-size:11px'>" +
            esc(b.checksum_short) + "…</td>" +
            "<td class='" + (b.ok ? "ok" : "bad") + "'>" +
            (b.ok ? "Verified" : "CHECKSUM FAILED") + "</td>" +
            "<td><button class='btn ghost' data-restore='" + esc(b.file) +
            "'>RESTORE</button></td></tr>";
        }) : "<div class='empty'>No backups yet.</div>";
      $$("[data-restore]").forEach(function (b) {
        b.onclick = function () {
          if (!confirm("Restore " + b.dataset.restore + "?\n\nYour current " +
            "database will be saved as a new backup first.")) return;
          post("/api/backups/restore", { file: b.dataset.restore })
            .then(function (r) {
              toast("Restored. Previous database saved as " + r.previous_saved_as, "ok");
              refreshStatus(); loadBackups();
            }).catch(function (e) { toast(e.message, "err"); });
        };
      });
    });
  }

  /* ------------------------------------------------------------ logs */
  $$(".tab").forEach(function (t) {
    t.onclick = function () {
      $$(".tab").forEach(function (x) { x.classList.remove("active"); });
      t.classList.add("active"); loadLogs(t.dataset.log);
    };
  });
  function loadLogs(kind) {
    go("logs");
    $$(".tab").forEach(function (x) {
      x.classList.toggle("active", x.dataset.log === kind);
    });
    api("/api/logs?kind=" + kind).then(function (d) {
      if (d.text !== undefined) {
        $("#logBody").innerHTML = "<pre>" + esc(d.text || "(log file is empty)") + "</pre>";
        return;
      }
      if (!d.rows.length) {
        $("#logBody").innerHTML = "<div class='empty'>Nothing recorded.</div>";
        return;
      }
      var cols = Object.keys(d.rows[0]);
      $("#logBody").innerHTML = table(cols.map(function (c) {
        return { label: c.replace(/_/g, " ") };
      }), d.rows, function (r) {
        return "<tr>" + cols.map(function (c) {
          return "<td>" + esc(r[c]) + "</td>";
        }).join("") + "</tr>";
      });
    }).catch(function (e) { toast(e.message, "err"); });
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest ? e.target.closest("[data-log-jump]") : null;
    if (t) loadLogs(t.dataset.logJump);
  });

  /* ------------------------------------------------------------ boot */
  refreshStatus();
  watch();
  setInterval(function () {
    if ($("#page-dashboard").classList.contains("active") && !pollTimer) refreshStatus();
  }, 30000);
})();
