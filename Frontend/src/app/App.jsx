import { BrowserRouter, useLocation } from "react-router-dom";
import { AuthProvider } from "../auth/AuthContext.jsx";
import { ErrorBoundary } from "../ui/ErrorBoundary.jsx";
import { ToastProvider } from "../ui/feedback.jsx";
import { AppRoutes } from "./routes.jsx";

function GuardedRoutes() {
  const { pathname } = useLocation();
  return (
    <ErrorBoundary resetKey={pathname}>
      <AppRoutes />
    </ErrorBoundary>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <GuardedRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
