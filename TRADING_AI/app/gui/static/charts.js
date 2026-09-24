/* Hand-written canvas charts. No CDN, no external library, so the app works
   with the network unplugged. */
(function (g) {
  "use strict";

  var C = {
    grid: "#1e2635", axis: "#5d6b80", fg: "#e6edf6",
    up: "#1fae62", down: "#e04d4d", ema: "#e2a03f", sma50: "#4a90d9",
    sma200: "#b07de8", macd: "#4a90d9", sig: "#e2a03f",
    entry: "#3d7de8", stop: "#e04d4d", target: "#1fae62", sr: "#4a5568"
  };

  function prep(cv) {
    var r = window.devicePixelRatio || 1;
    var w = cv.clientWidth || cv.parentNode.clientWidth || 800;
    var h = parseInt(cv.getAttribute("height"), 10) || 200;
    cv.width = w * r; cv.height = h * r;
    cv.style.height = h + "px";
    var x = cv.getContext("2d");
    x.setTransform(r, 0, 0, r, 0, 0);
    x.clearRect(0, 0, w, h);
    return { x: x, w: w, h: h };
  }

  function extent(arrs) {
    var lo = Infinity, hi = -Infinity;
    arrs.forEach(function (a) {
      if (!a) return;
      for (var i = 0; i < a.length; i++) {
        var v = a[i];
        if (v === null || v === undefined || isNaN(v)) continue;
        if (v < lo) lo = v; if (v > hi) hi = v;
      }
    });
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (lo === hi) { lo -= 1; hi += 1; }
    return [lo, hi];
  }

  function fmt(v) {
    if (v === null || v === undefined || isNaN(v)) return "-";
    var a = Math.abs(v);
    if (a >= 1e7) return (v / 1e7).toFixed(2) + "Cr";
    if (a >= 1e5) return (v / 1e5).toFixed(2) + "L";
    if (a >= 1000) return v.toFixed(0);
    return v.toFixed(2);
  }

  function frame(x, w, h, pl, pr, pt, pb, lo, hi, rows, labelFn) {
    x.strokeStyle = C.grid; x.lineWidth = 1;
    x.fillStyle = C.axis; x.font = "10px system-ui"; x.textAlign = "right";
    rows = rows || 5;
    for (var i = 0; i <= rows; i++) {
      var yy = pt + (h - pt - pb) * i / rows;
      var val = hi - (hi - lo) * i / rows;
      x.beginPath(); x.moveTo(pl, Math.round(yy) + .5);
      x.lineTo(w - pr, Math.round(yy) + .5); x.stroke();
      x.fillText((labelFn || fmt)(val), pl - 6, yy + 3);
    }
  }

  function dates(x, ds, pl, pr, w, h, pb) {
    if (!ds || !ds.length) return;
    x.fillStyle = C.axis; x.font = "10px system-ui"; x.textAlign = "center";
    var n = Math.min(7, ds.length), iw = w - pl - pr;
    for (var i = 0; i < n; i++) {
      var k = Math.floor(i * (ds.length - 1) / Math.max(n - 1, 1));
      x.fillText(ds[k].slice(2), pl + iw * k / Math.max(ds.length - 1, 1), h - pb + 13);
    }
  }

  function line(x, arr, pl, iw, pt, ih, lo, hi, color, width) {
    x.strokeStyle = color; x.lineWidth = width || 1.4;
    x.beginPath();
    var started = false, n = arr.length;
    for (var i = 0; i < n; i++) {
      var v = arr[i];
      if (v === null || v === undefined || isNaN(v)) { started = false; continue; }
      var px = pl + iw * i / Math.max(n - 1, 1);
      var py = pt + ih - (v - lo) / (hi - lo) * ih;
      if (!started) { x.moveTo(px, py); started = true; } else x.lineTo(px, py);
    }
    x.stroke();
  }

  function hline(x, v, pl, w, pr, pt, ih, lo, hi, color, label) {
    if (v === null || v === undefined || isNaN(v) || v < lo || v > hi) return;
    var py = pt + ih - (v - lo) / (hi - lo) * ih;
    x.save(); x.strokeStyle = color; x.setLineDash([5, 4]); x.lineWidth = 1;
    x.beginPath(); x.moveTo(pl, py); x.lineTo(w - pr, py); x.stroke();
    x.restore();
    if (label) {
      x.fillStyle = color; x.font = "10px system-ui"; x.textAlign = "left";
      x.fillText(label + " " + v.toFixed(2), pl + 4, py - 3);
    }
  }

  /* ------------------------------------------------------- candles */
  g.drawCandles = function (cv, d) {
    var p = prep(cv), x = p.x, w = p.w, h = p.h;
    var pl = 58, pr = 14, pt = 10, pb = 20;
    var iw = w - pl - pr, ih = h - pt - pb;
    var levels = [d.entry, d.stop, d.target].filter(function (v) { return v; });
    var e = extent([d.high, d.low, d.sma200, levels]);
    var pad = (e[1] - e[0]) * 0.05, lo = e[0] - pad, hi = e[1] + pad;

    frame(x, w, h, pl, pr, pt, pb, lo, hi, 5);
    dates(x, d.dates, pl, pr, w, h, pb);

    var n = d.close.length, cw = Math.max(1, Math.min(9, iw / n * 0.7));
    for (var i = 0; i < n; i++) {
      var o = d.open[i], c = d.close[i], hg = d.high[i], l = d.low[i];
      if (c === null || o === null) continue;
      var px = pl + iw * i / Math.max(n - 1, 1);
      var yv = function (v) { return pt + ih - (v - lo) / (hi - lo) * ih; };
      var up = c >= o;
      x.strokeStyle = up ? C.up : C.down; x.fillStyle = up ? C.up : C.down;
      x.lineWidth = 1;
      x.beginPath(); x.moveTo(px, yv(hg)); x.lineTo(px, yv(l)); x.stroke();
      var y1 = yv(Math.max(o, c)), y2 = yv(Math.min(o, c));
      x.fillRect(px - cw / 2, y1, cw, Math.max(1, y2 - y1));
    }

    (d.support || []).forEach(function (s) {
      hline(x, s, pl, w, pr, pt, ih, lo, hi, C.sr, "S");
    });
    (d.resistance || []).forEach(function (s) {
      hline(x, s, pl, w, pr, pt, ih, lo, hi, C.sr, "R");
    });
    if (d.ema20) line(x, d.ema20, pl, iw, pt, ih, lo, hi, C.ema);
    if (d.sma50) line(x, d.sma50, pl, iw, pt, ih, lo, hi, C.sma50);
    if (d.sma200) line(x, d.sma200, pl, iw, pt, ih, lo, hi, C.sma200);
    hline(x, d.target, pl, w, pr, pt, ih, lo, hi, C.target, "TARGET");
    hline(x, d.entry, pl, w, pr, pt, ih, lo, hi, C.entry, "ENTRY");
    hline(x, d.stop, pl, w, pr, pt, ih, lo, hi, C.stop, "STOP");

    x.textAlign = "left"; x.font = "10px system-ui";
    [["EMA20", C.ema], ["SMA50", C.sma50], ["SMA200", C.sma200]]
      .forEach(function (t, k) {
        x.fillStyle = t[1]; x.fillText(t[0], pl + 6 + k * 52, pt + 11);
      });
  };

  /* -------------------------------------------------------- volume */
  g.drawVolume = function (cv, d) {
    var p = prep(cv), x = p.x, w = p.w, h = p.h;
    var pl = 58, pr = 14, pt = 8, pb = 12;
    var iw = w - pl - pr, ih = h - pt - pb;
    var e = extent([d.volume]), hi = e[1], lo = 0;
    frame(x, w, h, pl, pr, pt, pb, lo, hi, 2);
    var n = d.volume.length, bw = Math.max(1, Math.min(9, iw / n * 0.7));
    for (var i = 0; i < n; i++) {
      var v = d.volume[i]; if (!v) continue;
      var px = pl + iw * i / Math.max(n - 1, 1);
      var bh = v / hi * ih;
      x.fillStyle = (d.close[i] >= d.open[i]) ? "#1fae6288" : "#e04d4d88";
      x.fillRect(px - bw / 2, pt + ih - bh, bw, bh);
    }
    x.fillStyle = C.axis; x.textAlign = "left"; x.font = "10px system-ui";
    x.fillText("VOLUME", pl + 6, pt + 10);
  };

  /* ----------------------------------------------------------- RSI */
  g.drawRsi = function (cv, d) {
    var p = prep(cv), x = p.x, w = p.w, h = p.h;
    var pl = 58, pr = 14, pt = 8, pb = 12;
    var iw = w - pl - pr, ih = h - pt - pb, lo = 0, hi = 100;
    frame(x, w, h, pl, pr, pt, pb, lo, hi, 4, function (v) { return v.toFixed(0); });
    [30, 70].forEach(function (lv) {
      hline(x, lv, pl, w, pr, pt, ih, lo, hi, "#3b4657", "");
    });
    line(x, d.rsi, pl, iw, pt, ih, lo, hi, "#b07de8", 1.5);
    x.fillStyle = C.axis; x.textAlign = "left"; x.font = "10px system-ui";
    x.fillText("RSI 14", pl + 6, pt + 10);
  };

  /* ---------------------------------------------------------- MACD */
  g.drawMacd = function (cv, d) {
    var p = prep(cv), x = p.x, w = p.w, h = p.h;
    var pl = 58, pr = 14, pt = 8, pb = 12;
    var iw = w - pl - pr, ih = h - pt - pb;
    var e = extent([d.macd, d.macd_signal, d.macd_hist]);
    var m = Math.max(Math.abs(e[0]), Math.abs(e[1])) * 1.1 || 1;
    var lo = -m, hi = m;
    frame(x, w, h, pl, pr, pt, pb, lo, hi, 2);
    var n = (d.macd_hist || []).length, bw = Math.max(1, Math.min(7, iw / n * 0.6));
    for (var i = 0; i < n; i++) {
      var v = d.macd_hist[i]; if (v === null || isNaN(v)) continue;
      var px = pl + iw * i / Math.max(n - 1, 1);
      var zy = pt + ih - (0 - lo) / (hi - lo) * ih;
      var vy = pt + ih - (v - lo) / (hi - lo) * ih;
      x.fillStyle = v >= 0 ? "#1fae6299" : "#e04d4d99";
      x.fillRect(px - bw / 2, Math.min(zy, vy), bw, Math.abs(vy - zy) || 1);
    }
    line(x, d.macd, pl, iw, pt, ih, lo, hi, C.macd, 1.4);
    line(x, d.macd_signal, pl, iw, pt, ih, lo, hi, C.sig, 1.4);
    x.fillStyle = C.axis; x.textAlign = "left"; x.font = "10px system-ui";
    x.fillText("MACD 12/26/9", pl + 6, pt + 10);
  };

  /* -------------------------------------------------------- equity */
  g.drawEquity = function (cv, rows) {
    var p = prep(cv), x = p.x, w = p.w, h = p.h;
    var pl = 68, pr = 14, pt = 12, pb = 22;
    var iw = w - pl - pr, ih = h - pt - pb;
    if (!rows || !rows.length) {
      x.fillStyle = C.axis; x.textAlign = "center";
      x.fillText("No equity curve yet", w / 2, h / 2); return;
    }
    var vals = rows.map(function (r) { return r.equity; });
    var ds = rows.map(function (r) { return String(r.date).slice(0, 10); });
    var e = extent([vals]), pad = (e[1] - e[0]) * .06;
    var lo = e[0] - pad, hi = e[1] + pad;
    frame(x, w, h, pl, pr, pt, pb, lo, hi, 5);
    dates(x, ds, pl, pr, w, h, pb);
    line(x, vals, pl, iw, pt, ih, lo, hi, "#4fb3ff", 1.8);
    hline(x, vals[0], pl, w, pr, pt, ih, lo, hi, "#5d6b80", "start");
  };
})(window);
