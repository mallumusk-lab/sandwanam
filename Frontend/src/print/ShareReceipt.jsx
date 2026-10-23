import { useCallback, useState } from "react";
import { saveBlob } from "../api/client.js";
import { useSubmit } from "../hooks/useAsync.js";
import { PHONE_PATTERN } from "../lib/validation.js";
import { Button } from "../ui/controls.jsx";
import { useToast } from "../ui/feedback.jsx";
import { Icon } from "../ui/Icon.jsx";
import { Modal } from "../ui/Modal.jsx";
import { jpegToPdf } from "./pdf.js";
import { renderSheetJpeg } from "./receiptCanvas.js";

const SHARE_TEXT = "Your receipt is attached as a PDF.";

/** A file name with only letters, digits, dots and dashes (loan numbers are safe, but be sure). */
export function pdfFileName(name) {
  return String(name).replace(/[^A-Za-z0-9.-]+/g, "-");
}

/** wa.me link for an Indian mobile number, or null when the number isn't one. Short text only. */
export function whatsappLink(phone) {
  const digits = String(phone ?? "").replace(/[\s-]/g, "").replace(/^\+91/, "");
  if (!PHONE_PATTERN.test(digits)) return null;
  return `https://wa.me/91${digits}?text=${encodeURIComponent(SHARE_TEXT)}`;
}

export function mailtoLink(title) {
  return `mailto:?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(`${SHARE_TEXT} Please find it attached.`)}`;
}

function SavedDialog({ saved, onClose }) {
  const whatsapp = whatsappLink(saved.phone);
  return (
    <Modal open onClose={onClose} title="Receipt saved as PDF"
      description={`${saved.name} is in your downloads.`}
      footer={<Button variant="primary" onClick={onClose}>Done</Button>}>
      <div className="stack">
        <p>This device can't share files directly. Open WhatsApp or email with a button below, then attach the saved PDF from your downloads.</p>
        <div className="cluster">
          {whatsapp ? (
            <a className="btn btn-secondary" href={whatsapp} target="_blank" rel="noopener noreferrer">
              <Icon name="share" />WhatsApp the customer
            </a>
          ) : null}
          <a className="btn btn-secondary" href={mailtoLink(saved.title)}>
            <Icon name="mail" />Email
          </a>
        </div>
        {whatsapp ? null : <p className="muted">The customer's phone number isn't a 10-digit mobile number, so WhatsApp isn't offered.</p>}
      </div>
    </Modal>
  );
}

/**
 * Share the Customer copy as a one-page PDF. The PDF is drawn from `sheet` (built from the
 * /receipts/* data the page loaded); `styleSource` is the copy on screen, for colours and fonts.
 */
export function ShareReceiptButton({ sheet, styleSource, fileName, title, phone }) {
  const toast = useToast();
  const [saved, setSaved] = useState(null);
  const action = useCallback(async () => {
    let file;
    try {
      const jpeg = await renderSheetJpeg(sheet, { element: styleSource?.current });
      const pdf = jpegToPdf(jpeg, { title });
      file = new File([pdf], pdfFileName(fileName), { type: "application/pdf" });
    } catch (err) {
      toast.error("The PDF couldn't be made", err.message);
      return;
    }
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title, text: SHARE_TEXT });
        return;
      } catch (err) {
        if (err?.name === "AbortError") return; // closed the share sheet
        // anything else (for example, sharing blocked): save the file instead
      }
    }
    saveBlob(file, file.name);
    setSaved({ name: file.name, title, phone });
  }, [sheet, styleSource, fileName, title, phone, toast]);
  const [share, sharing] = useSubmit(action);
  return (
    <>
      <Button icon="share" onClick={share} loading={sharing} disabled={!sheet}>Share</Button>
      {saved ? <SavedDialog saved={saved} onClose={() => setSaved(null)} /> : null}
    </>
  );
}
