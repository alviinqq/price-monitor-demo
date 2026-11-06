// Local preview: node dev-server.js -> http://localhost:3001
const http = require("http");
const fs = require("fs");
const path = require("path");
const shop = require("./api/shop");

const PORT = process.env.PORT || 3001;
const TYPES = { ".html": "text/html; charset=utf-8", ".json": "application/json", ".png": "image/png" };

http.createServer((req, res) => {
  if (req.url.startsWith("/api/shop")) return shop(req, res);
  const rel = req.url.split("?")[0] === "/" ? "/index.html" : req.url.split("?")[0];
  const file = path.join(__dirname, path.normalize(rel));
  if (!file.startsWith(__dirname) || !fs.existsSync(file)) {
    res.statusCode = 404;
    return res.end("Not found");
  }
  res.setHeader("Content-Type", TYPES[path.extname(file)] || "application/octet-stream");
  fs.createReadStream(file).pipe(res);
}).listen(PORT, () => console.log(`http://localhost:${PORT}`));
