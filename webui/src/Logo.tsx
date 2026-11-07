import { useId } from 'react'

/**
 * LarkAgentX 的标志： 飞书的三色小鸟，翅膀换成一颗 AI 的星光。
 * 深色头翼跟随主题（--logo-head），其余两色固定。
 */
export function Mark({ className, size = 24 }: { className?: string; size?: number }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden="true" className={className}>
      <path fill="#3370ff" d="M5 24C12 31.2 20 36.6 28.5 40.5 36 44 44.3 43.8 50.8 39.2 46.6 49.6 36.6 56.5 25.5 56.5 14.2 56.5 5 48.8 5 38.8Z" />
      <path style={{ fill: 'var(--logo-head)' }} d="M28.5 40.5C33.2 36.6 38 30.8 43 27.6 47.2 25 52.4 23.9 59.6 24.4 56.6 27 54.1 31.6 51.6 36 46.8 44.6 36.8 46.4 28.5 40.5Z" />
      <path fill="#00d6b9" d="M28.5 3C30.12 15.35 31.58 17.08 42 19 31.58 20.92 30.12 22.65 28.5 35 26.88 22.65 25.42 20.92 15 19 25.42 17.08 26.88 15.35 28.5 3Z" />
    </svg>
  )
}

/** 页脚的通栏大字： 首屏同款点阵填充 */
export function FooterName({ className }: { className?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg viewBox="0 0 1000 206" aria-hidden="true" className={className} style={{ color: 'var(--fg-3)' }}>
      <defs>
        <pattern id={`d${id}`} width="5" height="5" patternUnits="userSpaceOnUse">
          <circle cx="2.5" cy="2.5" r="1.25" fill="currentColor" />
        </pattern>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity=".1" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[`url(#g${id})`, `url(#d${id})`].map((fill) => (
        <text key={fill} x="0" y="150" textLength={1000} lengthAdjust="spacing" fill={fill} style={{ fontFamily: 'var(--font-sans)', fontSize: 188, fontWeight: 700, letterSpacing: '-0.04em' }}>
          LarkAgentX
        </text>
      ))}
    </svg>
  )
}
