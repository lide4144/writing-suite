// 观众席（§5）——全屏沉浸页面：中栏活动流 + 浮动仪表盘 + 演员表 + 底部时间轴。
// 布局为全宽中栏，无固定左右栏；导航栏由全局 Shell 浮于顶部，本页不留占位。

import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useSceneWatch } from '../components/watch/useSceneWatch'
import { Prologue } from '../components/watch/Prologue'
import { ActivityFeed, type SeekTarget } from '../components/watch/ActivityFeed'
import { DashboardPanel } from '../components/watch/DashboardPanel'
import { CastPanel } from '../components/watch/CastPanel'
import { Timeline } from '../components/watch/Timeline'
import { SummaryModal } from '../components/watch/SummaryModal'
import { PixelStage } from '../components/stage/PixelStage'
import { cn } from '../utils/cn'

const PROLOGUE_MIN_MS = 1400 // 序幕最短驻留，保证可读
const HISTORY_TAG_MS = 4000
const HOVER_OPEN_DELAY = 300
const HOVER_CLOSE_DELAY = 500
const PANEL_WIDTH = 320
const PANEL_MAX_HEIGHT = 400
const MAX_PINNED = 3

/** 加载骨架：全宽中栏占位 + 底部时间轴占位（§5.4.5） */
function FeedSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 px-6 py-10">
      {[80, 60, 70, 45].map((w, i) => (
        <div key={i} className="animate-pulse rounded-xl border border-stage-800 bg-stage-900 p-4">
          <div className="mb-3 h-3 rounded bg-stage-700" style={{ width: `${w / 2}%` }} />
          <div className="h-3 rounded bg-stage-800" style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  )
}

export function WatchPage() {
  const { sceneId } = useParams<{ sceneId: string }>()
  const { scene, messages, characters, summary, loading, notFound, ended, liveMilestones } =
    useSceneWatch(sceneId)

  // —— 序幕时序（§5.4.5）：数据就绪后再驻留片刻，随后淡出、正式界面淡入 ——
  const [prologueDone, setPrologueDone] = useState(false)
  useEffect(() => {
    if (loading || notFound || !scene) return
    const timer = window.setTimeout(() => setPrologueDone(true), PROLOGUE_MIN_MS)
    return () => window.clearTimeout(timer)
  }, [loading, notFound, scene])

  // —— 「此前已有 XX 轮互动」标签：序幕谢幕后短暂显示 ——
  const [historyTag, setHistoryTag] = useState(false)
  useEffect(() => {
    if (!prologueDone || messages.length === 0) return
    setHistoryTag(true)
    const timer = window.setTimeout(() => setHistoryTag(false), HISTORY_TAG_MS)
    return () => window.clearTimeout(timer)
    // 仅在序幕结束时判定一次，直播新消息不应重新触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prologueDone])

  // —— 补课模式（§5.4.6）：进入时已落幕/有未读事件的场景才弹；
  // 正在直播（含观看中途落幕）的现场不弹，摘要留给下次进入 ——
  const liveAtLoadRef = useRef<boolean | null>(null)
  if (scene && liveAtLoadRef.current === null) liveAtLoadRef.current = scene.status === 'running'
  const [summaryOpen, setSummaryOpen] = useState(false)
  useEffect(() => {
    if (!prologueDone || !summary || !scene) return
    if (!liveAtLoadRef.current && (ended || scene.hasUnreadEvents)) setSummaryOpen(true)
  }, [prologueDone, summary, scene, ended])

  // —— 活动流跳转 / 高亮 ——
  const [seekTarget, setSeekTarget] = useState<SeekTarget | null>(null)

  // —— 中栏视图：活动流 / 像素舞台 ——
  const [view, setView] = useState<'feed' | 'stage'>('feed')
  const seek = (id: string) => setSeekTarget({ id, nonce: Date.now() })
  const seekLatest = () => {
    const last = messages[messages.length - 1]
    if (last) seek(last.id)
  }
  const seekFirst = () => {
    const first = messages[0]
    if (first) seek(first.id)
  }
  const focusCharacter = (characterId: string) => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].characterId === characterId) {
        seek(messages[i].id)
        return
      }
    }
  }

  // —— 悬停仪表盘（§5.4.2）：悬停 300ms 展开，移出 500ms 收起 ——
  const [hoverPanel, setHoverPanel] = useState<{ characterId: string; rect: DOMRect } | null>(null)
  const openTimer = useRef<number | null>(null)
  const closeTimer = useRef<number | null>(null)

  const clearHoverTimers = () => {
    if (openTimer.current !== null) {
      window.clearTimeout(openTimer.current)
      openTimer.current = null
    }
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }

  const handleCharacterEnter = (characterId: string, rect: DOMRect) => {
    clearHoverTimers()
    openTimer.current = window.setTimeout(() => setHoverPanel({ characterId, rect }), HOVER_OPEN_DELAY)
  }
  const scheduleHoverClose = () => {
    clearHoverTimers()
    closeTimer.current = window.setTimeout(() => setHoverPanel(null), HOVER_CLOSE_DELAY)
  }

  // —— pin 固定：不随移出收起，视口右侧纵向排布，最多 MAX_PINNED 个（超出挤掉最早） ——
  const [pinnedIds, setPinnedIds] = useState<string[]>([])
  const pinCharacter = (characterId: string) => {
    setPinnedIds((prev) => [...prev.filter((id) => id !== characterId), characterId].slice(-MAX_PINNED))
    setHoverPanel(null)
  }
  const unpinCharacter = (characterId: string) => {
    setPinnedIds((prev) => prev.filter((id) => id !== characterId))
  }

  const hoverCharacter = hoverPanel
    ? (characters.find((c) => c.id === hoverPanel.characterId) ?? null)
    : null

  // 面板位置：优先触发点右侧，空间不足放左侧，纵向钳制在视口内
  let hoverPos: { left: number; top: number } | null = null
  if (hoverPanel) {
    let left = hoverPanel.rect.right + 12
    if (left + PANEL_WIDTH > window.innerWidth - 16) {
      left = Math.max(8, hoverPanel.rect.left - PANEL_WIDTH - 12)
    }
    const top = Math.max(8, Math.min(hoverPanel.rect.top, window.innerHeight - PANEL_MAX_HEIGHT - 16))
    hoverPos = { left, top }
  }

  if (notFound) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-stage-950">
        <span className="text-4xl">🎭</span>
        <p className="font-serif text-xl text-stone-300">这个舞台不存在</p>
        <Link to="/" className="text-sm text-gold hover:underline">
          ← 返回画廊
        </Link>
      </div>
    )
  }

  const showPrologue = !prologueDone && !loading && scene !== null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-stage-950">
      {/* 落幕横幅（§8.4）：活动流只读 */}
      {ended && (
        <div className="shrink-0 border-b border-gold/20 bg-gold/10 px-4 py-2 text-center text-xs text-gold">
          🎬 本场演出已落幕 · 活动流为只读回放
        </div>
      )}

      {/* 中栏活动流 */}
      <div className="relative min-h-0 flex-1">
        {loading || !scene ? (
          <FeedSkeleton />
        ) : (
          <motion.div
            className="h-full"
            initial={{ opacity: 0 }}
            animate={{ opacity: prologueDone ? 1 : 0 }}
            transition={{ duration: 0.6 }}
          >
            {view === 'feed' ? (
              <ActivityFeed
                messages={messages}
                characters={characters}
                seekTarget={seekTarget}
                onCharacterEnter={handleCharacterEnter}
                onCharacterLeave={scheduleHoverClose}
              />
            ) : (
              <PixelStage
                key={sceneId}
                messages={messages}
                characters={characters}
                ended={ended}
                seekTarget={seekTarget}
                onCharacterEnter={handleCharacterEnter}
                onCharacterLeave={scheduleHoverClose}
              />
            )}
          </motion.div>
        )}

        {/* 历史标签 */}
        <AnimatePresence>
          {historyTag && (
            <motion.div
              className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-full border border-stage-600 bg-stage-900/95 px-4 py-1.5 text-xs text-stone-400 shadow-lg backdrop-blur"
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
            >
              此前已有 {messages.length} 轮互动
            </motion.div>
          )}
        </AnimatePresence>

        {/* 视图切换：活动流 / 像素舞台 */}
        {prologueDone && (
          <div className="absolute left-4 top-3 z-20 flex overflow-hidden rounded-full border border-stage-600 bg-stage-900/95 text-xs shadow-lg backdrop-blur">
            <button
              type="button"
              onClick={() => setView('feed')}
              className={cn('px-3 py-1.5 transition-colors', view === 'feed' ? 'bg-gold/20 text-gold' : 'text-stone-400 hover:text-stone-200')}
            >
              📜 活动流
            </button>
            <button
              type="button"
              onClick={() => setView('stage')}
              className={cn('px-3 py-1.5 transition-colors', view === 'stage' ? 'bg-gold/20 text-gold' : 'text-stone-400 hover:text-stone-200')}
            >
              🎪 像素舞台
            </button>
          </div>
        )}

        {/* 悬停仪表盘 */}
        <AnimatePresence>
          {hoverPanel && hoverCharacter && hoverPos && (
            <motion.div
              key={hoverCharacter.id}
              className="fixed z-40"
              style={{ left: hoverPos.left, top: hoverPos.top }}
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.97 }}
              transition={{ duration: 0.18 }}
            >
              <DashboardPanel
                character={hoverCharacter}
                pinned={false}
                onPin={() => pinCharacter(hoverCharacter.id)}
                onUnpin={() => undefined}
                onFocus={focusCharacter}
                onMouseEnter={clearHoverTimers}
                onMouseLeave={scheduleHoverClose}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* pin 住的面板：视口右侧纵向排布 */}
        <div className="fixed right-14 top-20 z-30 flex max-h-[calc(100vh-10rem)] flex-col gap-3 overflow-y-auto">
          <AnimatePresence>
            {pinnedIds.map((id) => {
              const c = characters.find((ch) => ch.id === id)
              if (!c) return null
              return (
                <motion.div
                  key={id}
                  initial={{ opacity: 0, x: 24 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 24 }}
                  transition={{ duration: 0.2 }}
                >
                  <DashboardPanel
                    character={c}
                    pinned
                    onPin={() => undefined}
                    onUnpin={() => unpinCharacter(id)}
                    onFocus={focusCharacter}
                  />
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>

        {/* 演员表（右缘手柄 + 滑出面板） */}
        {!loading && scene && <CastPanel characters={characters} messages={messages} onSelect={pinCharacter} />}
      </div>

      {/* 底部时间轴 */}
      {!loading && scene && (
        <Timeline
          messages={messages}
          characters={characters}
          running={scene.status === 'running' && !ended}
          liveMilestones={liveMilestones}
          onSeek={seek}
          onSeekLatest={seekLatest}
        />
      )}

      {/* 场景序幕：数据就绪后淡出 */}
      <AnimatePresence>{showPrologue && scene && <Prologue scene={scene} messages={messages} />}</AnimatePresence>

      {/* 补课摘要弹窗 */}
      <AnimatePresence>
        {summaryOpen && summary && (
          <SummaryModal
            summary={summary}
            onEnterLive={() => {
              setSummaryOpen(false)
              seekLatest()
            }}
            onViewFull={() => {
              setSummaryOpen(false)
              seekFirst()
            }}
            onClose={() => setSummaryOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
