// Draws one receipt copy (the Customer copy) on an A4 canvas for the shared PDF. The text
// comes from the same sheet description the page prints (loanSheet / entrySheet), which is
// built only from /receipts/* data. Sizes are the print sizes from print.css; colours and
// the font family are read from the copy on screen, so there is one source for each.
// The browser shapes the text, so Malayalam terms render as they do on paper.

import { OFFICE_SEAL, RECEIPT_TERMS, letterheadText } from "./printing.jsx";
import { formatDay } from "../lib/dates.js";

const DPI = 200;
const PT = DPI / 72;
const MM = DPI / 25.4;
const CSS_PX = DPI / 96;
const LINE = 1.45;
export const PAGE_PX = { width: Math.round(210 * MM), height: Math.round(297 * MM) };
const MARGIN = 12 * MM;

function graphemes(text) {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    return Array.from(new Intl.Segmenter(undefined, { granularity: "grapheme" }).segment(text), (part) => part.segment);
  }
  return Array.from(text);
}

/**
 * Break text into lines no wider than `maxWidth` (as reported by `measure`): at spaces
 * first, and between characters (grapheme clusters) for a word that is too long alone.
 * Line breaks in the text are kept.
 */
export function wrapText(text, maxWidth, measure) {
  const lines = [];
  for (const paragraph of String(text ?? "").split(/\r?\n/)) {
    const words = paragraph.split(/[ \t]+/).filter(Boolean);
    let line = "";
    for (const word of words) {
      const candidate = line ? `${line} ${word}` : word;
      if (measure(candidate) <= maxWidth) {
        line = candidate;
        continue;
      }
      if (line) lines.push(line);
      line = "";
      if (measure(word) <= maxWidth) {
        line = word;
        continue;
      }
      for (const piece of graphemes(word)) {
        if (line && measure(line + piece) > maxWidth) {
          lines.push(line);
          line = piece;
        } else {
          line += piece;
        }
      }
    }
    lines.push(line);
  }
  return lines;
}

function readStyles(root) {
  const view = root.ownerDocument?.defaultView ?? globalThis;
  const computed = (element) => view.getComputedStyle(element);
  const sheet = computed(root);
  const pick = (selector, property) => {
    const element = root.querySelector(selector);
    return element ? computed(element)[property] || sheet.color : sheet.color;
  };
  const paper = sheet.backgroundColor;
  return {
    family: sheet.fontFamily || "sans-serif",
    paper: !paper || paper === "transparent" || /rgba\(.*,\s*0\)$/.test(paper) ? "white" : paper,
    ink: sheet.color,
    muted: pick(".sheet-fields dt", "color"),
    rule: pick(".sheet-fields div", "borderBottomColor"),
    brand: pick(".letterhead", "borderBottomColor"),
    name: pick(".letterhead-name", "color"),
    frame: pick(".sheet-total", "borderTopColor"),
    signature: pick(".signatures div", "borderTopColor"),
  };
}

