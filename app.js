(() => {
  const ORCID = "0000-0001-9762-102X";
  const PUB_PAGE = 12;   // publications shown before "Show all"
  const NEWS_PAGE = 8;   // news items shown before "Show more"

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso, opts) => {
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleDateString("en-US", opts || { year: "numeric", month: "short" });
  };
  $("yr").textContent = new Date().getFullYear();

  /* ---------- Decorative "classified raster" strip on each project card ---------- */
  const CLASSES = {
    urban:  ["#b9b4ad", "#8f8a84", "#d8d3cc", "#e0663a", "#6f9e86"],   // built-up, dense, bare, favela, vegetation
    lulc:   ["#1f6f4a", "#6f9e86", "#c9dfae", "#e7d59a", "#5b8fb9"],   // forest, savanna, grassland, agriculture, water
    school: ["#b9b4ad", "#6f9e86", "#e0663a", "#f0a868", "#d8d3cc"],
  };
  document.querySelectorAll(".card[data-raster]").forEach((card, k) => {
    const pal = CLASSES[card.dataset.raster] || CLASSES.urban;
    let seed = 17 + k * 101;
    const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
    let prev = 0;
    const cells = Array.from({ length: 32 }, () => {
      prev = rnd() < 0.55 ? prev : Math.floor(rnd() * pal.length);   // spatial autocorrelation, roughly
      return `<i style="background:${pal[prev]}"></i>`;
    }).join("");
    card.insertAdjacentHTML("afterbegin", `<div class="card-raster" aria-hidden="true">${cells}</div>`);
  });

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  /* ---------- Publications ---------- */
  // Fallback: fetch straight from OpenAlex in the browser if data/publications.json is missing or empty.
  async function liveOpenAlex() {
    const url = `https://api.openalex.org/works?filter=author.orcid:${ORCID}&sort=publication_year:desc&per_page=200` +
      `&select=title,publication_year,publication_date,primary_location,doi,type,authorships,open_access`;
    const j = await getJSON(url);
    return {
      updated: new Date().toISOString(),
      items: j.results.map((w) => ({
        year: w.publication_year,
        title: w.title,
        authors: (w.authorships || []).map((a) => a.author?.display_name).filter(Boolean),
        venue: w.primary_location?.source?.display_name || "",
        doi: w.doi || "",
        url: w.doi || w.primary_location?.landing_page_url || "",
        type: w.type,
        oa: !!w.open_access?.is_oa,
      })),
    };
  }

  function authorLine(authors) {
    if (!authors || !authors.length) return "";
    const list = authors.length > 8 ? [...authors.slice(0, 6), "…", authors[authors.length - 1]] : authors;
    return list.map((a) => (/pedrassoli/i.test(a) ? `<span class="me">${esc(a)}</span>` : esc(a))).join(", ");
  }

  const TYPE_LABEL = { "book-chapter": "Chapter", book: "Book", dissertation: "Thesis", preprint: "Preprint", dataset: "Dataset", "proceedings-article": "Conference" };

  function renderPubs(all) {
    const list = $("pub-list"), more = $("pub-more"), q = $("pub-search"), ysel = $("pub-year");
    let expanded = false;

    [...new Set(all.map((p) => p.year).filter(Boolean))].sort((a, b) => b - a)
      .forEach((y) => ysel.insertAdjacentHTML("beforeend", `<option>${y}</option>`));

    function draw() {
      const term = q.value.trim().toLowerCase(), yr = ysel.value;
      const filtered = all.filter((p) =>
        (!yr || String(p.year) === yr) &&
        (!term || `${p.title} ${p.venue} ${(p.authors || []).join(" ")}`.toLowerCase().includes(term)));
      const filtering = term || yr;
      const shown = expanded || filtering ? filtered : filtered.slice(0, PUB_PAGE);
      list.innerHTML = shown.length ? shown.map((p) => {
        const badge = TYPE_LABEL[p.type] ? `<span class="badge">${TYPE_LABEL[p.type]}</span>` : "";
        const title = p.url ? `<a class="pub-title" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : `<span class="pub-title">${esc(p.title)}</span>`;
        return `<li class="pub"><span class="pub-year">${esc(p.year)}</span><div>${title}
          <div class="pub-authors">${authorLine(p.authors)}</div>
          ${p.venue || badge ? `<div class="pub-venue">${esc(p.venue)}${badge}</div>` : ""}</div></li>`;
      }).join("") : `<li class="empty">No publications match.</li>`;
      more.hidden = expanded || filtering || filtered.length <= PUB_PAGE;
    }
    q.addEventListener("input", draw);
    ysel.addEventListener("change", draw);
    more.addEventListener("click", () => { expanded = true; draw(); });
    draw();
  }

  (async () => {
    let data = null;
    try { data = await getJSON("publications.json"); } catch (_) { data = window.__PUBS; }
    if (!data || !data.items || !data.items.length) {
      try { data = await liveOpenAlex(); } catch (_) {}
    }
    if (!data || !data.items || !data.items.length) {
      $("pub-list").innerHTML = `<li class="empty">Publications are temporarily unavailable — see <a href="https://orcid.org/${ORCID}">ORCID</a>.</li>`;
      return;
    }
    const items = data.items.filter((p) => p.title).sort((a, b) => (b.year || 0) - (a.year || 0));
    $("pub-meta").textContent = `${items.length} items · updated ${fmtDate(data.updated, { year: "numeric", month: "short", day: "numeric" })}`;
    renderPubs(items);
  })();

  /* ---------- News ---------- */
  (async () => {
    const list = $("news-list"), more = $("news-more");
    let data;
    try { data = await getJSON("news.json"); } catch (_) { data = window.__NEWS; }
    const items = (data?.items || []).sort((a, b) => new Date(b.date) - new Date(a.date));
    if (!items.length) { list.innerHTML = `<li class="empty">No recent coverage.</li>`; return; }
    $("news-meta").textContent = `updated ${fmtDate(data.updated, { year: "numeric", month: "short", day: "numeric" })}`;
    let n = NEWS_PAGE;
    function draw() {
      list.innerHTML = items.slice(0, n).map((it) => `
        <li class="news-item"><span class="news-date">${fmtDate(it.date)}</span>
        <div><a class="news-title" href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>
        <div class="news-source">${esc(it.source)}</div></div></li>`).join("");
      more.hidden = n >= items.length;
    }
    more.addEventListener("click", () => { n += NEWS_PAGE; draw(); });
    draw();
  })();
})();
