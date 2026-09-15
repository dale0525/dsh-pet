/**
 * 移动端判定与视口监听（纯逻辑层，无 React 依赖）
 *
 * 【为什么要在移动端网页禁用桌宠功能】
 * 1. 视口与核心交互遮挡：手机与平板等移动端视口空间极度受限，桌面宠物即便缩至最小
 *    也容易遮挡 DSH 核心界面的会话列表、输入框、发送按钮及操作菜单；且触控拖拽与网页原生
 *    滑动手势严重冲突，极易引发误触；
 * 2. 避免无谓能耗与后台请求：桌面宠物一旦挂载，就会启动余额、碎碎念、工作状态等多条
 *    轮询（见 pet.ts PetMulti / PetCard）；在移动端挂载即返回 null，使组件树根本不被创建，
 *    彻底省去移动端电池供电与蜂窝网络下的无效拉取与定时器开销。
 *
 * 【为什么采用「粗指针 OR 窄视口 (< 768px)」双重判据】
 * - 粗指针（(pointer: coarse)）：精准识别以触屏为主交互手段的物理设备（手机、平板），
 *   即便处于横屏等宽视口下，因缺乏高精度悬停与鼠标右键交互，依然判定为移动端；
 * - 窄视口（(max-width: 767.98px)）：覆盖 PC 桌面浏览器被缩放到窄窗口的情形（此时页面
 *   折叠为移动端排版，桌宠同样破坏版面）；上限取 767.98px 规避浮点设备像素比（DPR）的
 *   舍入误差，确保 768px 整（平板竖屏标准界限）不被误判为窄视口。
 *
 * 【为什么提供订阅监听与幂等解绑】
 * 视口尺寸与输入设备形态存在运行时动态切换（用户旋转屏幕、拖拽调节浏览器窗口尺寸、
 * 插拔外接鼠标或触控板）；暴露 subscribe 机制让上层容器在环境切换时能够干净地挂载或
 * 卸载整个宠物树，且解绑函数具备幂等性以防多重卸载抛错。
 */

/** 媒体查询串：粗指针（触摸设备）或窄视口（< 768px）任一命中即视为移动端 */
export const MOBILE_MEDIA_QUERY = '(pointer: coarse), (max-width: 767.98px)';

/** 判定是否移动端网页环境。
 *  env 缺省取全局 window；无 matchMedia（SSR / 桌面壳）时返回 false（不禁用）。 */
export function isMobileEnvironment(env?: { matchMedia?: (query: string) => { matches: boolean } }): boolean {
  const targetEnv = env ?? (globalThis as { matchMedia?: (query: string) => { matches: boolean } });
  if (typeof targetEnv?.matchMedia !== 'function') {
    return false;
  }
  return targetEnv.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

/** 判定所需的最小环境形状（只用到 matchMedia，便于单测注入伪造实现）。 */
export interface MobileEnv {
  matchMedia?: (query: string) => {
    matches: boolean;
    addEventListener?: (type: string, listener: () => void) => void;
    removeEventListener?: (type: string, listener: () => void) => void;
  };
}

/** 订阅移动端判定的变化（窗口缩放 / 设备旋转）。返回解绑函数。
 *  注意：`pointer` 媒体特性反映的是主输入机制，插拔外接鼠标是否触发 change 事件在各平台
 *  并不可靠，故这里只承诺窗口尺寸与设备旋转引起的变化。
 *  env 缺省取全局 window；无 matchMedia 时立即以 false 回调一次并返回一个空解绑函数。 */
export function subscribeMobileEnvironment(onChange: (isMobile: boolean) => void, env?: MobileEnv): () => void {
  const targetEnv = env ?? (globalThis as MobileEnv);

  if (typeof targetEnv?.matchMedia !== 'function') {
    onChange(false);
    return () => {};
  }

  const mql = targetEnv.matchMedia(MOBILE_MEDIA_QUERY);
  onChange(mql.matches);

  let disposed = false;
  const handler = () => {
    if (disposed) return;
    onChange(mql.matches);
  };

  // 只走标准的 EventTarget 接口：DSH 面向现代浏览器（本插件亦不支持 Safari），
  // 已废弃的 MediaQueryList.addListener 退化分支属多余兼容，故不保留。
  mql.addEventListener?.('change', handler);
  return () => {
    if (disposed) return;
    disposed = true;
    mql.removeEventListener?.('change', handler);
  };
}
