// Dùng trong probe: chạy rtCompute của web/gold.js trên nến lưu sẵn, in kết quả dạng JSON.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const a = src.indexOf("  const RR = {"), b = src.indexOf("  function applyRT");
const rtCompute = new Function(src.slice(a, b) + "\nreturn rtCompute;")();
const d = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = rtCompute(d.m15, d.h1, d.h4);
console.log(JSON.stringify(out));
