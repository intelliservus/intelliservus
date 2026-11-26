/**
 * 单飞刷新：并发的 401 共享同一次 refresh 请求，避免刷新风暴。
 * 刷新结束（成功或失败）后释放，下一次 401 可继续触发。
 */
export function createRefreshQueue(refresh: () => Promise<string | null>) {
  let inFlight: Promise<string | null> | null = null;

  return function refreshOnce(): Promise<string | null> {
    if (!inFlight) {
      inFlight = refresh().finally(() => {
        inFlight = null;
      });
    }
    return inFlight;
  };
}
