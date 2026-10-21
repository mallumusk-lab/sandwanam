import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Run an async loader and track { data, error, loading, loadedAt }.
 * - When the inputs change, the previous data is cleared so nothing stale is shown under a
 *   new branch, customer or period; `reload()` keeps the current data while refreshing.
 * - Pass `resetKey` to clear only when it changes (e.g. the filters, not the page number):
 *   paging then keeps the current rows, and the focused pager button, on screen.
 * - Aborts superseded requests and ignores responses that arrive late.
 */
export function useAsync(loader, deps, resetKey) {
  const [state, setState] = useState({ data: null, error: null, loading: true, loadedAt: null });
  const generation = useRef(0);
  const controllerRef = useRef(null);
  const lastResetKey = useRef(undefined);
  const resetKeyRef = useRef(resetKey);
  resetKeyRef.current = resetKey;

  const run = useCallback((keepData) => {
    const id = ++generation.current;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((previous) => ({
      data: keepData ? previous.data : null,
      error: null,
      loading: true,
      loadedAt: keepData ? previous.loadedAt : null,
    }));
    loader(controller.signal)
      .then((data) => {
        if (id === generation.current) setState({ data, error: null, loading: false, loadedAt: new Date().toISOString() });
      })
      .catch((error) => {
        if (controller.signal.aborted || id !== generation.current) return;
        setState((previous) => ({ ...previous, error, loading: false }));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    const key = resetKeyRef.current;
    const keep = key !== undefined && lastResetKey.current === key;
    lastResetKey.current = key;
    run(keep);
    return () => controllerRef.current?.abort();
  }, [run]);

  const reload = useCallback(() => run(true), [run]);

  return { ...state, reload };
}

/** Track a mutation so buttons can be disabled while it runs (prevents double submits). */
export function useSubmit(action) {
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const submit = useCallback(
    async (...args) => {
      if (busy.current) return undefined;
      busy.current = true;
      setPending(true);
      try {
        return await action(...args);
      } finally {
        busy.current = false;
        setPending(false);
      }
    },
    [action],
  );
  return [submit, pending];
}

export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · Gold Loan Desk` : "Gold Loan Desk";
  }, [title]);
}

/** Move focus to an element (usually a heading) whenever `key` changes after the first render. */
export function useFocusOnChange(key) {
  const ref = useRef(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    ref.current?.focus();
  }, [key]);
  return ref;
}
