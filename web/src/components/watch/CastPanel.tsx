// 演员表（§5.4.3）：屏幕右缘窄手柄，点击从右侧滑出面板（半透明遮罩，点遮罩关闭）。
// 手柄闲置 3 秒变半透明，鼠标靠近右缘恢复。点击条目关闭面板并 pin 开该角色仪表盘。

import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { CharacterInfo, Message } from '../../types'
import { Avatar } from '../common/Avatar'
import { formatRelative } from '../../utils/time'
import { cn } from '../../utils/cn'

const ACTIVE_WINDOW_MS = 5 * 60 * 1000
const IDLE_DELAY_MS = 3000
const EDGE_HOT_ZONE = 120

interface CastPanelProps {
  characters: CharacterInfo[]
  messages: Message[]
  /** 点击条目：关闭面板并 pin 开该角色仪表盘 */
  onSelect: (characterId: string) => void
}

export function CastPanel({ characters, messages, onSelect }: CastPanelProps) {
  const [open, setOpen] = useState(false)
  const [idle, setIdle] = useState(false)
  const idleTimer = useRef<number | null>(null)

  const poke = useCallback(() => {
    setIdle(false)
    if (idleTimer.current !== null) window.clearTimeout(idleTimer.current)
    idleTimer.current = window.setTimeout(() => setIdle(true), IDLE_DELAY_MS)
  }, [])

  useEffect(() => {
    poke()
    const onMove = (e: MouseEvent) => {
      if (e.clientX >= window.innerWidth - EDGE_HOT_ZONE) poke()
    }
    window.addEventListener('mousemove', onMove)
    return () => {
      window.removeEventListener('mousemove', onMove)
      if (idleTimer.current !== null) window.clearTimeout(idleTimer.current)
    }
  }, [poke])

  // 每个角色的最近一条消息
  const lastByChar = new Map<string, Message>()
  for (const m of messages) {
    if (m.characterId) lastByChar.set(m.characterId, m)
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen(true)
          poke()
        }}
        onMouseEnter={poke}
        className={cn(
          'fixed right-0 top-1/2 z-30 -translate-y-1/2 rounded-l-lg border border-r-0 border-stage-600 bg-stage-900/90 px-1.5 py-4 text-xs text-stone-300 shadow-lg backdrop-blur transition-opacity duration-500 hover:text-gold',
          '[writing-mode:vertical-rl]',
          idle && !open && 'opacity-30',
        )}
      >
        🎭 演员表 · {characters.length} 人
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              key="cast-overlay"
              className="fixed inset-0 z-40 bg-black/50"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
            />
            <motion.aside
              key="cast-panel"
              className="fixed right-0 top-0 z-50 flex h-full w-80 flex-col border-l border-stage-700 bg-stage-900"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.25, ease: 'easeOut' }}
            >
              <header className="flex items-center justify-between border-b border-stage-700 px-4 py-3">
                <span className="text-sm text-stone-300">🎭 演员表 · {characters.length} 人</span>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="text-stone-500 transition-colors hover:text-stone-200"
                >
                  ✕
                </button>
              </header>
              <div className="flex-1 overflow-y-auto p-2">
                {characters.map((c) => {
                  const last = lastByChar.get(c.id)
                  const active = last ? Date.now() - +new Date(last.timestamp) < ACTIVE_WINDOW_MS : false
                  return (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => {
                        setOpen(false)
                        onSelect(c.id)
                      }}
                      className="flex w-full items-start gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-stage-800"
                    >
                      <Avatar name={c.name} color={c.color} size={34} />
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="text-sm font-medium" style={{ color: c.color }}>
                            {c.name}
                          </span>
                          <span
                            className={cn(
                              'inline-block h-1.5 w-1.5 rounded-full',
                              active ? 'bg-emerald-400' : 'bg-stage-600',
                            )}
                          />
                          <span className="text-xs text-stone-500">
                            {last ? (active ? '活跃' : '沉默') : '未出场'}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-stone-500">
                          {last ? last.content : '——'}
                        </span>
                      </span>
                      {last && (
                        <span className="shrink-0 text-xs text-stone-600">{formatRelative(last.timestamp)}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
