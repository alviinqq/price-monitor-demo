// GET /api/shop?s=alfa[&date=YYYY-MM-DD]
// Renders a fictional shop page. Each shop uses different HTML markup on purpose,
// the way real competitor sites do, so the scraper needs per-site selectors.

const { SHOPS, PRODUCTS, priceFor, inStock } = require("../lib/catalog");

const fmtPl = (n) => n.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, " ");

function renderAlfa(date) {
  const cards = PRODUCTS.map((p) => {
    const price = priceFor("alfa", p, date);
    const stock = inStock("alfa", p, date);
    return `<div class="product-card" data-sku="${p.sku}">
  <h3 class="product-card__title">${p.name}</h3>
  <div class="product-card__price"><span class="amount">${fmtPl(price)}</span> zł</div>
  <div class="product-card__stock">${stock ? "Dostępny" : "Brak w magazynie"}</div>
</div>`;
  }).join("\n");
  return `<main class="grid">${cards}</main>`;
}

function renderVoltix(date) {
  const rows = PRODUCTS.map((p) => {
    const price = priceFor("voltix", p, date);
    const stock = inStock("voltix", p, date);
    return `<tr id="sku-${p.sku}"><td class="name">${p.name}</td><td class="price">${price.toFixed(2)} PLN</td><td class="avail">${stock ? "in stock" : "out of stock"}</td></tr>`;
  }).join("\n");
  return `<table class="offers"><thead><tr><th>Product</th><th>Price</th><th>Availability</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderMediaplus(date) {
  const items = PRODUCTS.map((p) => {
    const price = priceFor("mediaplus", p, date);
    const stock = inStock("mediaplus", p, date);
    const [zl, gr] = price.toFixed(2).split(".");
    return `<li class="offer" data-product-id="${p.sku}" data-available="${stock ? 1 : 0}">
  <a class="offer-name" href="#${p.sku}">${p.name}</a>
  <p class="offer-price"><strong>${zl}</strong><sup>${gr}</sup> zł</p>
</li>`;
  }).join("\n");
  return `<ul class="offers-list">${items}</ul>`;
}

const RENDER = { alfa: renderAlfa, voltix: renderVoltix, mediaplus: renderMediaplus };

function handler(req, res) {
  const url = new URL(req.url, "http://localhost");
  const shopId = url.searchParams.get("s");
  const dateParam = url.searchParams.get("date");
  const today = new Date().toISOString().slice(0, 10);
  const date = /^\d{4}-\d{2}-\d{2}$/.test(dateParam || "") && dateParam <= today ? dateParam : today;

  if (!RENDER[shopId]) {
    res.statusCode = 404;
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    return res.end("Unknown shop");
  }

  const shop = SHOPS[shopId];
  const html = `<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8"><title>${shop.name} (demo shop)</title>
<meta name="robots" content="noindex"></head><body>
<header><h1>${shop.name}</h1><p>Demo shop for the price-monitor project. Fictional prices for ${date}.</p></header>
${RENDER[shopId](date)}
</body></html>`;
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "s-maxage=3600");
  res.end(html);
}

module.exports = handler;
