"use client";

/**
 * 通用错误边界。
 *
 * 捕获子树 React 渲染异常，避免整个 studio/admin 白屏。
 * 仅 client side。
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
};

type State = { hasError: boolean; error?: Error };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error("[ErrorBoundary]", error, info);
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <div className="grid min-h-[60vh] place-items-center p-8">
        <div className="max-w-md space-y-3 rounded-3xl border border-rose-200 bg-rose-50 p-6 text-center">
          <p className="text-lg font-bold text-rose-900">出错了</p>
          <p className="text-sm text-rose-700">
            {this.state.error?.message || "页面加载时出现未预期的错误。"}
          </p>
          <div className="flex justify-center gap-2 pt-2">
            <Button variant="secondary" onClick={this.handleReset}>
              重试
            </Button>
            <Button onClick={() => window.location.reload()}>刷新页面</Button>
          </div>
        </div>
      </div>
    );
  }
}
