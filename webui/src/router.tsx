import { type AnchorHTMLAttributes, useSyncExternalStore } from 'react'

/** 很小的路径路由： 页面不多，不值得多一个依赖。后端把未知路径都回 index.html。 */
const listeners = new Set<() => void>()

function subscribe(fn: () => void) {
  listeners.add(fn)
  window.addEventListener('popstate', fn)
  return () => {
    listeners.delete(fn)
    window.removeEventListener('popstate', fn)
  }
}

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === location.pathname) return
  history[opts.replace ? 'replaceState' : 'pushState'](null, '', to)
  listeners.forEach((f) => f())
}

export function usePath(): string {
  return useSyncExternalStore(subscribe, () => location.pathname)
}

export function Link({ to, onClick, ...rest }: { to: string } & AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a
      href={to}
      onClick={(e) => {
        onClick?.(e)
        if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
        e.preventDefault()
        navigate(to)
      }}
      {...rest}
    />
  )
}
