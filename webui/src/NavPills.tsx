import { useRef, useState } from 'react'
import { Link } from './router'
import { cn } from './ui'

export interface NavItem {
  label: string
  to?: string
  href?: string
  external?: boolean
  active?: boolean
}

/** 页头中间的导航： 一块胶囊跟着鼠标在链接之间滑动，当前页下面一个小点 */
export function NavPills({ items }: { items: NavItem[] }) {
  const box = useRef<HTMLElement>(null)
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null)
  const over = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a')
    if (a) setPill({ x: a.offsetLeft, w: a.offsetWidth })
  }
  const cls = (active?: boolean) =>
    cn('relative flex h-8 items-center whitespace-nowrap rounded-full px-3 text-small no-underline transition-colors', active ? 'font-medium text-fg-1' : 'text-fg-2 hover:text-fg-1')
  return (
    <nav ref={box} className="relative flex items-center" onMouseOver={over} onMouseLeave={() => setPill(null)}>
      <span
        aria-hidden="true"
        className={cn('absolute top-0 left-0 h-8 rounded-full bg-fill-2 transition-[transform,width,opacity] duration-200', pill ? 'opacity-100' : 'opacity-0')}
        style={{ transform: `translateX(${pill?.x ?? 0}px)`, width: pill?.w ?? 0 }}
      />
      {items.map((it) =>
        it.to ? (
          <Link key={it.label} to={it.to} className={cls(it.active)} aria-current={it.active ? 'page' : undefined}>
            {it.label}
            {it.active && <span aria-hidden="true" className="absolute bottom-0 left-1/2 size-1 -translate-x-1/2 rounded-full bg-fg-1" />}
          </Link>
        ) : (
          <a key={it.label} href={it.href} target={it.external ? '_blank' : undefined} rel="noreferrer" className={cls()}>
            {it.label}
          </a>
        ),
      )}
    </nav>
  )
}
