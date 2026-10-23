// The shared-receipt PDF: JPEG parsing, the PDF file structure, text wrapping and the
// canvas drawing (with a recording fake canvas, since Node has none).
import { test } from "node:test";
import assert from "node:assert/strict";
import { jpegInfo, jpegToPdf, pdfText } from "../src/print/pdf.js";
import { PAGE_PX, renderSheetJpeg, wrapText } from "../src/print/receiptCanvas.js";
import { RECEIPT_TERMS } from "../src/print/printing.jsx";

/** A tiny JPEG-shaped byte string: SOI, APP0, a standalone RST, fill bytes, SOF, SOS, EOI. */
function fakeJpeg({ sof = 0xc0, width = 0x0456, height = 0x0123, components = 3 } = {}) {
  return new Uint8Array([
    0xff, 0xd8,
    0xff, 0xe0, 0x00, 0x07, 0x4a, 0x46, 0x49, 0x46, 0x00, // APP0 "JFIF"
    0xff, 0xd0, // RST0 (standalone, no length)
    0xff, 0xff, 0xff, // fill bytes before the next marker
    sof, 0x00, 0x0b, 0x08, height >> 8, height & 0xff, width >> 8, width & 0xff, components, 0x01, 0x11, 0x00,
    0xff, 0xda, 0x00, 0x02,
    0x12, 0x34, 0x56,
    0xff, 0xd9,
  ]);
}

const latin1 = (bytes) => Buffer.from(bytes).toString("latin1");

test("jpegInfo reads the frame size past fill bytes and standalone markers", () => {
  assert.deepEqual(jpegInfo(fakeJpeg()), { bitsPerComponent: 8, width: 0x0456, height: 0x0123, components: 3 });
  assert.equal(jpegInfo(fakeJpeg({ sof: 0xc2, components: 1 })).components, 1);
  assert.equal(jpegInfo(fakeJpeg({ sof: 0xc1, width: 1654, height: 2339 })).width, 1654);
});

test("jpegInfo refuses what isn't a supported JPEG", () => {
  assert.throws(() => jpegInfo(new TextEncoder().encode("%PDF-1.4")), /not a JPEG/);
  assert.throws(() => jpegInfo(new Uint8Array([0xff, 0xd8, 0xff, 0xda, 0x00, 0x02, 0xff, 0xd9])), /no size/);
  assert.throws(() => jpegInfo(fakeJpeg({ sof: 0xc3 })), /unsupported compression/);
  assert.throws(() => jpegInfo(fakeJpeg({ components: 2 })), /unsupported colour/);
  assert.throws(() => jpegInfo(fakeJpeg().slice(0, 20)), /no size/);
  assert.throws(() => jpegInfo([0xff, 0xd8]), /not a JPEG/);
});

test("jpegToPdf writes a valid single-page PDF 1.4", () => {
  const jpeg = fakeJpeg({ width: 1654, height: 2339 });
  const pdf = jpegToPdf(jpeg, { title: "Loan voucher" });
  const text = latin1(pdf);
  assert.ok(text.startsWith("%PDF-1.4\n"));
  assert.ok(text.endsWith("%%EOF\n"));

  const startxref = Number(/startxref\n(\d+)\n%%EOF\n$/.exec(text)[1]);
  assert.equal(text.slice(startxref, startxref + 5), "xref\n");
  const xref = text.slice(startxref).split("\n");
  assert.equal(xref[1], "0 7");
  assert.equal(xref[2], "0000000000 65535 f ");
  for (let id = 1; id <= 6; id += 1) {
    const entry = xref[2 + id];
    assert.match(entry, /^\d{10} 00000 n $/);
    assert.equal(entry.length + 1, 20); // every xref line is exactly 20 bytes
    const offset = Number(entry.slice(0, 10));
    assert.equal(text.slice(offset, offset + `${id} 0 obj`.length), `${id} 0 obj`);
  }
  assert.match(text, /trailer\n<< \/Size 7 \/Root 1 0 R \/Info 6 0 R >>/);

  // every stream's /Length is its exact byte count
  const streams = [...text.matchAll(/\/Length (\d+) >>\nstream\n/g)];
  assert.equal(streams.length, 2);
  for (const match of streams) {
    const start = match.index + match[0].length;
    assert.equal(text.slice(start + Number(match[1]), start + Number(match[1]) + 11), "\nendstream\n");
  }
  // the JPEG is embedded byte for byte, with its own size and colour space
  assert.ok(Buffer.from(pdf).indexOf(Buffer.from(jpeg)) > 0);
  assert.ok(text.includes(`/Width 1654 /Height 2339 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>`));
  assert.match(text, /\/MediaBox \[0 0 595 842\]/);
  assert.match(text, /\/Title <FEFF004C006F0061006E00200076006F00750063006800650072>/);
});

test("the image is scaled to fit the page and centred; grey and CMYK colour spaces", () => {
  const square = latin1(jpegToPdf(fakeJpeg({ width: 100, height: 100 }), { page: [595, 842] }));
  assert.match(square, /q\n595 0 0 595 0 123.5 cm\n\/Im0 Do\nQ\n/);
  assert.match(latin1(jpegToPdf(fakeJpeg({ components: 1 }))), /\/ColorSpace \/DeviceGray/);
  assert.match(latin1(jpegToPdf(fakeJpeg({ components: 4 }))), /\/ColorSpace \/DeviceCMYK \/BitsPerComponent 8 \/Decode \[1 0 1 0 1 0 1 0\]/);
  assert.throws(() => jpegToPdf(new Uint8Array([1, 2, 3])), /not a JPEG/);
});

