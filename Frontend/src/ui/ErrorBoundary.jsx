import { Component } from "react";
import { Button } from "./controls.jsx";
import { Icon } from "./Icon.jsx";

/** Catches render errors so one broken screen never blanks the whole application. */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false, resetKey: props.resetKey };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props, state) {
    // Navigating elsewhere clears the error.
    return props.resetKey !== state.resetKey ? { failed: false, resetKey: props.resetKey } : null;
  }

  componentDidCatch(error, info) {
    console.error("Screen failed to render", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page narrow" id="main">
        <div className="state state-error" role="alert">
          <div className="state-icon"><Icon name="alertCircle" /></div>
          <h1>Something went wrong on this screen</h1>
          <p>Nothing you saved was lost. Reload the page, or go back to the home page.</p>
          <div className="cluster">
            <Button variant="primary" icon="refresh" onClick={() => window.location.reload()}>Reload</Button>
            <Button onClick={() => window.location.assign("/")}>Home page</Button>
          </div>
        </div>
      </main>
    );
  }
}
