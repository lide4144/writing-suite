// 底部时间轴（§5.4.4）：每角色 + GM 各一条彩色横轨，消息为轨上标记点。
// 初始折叠成一条细线（活动概览），点击展开；展开后可缩放时间跨度（5/15/30 分钟/全部）。
// 悬停标记点显示摘要 tooltip，点击标记点活动流滚动到对应消息并高亮。
// 里程碑（importance >= 8 或 WS milestone）以金色特殊标记。
// 主拖拽条：按住轨道空白处拖动，松开后跳转到该时刻最近的消息；
// 回放控制：▶ 从当前位置逐条推进（活动流跟随高亮），■ 停止。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CharacterInfo, Message } from '../../types'
import { GM_COLOR } from '../../mock/data'
import { formatClock } from '../../utils/time'
import { cn } from '../../utils/cn'
import type { LiveMilestone } from './useSceneWatch'

/** 缩放档位：分钟数，0 表示全部 */
type Zoom = 5 | 15 | 30 | 0

const ZOOMS: { value: Zoom; label: string }[] = [
  { value: 5, label: '5 分钟' },
  { value: 15, label: '15 分钟' },
  { value: 30, label: '30 分钟' },
  { value: 0, label: '全部' },
]

const MILESTONE_IMPORTANCE = 8
const EDGE_PAD_MS = 30_000
const PLAY_INTERVAL_MS = 1400
// 轨道区相对容器左缘的偏移：px-4(16) + 轨名 w-10(40) + gap-2(8)
const TRACK_LEFT_PX = 64
const TRACK_RIGHT_PX = 16

interface TimelineProps {
  messages: Message[]
  characters: CharacterInfo[]
  running: boolean
  liveMilestones: LiveMilestone[]
  onSeek: (messageId: string) => void
  onSeekLatest: () => void
}