test("PDF titles are UTF-16BE hex, so the rupee sign and Malayalam survive", () => {
  assert.equal(pdfText(""), "<FEFF>");
  assert.equal(pdfText("₹1"), "<FEFF20B90031>");
  assert.equal(pdfText("പ"), "<FEFF0D2A>");
  assert.equal(pdfText("😀"), "<FEFFD83DDE00>");
});

test("wrapText breaks at spaces, then between characters, and keeps line breaks", () => {
  const measure = (text) => text.length;
  assert.deepEqual(wrapText("a bb ccc", 4, measure), ["a bb", "ccc"]);
  assert.deepEqual(wrapText("one", 10, measure), ["one"]);
  assert.deepEqual(wrapText("abcdefghij", 4, measure), ["abcd", "efgh", "ij"]);
  assert.deepEqual(wrapText("ab abcdefgh c", 4, measure), ["ab", "abcd", "efgh", "c"]);
  assert.deepEqual(wrapText("line one\nline two", 20, measure), ["line one", "line two"]);
  assert.deepEqual(wrapText("", 5, measure), [""]);
  assert.deepEqual(wrapText(null, 5, measure), [""]);
  assert.deepEqual(wrapText("a   b", 5, measure), ["a b"]);
  // a letter with a combining mark is one grapheme and is never split
  assert.deepEqual(wrapText("ééé", 2, measure), ["é", "é", "é"]);
});

function fakeElement(styles) {
  return {
    ownerDocument: { defaultView: { getComputedStyle: (element) => element.style } },
    style: styles.sheet,
    querySelector: (selector) => (styles[selector] ? { style: styles[selector] } : null),
  };
}

test("renderSheetJpeg draws the sheet's text with the live colours and returns the JPEG", async () => {
  const calls = [];
  const jpeg = fakeJpeg({ width: PAGE_PX.width, height: PAGE_PX.height });
  const ctx = {
    font: "", letterSpacing: "0px", lang: "inherit", fillStyle: "", strokeStyle: "", lineWidth: 1, textAlign: "", textBaseline: "",
    measureText(text) {
      return { width: text.length * 20 };
    },
    fillText(text, x, y) {
      calls.push({ text, x, y, fill: this.fillStyle, font: this.font, lang: this.lang });
    },
    fillRect(...args) {
      calls.push({ rect: args, fill: this.fillStyle });
    },
    beginPath() {}, moveTo() {}, lineTo() {}, arcTo() {}, closePath() {}, stroke() {}, drawImage() {},
  };
  const canvas = {
    getContext: () => ctx,
    toBlob: (callback, type, quality) => {
      calls.push({ blob: type, quality });
      callback(new Blob([jpeg], { type }));
    },
  };
  globalThis.document = { fonts: { ready: Promise.resolve() }, createElement: (tag) => (tag === "canvas" ? canvas : null) };

  const element = fakeElement({
    sheet: { color: "rgb(1, 1, 1)", backgroundColor: "rgb(255, 255, 255)", fontFamily: "system-ui, sans-serif" },
    ".sheet-fields dt": { color: "rgb(2, 2, 2)" },
    ".letterhead-name": { color: "rgb(3, 3, 3)" },
    ".letterhead": { borderBottomColor: "rgb(4, 4, 4)" },
  });
  const sheet = {
    copy: "Customer",
    letterhead: { name: "Santhwanam", address: "Main Road", phone: "9876543210" },
    title: "Loan voucher · Customer copy",
    date: "2026-10-20",
    fields: [["Loan number", "SAN1L1"], ["Customer", "Anu"], ["Number of items", 2], ["Phone", null]],
    total: { label: "Loan amount", value: "₹1,00,000.00" },
    terms: true,
    signatures: { left: "Received by", right: "Authorised signatory" },
  };
  const bytes = await renderSheetJpeg(sheet, { element });

  assert.deepEqual([...bytes], [...jpeg]);
  assert.deepEqual(calls.find((c) => c.blob), { blob: "image/jpeg", quality: 0.9 });
  assert.deepEqual(calls[0], { rect: [0, 0, PAGE_PX.width, PAGE_PX.height], fill: "rgb(255, 255, 255)" });
  const drawn = (text) => calls.find((c) => c.text === text);
  for (const text of ["Santhwanam", "Main Road", "Phone: 9876543210", "LOAN VOUCHER · CUSTOMER COPY", "Date: 20 Oct 2026",
    "LOAN NUMBER", "SAN1L1", "2", "—", "Loan amount", "₹1,00,000.00", "Terms and conditions", "Received by", "Office seal",
    "Authorised signatory"]) {
    assert.ok(drawn(text), `drew ${text}`);
  }
  assert.equal(drawn("Santhwanam").fill, "rgb(3, 3, 3)");
  assert.equal(drawn("LOAN NUMBER").fill, "rgb(2, 2, 2)");
  assert.equal(drawn("SAN1L1").fill, "rgb(1, 1, 1)");
  assert.match(drawn("SAN1L1").font, /^650 \d+(\.\d+)?px system-ui, sans-serif$/);
  // the Malayalam terms are drawn (wrapped) in Malayalam
  const malayalam = calls.filter((c) => c.lang === "ml" && /[ഀ-ൿ]/.test(c.text ?? ""));
  assert.equal(malayalam.map((c) => c.text).join(" ").replace(/\s+/g, " "), RECEIPT_TERMS.join(" ").replace(/\s+/g, " "));
  // nothing is drawn off the page
  for (const call of calls.filter((c) => c.text !== undefined)) {
    assert.ok(call.x >= 0 && call.x <= PAGE_PX.width && call.y > 0 && call.y < PAGE_PX.height, call.text);
  }
  await assert.rejects(renderSheetJpeg(sheet, { element: null }), /isn't on screen yet/);
});
