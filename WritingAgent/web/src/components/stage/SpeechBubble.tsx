// 像素风气泡：阶梯边框 + 错位方块尾巴。
// dialogue：深色底 + 角色色边框；thought：半透明虚线框（思想泡，全知读者专属）。

import { cn } from '../../utils/cn'

interface SpeechBubbleProps {
  text: string
  kind: 'dialogue' | 'thought'
  color?: string // 角色主题色（dialogue 时传入）
}

export function SpeechBubble({ text, kind, color }: SpeechBubbleProps) {
  if (kind === 'thought') {
    return (
      <div className={cn('pixel-bubble-pop pointer-events-none relative max-w-44 rounded-xl border border-dashed border-stone-400/60 bg-stage-950/70 px-2.5 py-1.5 text-[11px] italic leading-snug text-stone-300')}>
        💭 {text}
        <span className="absolute -bottom-1.5 left-4 h-1.5 w-1.5 rounded-full bg-stone-400/60" />
        <span className="absolute -bottom-3 left-6 h-1 w-1 rounded-full bg-stone-400/40" />
      </div>
    )
  }
  return (
    <div
      className={cn('pixel-bubble-pop pointer-events-none relative max-w-52 border-2 bg-stage-950/90 px-2.5 py-1.5 text-xs leading-snug text-stone-100')}
      style={{ borderColor: color ?? '#8a8a96' }}
    >
      {text}
      {/* 阶梯尾巴 */}
      <span className="absolute -bottom-2 left-3 h-2 w-2" style={{ backgroundColor: color ?? '#8a8a96' }} />
      <span className="absolute -bottom-3.5 left-5 h-1.5 w-1.5" style={{ backgroundColor: color ?? '#8a8a96' }} />
    </div>
  )
}
