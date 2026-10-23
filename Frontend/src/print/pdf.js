// A minimal PDF writer for one JPEG on one page (the shared receipt). Pure functions with
// no browser APIs beyond TextEncoder, so they run under Node's test runner too.

const SOF_MARKERS = new Set([0xc0, 0xc1, 0xc2]); // baseline, extended sequential, progressive
const STANDALONE = (marker) => marker === 0x01 || marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7);
const COLOUR_SPACES = { 1: "/DeviceGray", 3: "/DeviceRGB", 4: "/DeviceCMYK" };

/** Width, height and colour components from a JPEG's start-of-frame segment. */
export function jpegInfo(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) {
    throw new Error("The image is not a JPEG.");
  }
  let pos = 2;
  while (pos < bytes.length) {
    if (bytes[pos] !== 0xff) throw new Error("The JPEG image is damaged.");
    while (pos < bytes.length && bytes[pos] === 0xff) pos += 1; // fill bytes
    if (pos >= bytes.length) break;
    const marker = bytes[pos];
    pos += 1;
    if (STANDALONE(marker)) continue;
    if (marker === 0xd9 || marker === 0xda) break; // end of image, or scan data before any frame
    if (pos + 2 > bytes.length) break;
    const length = (bytes[pos] << 8) | bytes[pos + 1];
    if (length < 2 || pos + length > bytes.length) break;
    if (SOF_MARKERS.has(marker)) {
      if (length < 8) break;
      const components = bytes[pos + 7];
      if (!COLOUR_SPACES[components]) throw new Error("The JPEG image uses an unsupported colour format.");
      return {
        bitsPerComponent: bytes[pos + 2],
        height: (bytes[pos + 3] << 8) | bytes[pos + 4],
        width: (bytes[pos + 5] << 8) | bytes[pos + 6],
        components,
      };
    }
    if (marker >= 0xc3 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      throw new Error("The JPEG image uses an unsupported compression.");
    }
    pos += length;
  }
  throw new Error("The JPEG image has no size information.");
}

/** A PDF number: at most two decimals, never exponent notation (no toFixed). */
function num(value) {
  const hundredths = Math.round(value * 100);
  const sign = hundredths < 0 ? "-" : "";
  const abs = Math.abs(hundredths);
  const whole = Math.floor(abs / 100);
  const frac = abs % 100;
  if (!frac) return `${sign}${whole}`;
  return `${sign}${whole}.${String(frac).padStart(2, "0").replace(/0$/, "")}`;
}

/** A PDF text string as UTF-16BE hex with a byte-order mark, so any script survives. */
export function pdfText(text) {
  let hex = "FEFF";
  for (let i = 0; i < text.length; i += 1) hex += text.charCodeAt(i).toString(16).toUpperCase().padStart(4, "0");
  return `<${hex}>`;
}

/**
 * A single-page PDF 1.4 showing the JPEG scaled to fit the page (A4 in points by default),
 * centred. The JPEG bytes are embedded unchanged (/DCTDecode).
 */
export function jpegToPdf(jpegBytes, { title = "", page = [595, 842] } = {}) {
  const info = jpegInfo(jpegBytes);
  const [pageWidth, pageHeight] = page;
  const scale = Math.min(pageWidth / info.width, pageHeight / info.height);
  const drawWidth = info.width * scale;
  const drawHeight = info.height * scale;
  const x = (pageWidth - drawWidth) / 2;
  const y = (pageHeight - drawHeight) / 2;

  const encoder = new TextEncoder();
  const chunks = [];
  const offsets = [];
  let length = 0;
  const push = (part) => {
    const bytes = typeof part === "string" ? encoder.encode(part) : part;
    chunks.push(bytes);
    length += bytes.length;
  };
  const object = (id, body) => {
    offsets[id] = length;
    push(`${id} 0 obj\n${body}\nendobj\n`);
  };
  const stream = (id, dict, data) => {
    const bytes = typeof data === "string" ? encoder.encode(data) : data;
    offsets[id] = length;
    push(`${id} 0 obj\n<< ${dict} /Length ${bytes.length} >>\nstream\n`);
    push(bytes);
    push("\nendstream\nendobj\n");
  };

  push("%PDF-1.4\n");
  push(new Uint8Array([0x25, 0xe2, 0xe3, 0xcf, 0xd3, 0x0a])); // binary marker comment
  object(1, "<< /Type /Catalog /Pages 2 0 R >>");
  object(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  object(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${num(pageWidth)} ${num(pageHeight)}] `
    + "/Resources << /XObject << /Im0 4 0 R >> /ProcSet [/PDF /ImageB /ImageC] >> /Contents 5 0 R >>");
  const decode = info.components === 4 ? " /Decode [1 0 1 0 1 0 1 0]" : ""; // Adobe CMYK JPEGs are inverted
  stream(4, `/Type /XObject /Subtype /Image /Width ${info.width} /Height ${info.height} `
    + `/ColorSpace ${COLOUR_SPACES[info.components]} /BitsPerComponent ${info.bitsPerComponent}${decode} /Filter /DCTDecode`, jpegBytes);
  stream(5, "", `q\n${num(drawWidth)} 0 0 ${num(drawHeight)} ${num(x)} ${num(y)} cm\n/Im0 Do\nQ\n`);
  object(6, `<< /Title ${pdfText(title)} /Producer ${pdfText("Gold Loan Desk")} >>`);

  const xrefAt = length;
  let xref = `xref\n0 ${offsets.length}\n0000000000 65535 f \n`;
  for (let id = 1; id < offsets.length; id += 1) xref += `${String(offsets[id]).padStart(10, "0")} 00000 n \n`;
  push(xref);
  push(`trailer\n<< /Size ${offsets.length} /Root 1 0 R /Info 6 0 R >>\nstartxref\n${xrefAt}\n%%EOF\n`);

  const out = new Uint8Array(length);
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.length;
  }
  return out;
}
