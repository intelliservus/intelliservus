/**
 * access token 只保存在内存中，刷新页面即失效，由 refresh cookie 换回。
 * 禁止写入 localStorage / sessionStorage 或任何可持久化位置（事实源 §14.2）。
 */
let accessToken: string | null = null;

export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string | null): void {
    accessToken = token;
  },
};