const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n)}…` : s)

export function Timeline({ messages, characters, running, liveMilestones, onSeek, onSeekLatest }: TimelineProps) {
  const [expanded, setExpanded] = useState(false)
  const [zoom, setZoom] = useState<Zoom>(5)

  // 拖拽跳转：按住轨道空白处拖动时的时间（ms 时间戳）
  const [scrubTs, setScrubTs] = useState<number | null>(null)
  // 回放：当前推进到的时间 + 播放中标记 + 会话计数（拖拽后重开播放）
  const [playTs, setPlayTs] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [playSession, setPlaySession] = useState(0)
  const tracksRef = useRef<HTMLDivElement | null>(null)

  const ordered = useMemo(
    () => [...messages].sort((a, b) => +new Date(a.timestamp) - +new Date(b.timestamp)),
    [messages],
  )

  // 可见时间窗：running 场景右缘跟随当前时间，否则对齐最后一条消息
  const visibleRange = useMemo(() => {
    const times = messages.map((m) => +new Date(m.timestamp))
    const now = Date.now()
    const tFirst = times.length ? Math.min(...times) : now
    const tLast = times.length ? Math.max(...times) : now
    if (zoom === 0) {
      const start = tFirst - EDGE_PAD_MS
      return { start, end: Math.max(tLast + EDGE_PAD_MS, start + 60_000) }
    }
    const end = running ? Math.max(now, tLast) : tLast
    return { start: end - zoom * 60_000, end }
  }, [messages, zoom, running])

  // 折叠态的迷你轨始终用全程跨度
  const fullRange = useMemo(() => {
    const times = messages.map((m) => +new Date(m.timestamp))
    const now = Date.now()
    const tFirst = times.length ? Math.min(...times) : now
    const tLast = times.length ? Math.max(...times) : now
    return { start: tFirst - EDGE_PAD_MS, end: Math.max(tLast + EDGE_PAD_MS, tFirst + 60_000) }
  }, [messages])

  const posIn = (range: { start: number; end: number }, ts: string): number | null => {
    const p = ((+new Date(ts) - range.start) / (range.end - range.start)) * 100
    return p < 0 || p > 100 ? null : p
  }

  const posOfTs = (ts: number): number | null => {
    const p = ((ts - visibleRange.start) / (visibleRange.end - visibleRange.start)) * 100
    return p < 0 || p > 100 ? null : p
  }

  const colorOf = (m: Message): string =>
    (m.characterId && characters.find((c) => c.id === m.characterId)?.color) || GM_COLOR

  // 指针 x 坐标 → 可见时间窗内的时间戳
  const tsAtClientX = useCallback(
    (clientX: number): number | null => {
      const el = tracksRef.current
      if (!el) return null
      const rect = el.getBoundingClientRect()
      const trackWidth = rect.width - TRACK_LEFT_PX - TRACK_RIGHT_PX
      if (trackWidth <= 0) return null
      const x = Math.min(Math.max(clientX - rect.left - TRACK_LEFT_PX, 0), trackWidth)
      return visibleRange.start + (x / trackWidth) * (visibleRange.end - visibleRange.start)
    },
    [visibleRange],
  )

  const nearestMessage = useCallback(
    (ts: number): Message | null => {
      let best: Message | null = null
      let bestDist = Infinity
      for (const m of ordered) {
        const d = Math.abs(+new Date(m.timestamp) - ts)
        if (d < bestDist) {
          bestDist = d
          best = m
        }
      }
      return best
    },
    [ordered],
  )

  // —— 主拖拽条 ——
  const handleScrubStart = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button')) return // 标记点交给自身的点击
    const ts = tsAtClientX(e.clientX)
    if (ts === null) return
    e.currentTarget.setPointerCapture(e.pointerId)
    setScrubTs(ts)
  }
  const handleScrubMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (scrubTs === null) return
    const ts = tsAtClientX(e.clientX)
    if (ts !== null) setScrubTs(ts)
  }
  const handleScrubEnd = () => {
    if (scrubTs === null) return
    const nearest = nearestMessage(scrubTs)
    if (nearest) onSeek(nearest.id)
    setPlayTs(scrubTs)
    if (playing) setPlaySession((s) => s + 1) // 播放中拖拽：从新位置继续
    setScrubTs(null)
  }

  // —— 回放：从 playTs（或开头）逐条推进 ——
  useEffect(() => {
    if (!playing) return
    const from = playTs
    let idx = from === null ? 0 : ordered.findIndex((m) => +new Date(m.timestamp) > from)
    if (idx === -1) idx = ordered.length
    if (idx >= ordered.length) {
      setPlaying(false)
      return
    }
    const step = () => {
      const m = ordered[idx]
      if (!m) {
        setPlaying(false)
        return
      }
      onSeek(m.id)
      setPlayTs(+new Date(m.timestamp))
      idx += 1
      if (idx >= ordered.length) setPlaying(false)
    }
    step()
    const timer = window.setInterval(step, PLAY_INTERVAL_MS)
    return () => window.clearInterval(timer)
    // 仅在播放开关 / 播放会话变化时重建；ordered 的新消息追加不打断当前回放
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, playSession])

  const togglePlay = () => {
    if (playing) {
      setPlaying(false)
      setPlayTs(null)
    } else {
      setPlayTs(null)
      setPlaying(true)
      setPlaySession((s) => s + 1)
    }
  }

  const handleSeekLatest = () => {
    setPlaying(false)
    setPlayTs(null)
    onSeekLatest()
  }

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        title="展开时间轴"
        className="group flex h-7 w-full shrink-0 items-center gap-3 border-t border-stage-700 bg-stage-900/95 px-4"
      >
        <span className="text-xs text-stone-500 transition-colors group-hover:text-stone-300">⠿ 活动概览</span>
        <span className="relative h-3 flex-1">
          <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-stage-600" />
          {messages.map((m) => {
            const p = posIn(fullRange, m.timestamp)
            if (p === null) return null
            return (
              <span
                key={m.id}
                className="absolute top-1/2 h-1 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full"
                style={{ left: `${p}%`, backgroundColor: colorOf(m) }}
              />
            )
          })}
        </span>
        <span className="text-xs text-stone-600 transition-colors group-hover:text-stone-400">▲</span>
      </button>
    )
  }

  const tracks = [
    { key: 'gm', name: 'GM', color: GM_COLOR, list: messages.filter((m) => m.characterId === null) },
    ...characters.map((c) => ({
      key: c.id,
      name: c.name,
      color: c.color,
      list: messages.filter((m) => m.characterId === c.id),
    })),
  ]

  // 游标线（拖拽中亮金色，回放中暗金色）
  const cursorTs = scrubTs ?? (playing ? playTs : null)
  const cursorPos = cursorTs !== null ? posOfTs(cursorTs) : null

  return (
    <div className="shrink-0 border-t border-stage-700 bg-stage-900/95">
      <div className="flex items-center gap-2 px-4 pt-2">
        <span className="text-xs text-stone-500">活动概览</span>
        <button
          type="button"
          onClick={togglePlay}
          disabled={ordered.length === 0}
          title={playing ? '停止回放' : '从头回放'}
          className={cn(
            'rounded px-2 py-0.5 text-xs transition-colors',
            playing
              ? 'bg-gold/20 text-gold hover:bg-gold/30'
              : 'bg-stage-800 text-stone-300 hover:bg-stage-700 hover:text-gold',
            ordered.length === 0 && 'cursor-not-allowed opacity-40',
          )}
        >
          {playing ? '■ 停止' : '▶ 回放'}
        </button>
        <button
          type="button"
          onClick={handleSeekLatest}
          className="rounded bg-stage-800 px-2 py-0.5 text-xs text-stone-300 transition-colors hover:bg-stage-700 hover:text-gold"
        >
          ⏭ 回到最新
        </button>
        <span className="ml-auto flex items-center gap-1">
          {ZOOMS.map((z) => (
            <button
              key={z.value}
              type="button"
              onClick={() => setZoom(z.value)}
              className={cn(
                'rounded px-2 py-0.5 text-xs transition-colors',
                zoom === z.value ? 'bg-gold/20 text-gold' : 'text-stone-500 hover:text-stone-300',
              )}
            >
              {z.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setExpanded(false)}
            title="收起时间轴"
            className="ml-2 rounded px-2 py-0.5 text-xs text-stone-500 transition-colors hover:text-stone-300"
          >
            ▼ 收起
          </button>
        </span>
      </div>

      {/* 轨道区：整体可拖拽跳转（空白处按住拖动） */}
      <div
        ref={tracksRef}
        onPointerDown={handleScrubStart}
        onPointerMove={handleScrubMove}
        onPointerUp={handleScrubEnd}
        onPointerCancel={handleScrubEnd}
        title="按住空白处拖动，跳转到任意时刻"
        className={cn('relative space-y-1 px-4 py-2', scrubTs !== null && 'cursor-col-resize select-none')}
      >
        {tracks.map((track) => (
          <div key={track.key} className="flex items-center gap-2">
            <span className="w-10 shrink-0 truncate text-right text-xs" style={{ color: track.color }}>
              {track.name}
            </span>
            <div className="relative h-4 flex-1">
              <span className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 rounded bg-stage-700" />
              {track.list.map((m) => {
                const p = posIn(visibleRange, m.timestamp)
                if (p === null) return null
                const milestone = m.importance >= MILESTONE_IMPORTANCE
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => onSeek(m.id)}
                    className={cn(
                      'group absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full transition-transform hover:scale-125',
                      milestone ? 'h-2.5 w-2.5 ring-2 ring-gold' : 'h-1.5 w-1.5',
                    )}
                    style={{ left: `${p}%`, backgroundColor: track.color }}
                  >
                    <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1.5 hidden -translate-x-1/2 whitespace-nowrap rounded border border-stage-600 bg-stage-950 px-2 py-1 text-xs text-stone-300 group-hover:block">
                      {formatClock(m.timestamp)} · {m.characterName}：{cut(m.content, 20)}
                    </span>
                  </button>
                )
              })}
              {track.key === 'gm' &&
                liveMilestones.map((ms) => {
                  const p = posIn(visibleRange, ms.timestamp)
                  if (p === null) return null
                  return (
                    <span
                      key={ms.id}
                      className="group absolute top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] leading-none text-gold"
                      style={{ left: `${p}%` }}
                    >
                      ★
                      <span className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1.5 hidden -translate-x-1/2 whitespace-nowrap rounded border border-gold/40 bg-stage-950 px-2 py-1 text-xs text-gold group-hover:block">
                        里程碑 · {ms.chapter}：{ms.summary}
                      </span>
                    </span>
                  )
                })}
            </div>
          </div>
        ))}

        {/* 拖拽 / 回放游标线（横跨全部轨道） */}
        {cursorPos !== null && cursorTs !== null && (
          <div
            className="pointer-events-none absolute inset-y-1 z-10"
            style={{ left: `calc(${TRACK_LEFT_PX}px + (100% - ${TRACK_LEFT_PX + TRACK_RIGHT_PX}px) * ${cursorPos / 100})` }}
          >
            <div className={cn('h-full w-px', scrubTs !== null ? 'bg-gold' : 'bg-gold/50')} />
            {scrubTs !== null && (
              <div className="absolute -top-1 left-1/2 -translate-x-1/2 whitespace-nowrap rounded border border-gold/40 bg-stage-950 px-1.5 py-0.5 font-mono text-[10px] text-gold">
                {formatClock(new Date(cursorTs).toISOString())}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
