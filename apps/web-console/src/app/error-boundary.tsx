import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';

type Props = { children: ReactNode };
type State = { error: Error | null };

export class AppErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('未捕获的渲染错误', error, info.componentStack);
  }

  private readonly reset = () => {
    this.setState({ error: null });
  };

  override render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="mx-auto flex min-h-svh max-w-md flex-col items-start justify-center gap-4 p-6"
        >
          <h1 className="text-xl font-semibold">页面出错了</h1>
          <p className="text-sm text-muted-foreground">{this.state.error.message}</p>
          <Button onClick={this.reset}>重试</Button>
        </div>
      );
    }

    return this.props.children;
  }
}
