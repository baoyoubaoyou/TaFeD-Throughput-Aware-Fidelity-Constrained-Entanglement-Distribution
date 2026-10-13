import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repoRoot = "C:\\Users\\21433\\Desktop\\多智能体量子协同路由\\代码\\SimQN-main\\SimQN-main";
const packageRoot = path.join(repoRoot, "experiment_package_100runs");
const resultsDir = path.join(packageRoot, "results");
const outputPath = path.join(packageRoot, "experiment_summary_100runs.xlsx");
const previewPath = path.join(packageRoot, "experiment_summary_100runs_preview.png");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(field);
        field = "";
      } else if (ch === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else if (ch !== "\r") {
        field += ch;
      }
    }
  }
  row.push(field);
  if (row.length > 1 || row[0] !== "") rows.push(row);
  return rows;
}

function coerceValue(value) {
  const v = String(value ?? "").trim();
  if (v === "") return null;
  if (/^(true|false)$/i.test(v)) return /^true$/i.test(v);
  if (/^-?(?:\d+|\d*\.\d+)(?:e[+-]?\d+)?$/i.test(v) && !/^0\d+/.test(v)) {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return v;
}

function classifyFile(name) {
  if (name.startsWith("node_scaling")) return "node";
  if (name.startsWith("request_scaling")) return "request";
  if (name.startsWith("memory_capacity")) return "memory";
  if (name.startsWith("generation_capacity")) return "generation";
  if (name.startsWith("fidelity_demand")) return "fidelity";
  if (name.startsWith("path_length")) return "path";
  if (name.startsWith("milp")) return "milp";
  return "other";
}

function shortSheetName(fileName, used) {
  let name = fileName
    .replace(/\.csv$/i, "")
    .replace(/_with_baselines/g, "")
    .replace(/_scaling/g, "")
    .replace(/_capacity/g, "cap")
    .replace(/_demand/g, "dem")
    .replace(/_nodes/g, "n")
    .replace(/_groups/g, "g")
    .replace(/_seeds/g, "s")
    .replace(/comparison/g, "cmp")
    .replace(/summary/g, "sum")
    .replace(/raw_before_fixed_5to8/g, "raw_old")
    .replace(/publication_plot_data/g, "pubdata")
    .replace(/[^A-Za-z0-9_]/g, "_");
  name = name.slice(0, 31);
  let finalName = name;
  let i = 2;
  while (used.has(finalName)) {
    const suffix = `_${i}`;
    finalName = name.slice(0, 31 - suffix.length) + suffix;
    i++;
  }
  used.add(finalName);
  return finalName;
}

function cellRef(row, col) {
  let c = col + 1;
  let letters = "";
  while (c > 0) {
    const rem = (c - 1) % 26;
    letters = String.fromCharCode(65 + rem) + letters;
    c = Math.floor((c - 1) / 26);
  }
  return `${letters}${row + 1}`;
}

const allFiles = (await fs.readdir(resultsDir))
  .filter((f) => f.toLowerCase().endsWith(".csv"))
  .sort((a, b) => {
    const ca = classifyFile(a);
    const cb = classifyFile(b);
    if (ca !== cb) return ca.localeCompare(cb);
    const score = (x) => (x.includes("100") ? 0 : x.includes("summary") ? 1 : 2);
    return score(a) - score(b) || a.localeCompare(b);
  });

const workbook = Workbook.create();
const index = workbook.worksheets.add("Index");
index.showGridLines = false;

const indexRows = [
  ["100-run Experiment Workbook"],
  ["说明", "这个 Excel 汇总了实验包 results/ 目录下的主要 CSV。图、脚本、日志仍保留在归档包对应目录中。"],
  [],
  ["Category", "Sheet", "Source CSV", "Rows", "Columns", "Type"],
];

const usedSheetNames = new Set(["Index"]);

for (const fileName of allFiles) {
  const sourcePath = path.join(resultsDir, fileName);
  const text = await fs.readFile(sourcePath, "utf8");
  const parsed = parseCsv(text);
  const rows = parsed.map((r) => r.map(coerceValue));
  if (rows.length === 0) continue;

  const width = Math.max(...rows.map((r) => r.length));
  const normalized = rows.map((r) => {
    const copy = [...r];
    while (copy.length < width) copy.push(null);
    return copy;
  });

  const sheetName = shortSheetName(fileName, usedSheetNames);
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  const dataRange = sheet.getRangeByIndexes(0, 0, normalized.length, width);
  dataRange.values = normalized;

  const header = sheet.getRangeByIndexes(0, 0, 1, width);
  header.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  dataRange.format.borders = { preset: "inside", style: "thin", color: "#E5E7EB" };
  sheet.freezePanes.freezeRows(1);
  dataRange.format.autofitColumns();
  dataRange.format.autofitRows();

  const type = fileName.includes("_raw") ? "raw"
    : fileName.includes("_summary") ? "summary"
    : fileName.includes("_comparison") ? "comparison"
    : "other";
  indexRows.push([classifyFile(fileName), sheetName, fileName, normalized.length - 1, width, type]);
}

index.getRangeByIndexes(0, 0, indexRows.length, 6).values = indexRows;
index.getRange("A1:F1").merge();
index.getRange("A1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF", size: 16 },
};
index.getRange("A2:F2").merge();
index.getRange("A2").format = { fill: "#E6F4F1", wrapText: true };
index.getRange("A4:F4").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
};
index.getRangeByIndexes(3, 0, Math.max(1, indexRows.length - 3), 6).format.borders = {
  preset: "inside",
  style: "thin",
  color: "#D9E2F3",
};
index.freezePanes.freezeRows(4);
index.getRangeByIndexes(0, 0, indexRows.length, 6).format.autofitColumns();
index.getRange("B:B").format.columnWidth = 30;
index.getRange("C:C").format.columnWidth = 68;
index.getRange("A2").format.rowHeight = 38;

const inspect = await workbook.inspect({
  kind: "sheet,table",
  maxChars: 3000,
  tableMaxRows: 4,
  tableMaxCols: 6,
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({
  sheetName: "Index",
  range: `A1:F${Math.min(indexRows.length, 24)}`,
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Saved ${outputPath}`);
console.log(`Preview ${previewPath}`);
