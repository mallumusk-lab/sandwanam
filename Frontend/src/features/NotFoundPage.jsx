import { useDocumentTitle } from "../hooks/useAsync.js";
import { Button } from "../ui/controls.jsx";
import { EmptyState } from "../ui/feedback.jsx";

export default function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <div className="page narrow">
      <EmptyState icon="search" headingLevel={1} title="This page doesn't exist" action={<Button variant="primary" to="/">Go to the home page</Button>}>
        The link may be old, or the address may have a typo.
      </EmptyState>
    </div>
  );
}
