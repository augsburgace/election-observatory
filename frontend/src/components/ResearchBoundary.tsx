import { Component, type ErrorInfo, type ReactNode } from "react";
import { Empty } from "./ui";

/** Keep navigation and the pinned research scope usable if a renderer fails. */
export default class ResearchBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Research visualization failed", error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return (
        <Empty
          title="This research view needs to reload"
          action={
            <button className="button primary" onClick={() => location.reload()}>
              Reload this investigation
            </button>
          }
        >
          A visualization could not render. Your evidence, saved views and notes
          are safe. Reload this exact investigation, or use the navigation to
          open another research tool.
        </Empty>
      );
    }
    return this.props.children;
  }
}
