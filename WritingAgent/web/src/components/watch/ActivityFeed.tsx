// 中栏活动流（§5.4.1）：全宽居中列，消息严格按时间升序。
// 自动滚动：用户在底部则跟随新消息；已上翻阅读则不打扰，显示「↓ 回到最新」。

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { CharacterInfo, Message } from '../../types'
import { GM_COLOR } from '../../mock/data'
import { MessageCard } from './MessageCard'

/** 外部跳转目标（时间轴点击 / 仪表盘聚焦 / 摘要弹窗按钮） */
export interface SeekTarget {
  id: string
  /** 每次跳转递增，保证重复点同一目标也能触发 */
  nonce: number
}

interface ActivityFeedProps {
  messages: Message[]
  characters: CharacterInfo[]
  seekTarget: SeekTarget | null
  onCharacterEnter: (characterId: string, rect: DOMRect) => void
  onCharacterLeave: (characterId: string) => void
}

const BOTTOM_THRESHOLD = 80
const HIGHLIGHT_MS = 2000

export function ActivityFeed({ messages, characters, seekTarget, onCharacterEnter, onCharacterLeave }: ActivityFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(false)
  const atBottomRef = useRef(false)
  const [newCount, setNewCount] = useState(0)
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const prevLenRef = useRef(0)
  const initializedRef = useRef(false)

  const colorOf = (m: Message): string =>
    (m.characterId && characters.find((c) => c.id === m.characterId)?.color) || GM_COLOR

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

  // 新消息到达：在底部则跟随滚动，否则累计未读数
  useEffect(() => {
    const delta = messages.length - prevLenRef.current
    prevLenRef.current = messages.length
    if (!initializedRef.current) {
      // 初次载入：从第一条开始展示（§5.4.5），不滚动
      initializedRef.current = messages.length > 0
      const el = scrollRef.current
      if (el && el.scrollHeight <= el.clientHeight + 4) {
        atBottomRef.current = true
        setAtBottom(true)
      }
      return
    }
    if (delta <= 0) return
    if (atBottomRef.current) {
      scrollToBottom()
    } else {
      setNewCount((c) => c + delta)
    }
  }, [messages.length])

  // 外部跳转：滚动到目标消息并短暂高亮
  useEffect(() => {
    if (!seekTarget) return
    const el = scrollRef.current?.querySelector(`[data-mid="${seekTarget.id}"]`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setHighlightId(seekTarget.id)
    const timer = window.setTimeout(() => setHighlightId(null), HIGHLIGHT_MS)
    return () => window.clearTimeout(timer)
  }, [seekTarget])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const at = el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD
    atBottomRef.current = at
    setAtBottom(at)
    if (at) setNewCount(0)
  }

  // 章节分隔线（午后 → 破冰 → 冲突 ……）
  let prevChapter: string | null = null

  return (
    <div className="relative h-full">
      <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-3 px-6 py-8">
          {messages.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center gap-3 text-stone-500">
              <span className="text-3xl">🎭</span>
              <p className="font-serif">舞台空无一人，等待开场…</p>
            </div>
          ) : (
            messages.map((m) => {
              const showChapter = m.chapter !== null && m.chapter !== prevChapter
              prevChapter = m.chapter
              return (
                <div key={m.id}>
                  {showChapter && (
                    <div className="flex items-center gap-3 py-2">
                      <span className="h-px flex-1 bg-stage-700" />
                      <span className="font-serif text-xs tracking-[0.3em] text-stone-500">{m.chapter}</span>
                      <span className="h-px flex-1 bg-stage-700" />
                    </div>
                  )}
                  <MessageCard
                    message={m}
                    color={colorOf(m)}
                    highlighted={highlightId === m.id}
                    onCharacterEnter={onCharacterEnter}
                    onCharacterLeave={onCharacterLeave}
                  />
                </div>
              )
            })
          )}
        </div>
      </div>

      <AnimatePresence>
        {!atBottom && messages.length > 0 && (
          <motion.button
            type="button"
            className="absolute bottom-4 right-6 z-10 rounded-full border border-stage-600 bg-stage-900/95 px-4 py-2 text-xs text-stone-300 shadow-xl backdrop-blur transition-colors hover:border-gold/50 hover:text-gold"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            onClick={() => {
              scrollToBottom()
              setNewCount(0)
            }}
          >
            ↓ 回到最新{newCount > 0 ? ` · ${newCount} 条新消息` : ''}
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}