async function loadLogo(source) {
  if (typeof source !== "string" || !source.startsWith("data:image/")) return null;
  try {
    const image = new Image();
    image.src = source;
    await image.decode();
    return image;
  } catch {
    return null; // a broken logo never stops the receipt
  }
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

/** Draw the sheet on a fresh canvas and return it as JPEG bytes. `refs.element` is the copy on screen. */
export async function renderSheetJpeg(sheet, refs) {
  const root = refs?.element;
  if (!root) throw new Error("The receipt isn't on screen yet. Wait for it to load and try again.");
  const colours = readStyles(root);
  if (document.fonts?.ready) await document.fonts.ready;
  const logo = await loadLogo(sheet.letterhead?.logo);

  const canvas = document.createElement("canvas");
  canvas.width = PAGE_PX.width;
  canvas.height = PAGE_PX.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser can't draw the PDF.");
  const spacing = "letterSpacing" in ctx;

  const font = (sizePt, weight = 400, letterEm = 0) => {
    ctx.font = `${weight} ${sizePt * PT}px ${colours.family}`;
    if (spacing) ctx.letterSpacing = `${letterEm * sizePt * PT}px`;
  };
  const measure = (text) => ctx.measureText(text).width;
  const lineHeight = (sizePt) => sizePt * PT * LINE;
  // Draw wrapped lines from the top of their line box; returns the height used.
  const lines = (list, x, top, sizePt, colour, align = "left") => {
    ctx.fillStyle = colour;
    ctx.textAlign = align;
    ctx.textBaseline = "middle";
    list.forEach((text, index) => ctx.fillText(text, x, top + lineHeight(sizePt) * (index + 0.5)));
    return list.length * lineHeight(sizePt);
  };
  const rule = (x1, x2, y, colour, widthCssPx) => {
    ctx.strokeStyle = colour;
    ctx.lineWidth = widthCssPx * CSS_PX;
    ctx.beginPath();
    ctx.moveTo(x1, y);
    ctx.lineTo(x2, y);
    ctx.stroke();
  };

  ctx.fillStyle = colours.paper;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const left = MARGIN;
  const width = PAGE_PX.width - 2 * MARGIN;
  const right = left + width;
  let y = MARGIN;

  // Letterhead: logo · name and contact lines · document title and date
  const head = letterheadText(sheet.letterhead);
  const title = sheet.title.toUpperCase();
  const dateLine = `Date: ${formatDay(sheet.date)}`;
  font(11, 700);
  const titleWidth = measure(title);
  font(9);
  const docWidth = Math.min(width / 2, Math.max(titleWidth, measure(dateLine)));
  const logoSize = logo ? 14 * MM : 0;
  const textLeft = left + (logo ? logoSize + 4 * MM : 0);
  const textWidth = right - docWidth - 4 * MM - textLeft;
  font(13, 800, 0.02);
  const nameLines = wrapText(head.name, textWidth, measure);
  font(9);
  const infoLines = [head.address, head.contact].filter(Boolean).flatMap((text) => wrapText(text, textWidth, measure));
  font(11, 700);
  const titleLines = wrapText(title, docWidth, measure);
  const textHeight = nameLines.length * lineHeight(13) + infoLines.length * lineHeight(9);
  const docHeight = titleLines.length * lineHeight(11) + lineHeight(9);
  const headHeight = Math.max(logoSize, textHeight, docHeight);
  if (logo) {
    const scale = Math.min(logoSize / logo.naturalWidth, logoSize / logo.naturalHeight) || 0;
    const w = logo.naturalWidth * scale;
    const h = logo.naturalHeight * scale;
    ctx.drawImage(logo, left + (logoSize - w) / 2, y + (headHeight - h) / 2, w, h);
  }
  let top = y + (headHeight - textHeight) / 2;
  font(13, 800, 0.02);
  top += lines(nameLines, textLeft, top, 13, colours.name);
  font(9);
  lines(infoLines, textLeft, top, 9, colours.muted);
  top = y + (headHeight - docHeight) / 2;
  font(11, 700);
  top += lines(titleLines, right, top, 11, colours.ink, "right");
  font(9);
  lines([dateLine], right, top, 9, colours.muted, "right");
  y += headHeight + 3 * MM;
  rule(left, right, y + CSS_PX, colours.brand, 2);
  y += 2 * CSS_PX + 4 * MM;

  // Fields: three columns, label above value, a rule under each
  const columnGap = 6 * MM;
  const columnWidth = (width - 2 * columnGap) / 3;
  const cells = sheet.fields.filter(Boolean).map(([label, value]) => {
    font(7.5, 400, 0.05);
    const labelLines = wrapText(String(label).toUpperCase(), columnWidth, measure);
    font(10.5, 650);
    const valueLines = wrapText(value === null || value === undefined ? "—" : String(value), columnWidth, measure);
    return { labelLines, valueLines, height: labelLines.length * lineHeight(7.5) + valueLines.length * lineHeight(10.5) };
  });
  for (let start = 0; start < cells.length; start += 3) {
    const row = cells.slice(start, start + 3);
    const rowHeight = Math.max(...row.map((cell) => cell.height)) + 1 * MM + CSS_PX;
    row.forEach((cell, index) => {
      const x = left + index * (columnWidth + columnGap);
      font(7.5, 400, 0.05);
      const used = lines(cell.labelLines, x, y, 7.5, colours.muted);
      font(10.5, 650);
      lines(cell.valueLines, x, y + used, 10.5, colours.ink);
      rule(x, x + columnWidth, y + rowHeight - CSS_PX / 2, colours.rule, 1);
    });
    y += rowHeight + (start + 3 < cells.length ? 2 * MM : 0);
  }
  y += 4 * MM;

  // Total in a framed box
  if (sheet.total) {
    y += 2 * MM;
    const boxHeight = 6 * MM + lineHeight(14);
    ctx.strokeStyle = colours.frame;
    ctx.lineWidth = 1.5 * CSS_PX;
    roundedRect(ctx, left, y, width, boxHeight, 2 * MM);
    ctx.stroke();
    ctx.fillStyle = colours.ink;
    ctx.textBaseline = "alphabetic";
    const baseline = y + 3 * MM + lineHeight(14) / 2 + 14 * PT * 0.35;
    font(10.5, 700);
    ctx.textAlign = "left";
    ctx.fillText(sheet.total.label, left + 4 * MM, baseline);
    font(14, 700);
    ctx.textAlign = "right";
    ctx.fillText(sheet.total.value, right - 4 * MM, baseline);
    y += boxHeight + 4 * MM;
  }

  // Terms (Malayalam)
  if (sheet.terms) {
    y += 3 * MM;
    font(8.5, 700);
    y += lines(["Terms and conditions"], left, y, 8.5, colours.ink) + 1 * MM;
    font(8.5);
    if ("lang" in ctx) ctx.lang = "ml";
    for (const term of RECEIPT_TERMS) {
      const termLines = wrapText(term, width - 5 * MM, measure);
      lines(["•"], left + 2 * MM, y, 8.5, colours.ink, "center");
      y += lines(termLines, left + 5 * MM, y, 8.5, colours.ink);
    }
    if ("lang" in ctx) ctx.lang = "en";
    y += 3 * MM;
  }

  // Signature lines
  y += 10 * MM;
  const signatureGap = 8 * MM;
  const signatureWidth = (width - 2 * signatureGap) / 3;
  const signatures = [sheet.signatures?.left ?? "", OFFICE_SEAL, sheet.signatures?.right ?? ""];
  font(8.5);
  signatures.forEach((text, index) => {
    const x = left + index * (signatureWidth + signatureGap);
    rule(x, x + signatureWidth, y, colours.signature, 1);
    lines(wrapText(text, signatureWidth, measure), x + signatureWidth / 2, y + CSS_PX + 1 * MM, 8.5, colours.muted, "center");
  });

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob) throw new Error("This browser couldn't make the PDF image.");
  return new Uint8Array(await blob.arrayBuffer());
}
