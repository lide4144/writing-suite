// 浮动仪表盘（§5.4.2）：情绪标签 / 最近内心独白 / 最近记忆活动 / 聚焦按钮。
// 状态数据以全局 store 的 characterStates 为准（WS state_change 实时更新）。
// 同一组件复用于两种形态：悬停浮层（外层定位）与 pin 固定（视口右侧排布）。

import type { CharacterInfo } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { Avatar } from '../common/Avatar'
import { cn } from '../../utils/cn'

interface DashboardPanelProps {
  character: CharacterInfo
  pinned: boolean
  onPin: () => void
  onUnpin: () => void
  /** 聚焦此角色：滚动到该角色最近一条消息并高亮 */
  onFocus: (characterId: string) => void
  /** 悬停形态下，面板自身的 hover 也维持展开（移出 500ms 后收起） */
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export function DashboardPanel({
  character,
  pinned,
  onPin,
  onUnpin,
  onFocus,
  onMouseEnter,
  onMouseLeave,
}: DashboardPanelProps) {
  const state = useAppStore((s) => s.characterStates[character.id])
  const memory = state?.lastMemoryActivity ?? null

  return (
    <div
      className="w-[320px] rounded-xl border bg-stage-900/95 shadow-2xl backdrop-blur"
      style={{ borderColor: `${character.color}55` }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <header className="flex items-center gap-2.5 px-4 pt-3">
        <Avatar name={character.name} color={character.color} size={34} />
        <div className="min-w-0">
          <div className="truncate text-sm font-medium" style={{ color: character.color }}>
            {character.name}
          </div>
          <div className="text-xs text-stone-400">{state?.emotion ?? '状态未知'}</div>
        </div>
        <button
          type="button"
          onClick={pinned ? onUnpin : onPin}
          title={pinned ? '取消固定' : '固定面板'}
          className={cn(
            'ml-auto rounded-md px-1.5 py-1 text-sm transition-colors hover:bg-white/10',
            pinned ? 'text-gold' : 'text-stone-500',
          )}
        >
          📌
        </button>
      </header>

      <div className="max-h-[280px] space-y-3 overflow-y-auto px-4 py-3">
        <section>
          <div className="mb-1 text-xs tracking-wide text-stone-500">最近的内心独白</div>
          {state?.innerThought ? (
            <p
              className="rounded-r-lg border-l-2 bg-stage-950/70 px-3 py-2 font-serif text-sm leading-relaxed text-stone-300"
              style={{ borderLeftColor: character.color }}
            >
              「{state.innerThought}」
            </p>
          ) : (
            <p className="text-sm text-stone-600">暂无内心独白</p>
          )}
        </section>

        <section>
          <div className="mb-1 text-xs tracking-wide text-stone-500">最近的记忆活动</div>
          {memory ? (
            <p className="font-mono text-xs leading-relaxed text-stone-400">
              {memory.type === 'recall' ? '📖 recall' : '✏️ memorize'}：{memory.content}
            </p>
          ) : (
            <p className="text-sm text-stone-600">暂无记忆活动</p>
          )}
        </section>
      </div>

      <footer className="border-t border-stage-700/60 px-4 py-2.5">
        <button
          type="button"
          onClick={() => onFocus(character.id)}
          className="w-full rounded-lg bg-stage-800 px-3 py-1.5 text-xs text-stone-300 transition-colors hover:bg-stage-700 hover:text-stone-100"
        >
          🎯 聚焦此角色最近活动
        </button>
      </footer>
    </div>
  )
}
