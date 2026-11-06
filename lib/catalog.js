// Fictional demo shops. Prices change every day by a deterministic formula,
// so the scraper has something real to fetch and the history is reproducible.

const SHOPS = {
  alfa: { name: "AlfaTech", style: "grid" },
  voltix: { name: "Voltix", style: "table" },
  mediaplus: { name: "MediaPlus", style: "list" },
};

const PRODUCTS = [
  { sku: "hp-anc-300", name: "Wireless ANC Headphones X300", base: 449 },
  { sku: "ssd-1tb-nv", name: "NVMe SSD 1 TB", base: 289 },
  { sku: "kb-mech-87", name: "Mechanical Keyboard TKL 87", base: 329 },
  { sku: "mon-27-qhd", name: '27" QHD Monitor 165 Hz', base: 1149 },
  { sku: "rt-ax3000", name: "Wi-Fi 6 Router AX3000", base: 259 },
  { sku: "cam-4k-web", name: "4K Webcam Pro", base: 399 },
];

// Small string hash (FNV-1a), so every shop/product/day gets its own stable "random" value.
function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  // final avalanche (murmur3 fmix) so similar strings don't give similar values
  h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b);
  h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}

function dayIndex(dateStr) {
  return Math.floor(Date.parse(dateStr + "T00:00:00Z") / 86400000);
}

function priceFor(shopId, product, dateStr) {
  const day = dayIndex(dateStr);
  const seed = hash(shopId + product.sku) * 10;
  const shopBias = { alfa: 0.02, voltix: -0.01, mediaplus: 0.04 }[shopId] || 0;
  const wave = 0.05 * Math.sin(day / 6 + seed);
  // About one day in fourteen a shop runs a promo on a product.
  const promo = hash(`${shopId}|${product.sku}|${day}`) < 0.07 ? -0.12 : 0;
  const raw = product.base * (1 + shopBias + wave + promo);
  return Math.round(raw) - 0.01; // shop-style prices like 429.99
}

function inStock(shopId, product, dateStr) {
  return hash(`stock|${shopId}|${product.sku}|${dayIndex(dateStr)}`) > 0.08;
}

module.exports = { SHOPS, PRODUCTS, priceFor, inStock, hash, dayIndex };
