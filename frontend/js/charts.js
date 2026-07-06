/* PathFinder — dependency-free SVG charts (offline-safe, no chart lib). */
const Charts = (() => {
  const COL = {
    up: '#0e5c48', down: '#bd4a2c', flat: '#3a5566',
    band: 'rgba(14,92,72,.12)', bandDown: 'rgba(189,74,44,.12)',
    grid: '#e8dfce', ink: '#514a3c', faint: '#8a8069',
  };
  const colorFor = (dir) => COL[dir] || COL.flat;

  function sparkline(values, opts = {}) {
    const w = opts.w || 66, h = opts.h || 30, pad = 3, color = opts.color || COL.flat;
    if (!values || values.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const x = (i) => pad + (i * (w - 2 * pad)) / (values.length - 1);
    const y = (v) => h - pad - ((v - min) / span) * (h - 2 * pad);
    const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
    const area = `${d} L${x(values.length - 1).toFixed(1)} ${h - pad} L${x(0).toFixed(1)} ${h - pad} Z`;
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
      <path d="${area}" fill="${color}" opacity="0.10"/>
      <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${x(values.length - 1).toFixed(1)}" cy="${y(values[values.length - 1]).toFixed(1)}" r="2.1" fill="${color}"/>
    </svg>`;
  }

  function matchRing(score, size = 58) {
    const r = size / 2 - 5, c = 2 * Math.PI * r, pct = Math.max(0, Math.min(100, score));
    const off = c * (1 - pct / 100);
    const col = pct >= 55 ? COL.up : pct >= 40 ? '#d69200' : COL.flat;
    return `<svg class="match-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${COL.grid}" stroke-width="5"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${col}" stroke-width="5"
        stroke-linecap="round" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"
        transform="rotate(-90 ${size / 2} ${size / 2})"/>
      <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central"
        font-family="var(--font-mono)" font-size="${size * 0.28}" font-weight="700" fill="${col}">${Math.round(pct)}</text>
    </svg>`;
  }

  function forecastChart(points, opts = {}) {
    const w = opts.w || 620, h = opts.h || 250;
    const padL = 40, padR = 14, padT = 14, padB = 26;
    const dir = opts.direction || 'flat';
    const line = colorFor(dir);
    const band = dir === 'down' ? COL.bandDown : COL.band;

    const N = points.length;
    const lows = points.map(p => p.is_forecast ? p.lower : p.value);
    const highs = points.map(p => p.is_forecast ? p.upper : p.value);
    let ymin = Math.min(...lows), ymax = Math.max(...highs);
    const padY = (ymax - ymin) * 0.08 || 1; ymin -= padY; ymax += padY;
    const span = ymax - ymin || 1;
    const x = (i) => padL + (i * (w - padL - padR)) / (N - 1);
    const y = (v) => h - padB - ((v - ymin) / span) * (h - padT - padB);

    const hist = points.filter(p => !p.is_forecast);
    const fc = points.filter(p => p.is_forecast);
    const bIdx = hist.length; // first forecast index

    const path = (arr, off, key = 'value') =>
      arr.map((p, i) => `${i ? 'L' : 'M'}${x(i + off).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ');

    // Confidence band polygon over forecast region (+ bridge from last history point).
    const upPts = fc.map((p, i) => `${x(bIdx + i).toFixed(1)} ${y(p.upper).toFixed(1)}`);
    const loPts = fc.map((p, i) => `${x(bIdx + i).toFixed(1)} ${y(p.lower).toFixed(1)}`).reverse();
    const bandPath = `M${x(bIdx - 1).toFixed(1)} ${y(hist[hist.length - 1].value).toFixed(1)} L${upPts.join(' L')} L${loPts.join(' L')} Z`;

    // gridlines (4 horizontal)
    let grid = '';
    for (let g = 0; g <= 3; g++) {
      const gv = ymin + (span * g) / 3, gy = y(gv).toFixed(1);
      grid += `<line x1="${padL}" y1="${gy}" x2="${w - padR}" y2="${gy}" stroke="${COL.grid}" stroke-width="1"/>
        <text x="${padL - 6}" y="${gy}" text-anchor="end" dominant-baseline="central" font-family="var(--font-mono)" font-size="9" fill="${COL.faint}">${Math.round(gv)}</text>`;
    }

    // x labels: first, boundary, last
    const lab = (i, txt, anchor) =>
      `<text x="${x(i).toFixed(1)}" y="${h - 8}" text-anchor="${anchor}" font-family="var(--font-mono)" font-size="9" fill="${COL.faint}">${txt}</text>`;

    const histLine = path(hist, 0);
    const bridge = `M${x(bIdx - 1).toFixed(1)} ${y(hist[hist.length - 1].value).toFixed(1)} L${x(bIdx).toFixed(1)} ${y(fc[0].value).toFixed(1)}`;
    const fcLine = bridge + ' ' + path(fc, bIdx).replace(/^M[^L]*/, 'L');

    const bx = x(bIdx - 1).toFixed(1);
    return `<svg class="forecast-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Skill demand history and 3-year forecast">
      ${grid}
      <path d="${bandPath}" fill="${band}" stroke="none"/>
      <line x1="${bx}" y1="${padT}" x2="${bx}" y2="${h - padB}" stroke="${COL.faint}" stroke-width="1" stroke-dasharray="3 3"/>
      <text x="${bx}" y="${padT + 2}" text-anchor="middle" font-family="var(--font-mono)" font-size="9" fill="${COL.faint}">now</text>
      <path d="${histLine}" fill="none" stroke="${line}" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="${fcLine}" fill="none" stroke="${line}" stroke-width="2.2" stroke-dasharray="5 4" stroke-linejoin="round" opacity="0.85"/>
      ${lab(0, points[0].month, 'start')}
      ${lab(N - 1, points[N - 1].month, 'end')}
    </svg>`;
  }

  return { sparkline, matchRing, forecastChart, colorFor };
})();
