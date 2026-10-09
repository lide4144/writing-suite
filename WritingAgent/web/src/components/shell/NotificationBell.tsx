import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import type { NotificationEvent } from '../../types'
import { useAppStore } from '../../store/useAppStore'
import { cn } from '../../utils/cn'
import { formatRelative } from '../../utils/time'

const TYPE_META: Record<NotificationEvent['type'], { icon: string; label: string }> = {
  scene_ended: { icon: '🎬', label: '场景落幕' },
  milestone: { icon: '⭐', label: '重大事件' },
}

// 通知铃铛（§3.2）：未读角标 + 下拉时间线；展开时全部标记已读，点击条目跳转对应场景观众席。
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const navigate = useNavigate()

  const notifications = useAppStore((s) => s.notifications)
  const unreadCount = useAppStore((s) => s.unreadCount)
  const markAllRead = useAppStore((s) => s.markAllRead)

  // 有未读的「场景结束」通知时铃铛闪烁（§3.2）
  const hasUnreadEnded = notifications.some((n) => !n.isRead && n.type === 'scene_ended')

  // 桌面通知（§3.2）：新通知到达且浏览器已授权时，推送桌面 Notification
  const seenLatestRef = useRef<string | null>(null)
  useEffect(() => {
    const latest = notifications[0] // addNotification 是前插，首条即最新
    if (!latest) return
    if (seenLatestRef.current === null) {
      seenLatestRef.current = latest.id
      return
    }
    if (latest.id === seenLatestRef.current) return
    seenLatestRef.current = latest.id
    if (!('Notification' in window) || Notification.permission !== 'granted') return
    const meta = TYPE_META[latest.type]
    new Notification(`${meta.icon} ${meta.label} · ${latest.sceneTitle}`, { body: latest.message })
  }, [notifications])

  // 点击外部 / 按 Esc 关闭下拉
  useEffect(() => {
    if (!open) return
    const onMouseDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const toggle = () => {
    if (!open) {
      markAllRead() // 展开即视为已读
      // 借用户点击的手势申请桌面通知权限（§3.2「如果浏览器允许」）
      if ('Notification' in window && Notification.permission === 'default') {
        void Notification.requestPermission()
      }
    }
    setOpen(!open)
  }

  const sorted = [...notifications].sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={toggle}
        aria-label="通知"
        className={cn(
          'relative rounded-full p-2 text-stone-300 transition-colors hover:bg-stage-800 hover:text-gold',
          hasUnreadEnded && 'animate-pulse',
        )}
      >
        <span className="text-base leading-none">🔔</span>
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 font-mono text-[10px] font-semibold text-white">
            {unreadCount}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full z-50 mt-2 w-96 overflow-hidden rounded-xl border border-stage-700 bg-stage-900 shadow-2xl shadow-black/50"
          >
            <div className="border-b border-stage-700 px-4 py-2.5 text-xs font-medium tracking-wider text-stone-400">
              通知 · 近期事件
            </div>
            {sorted.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-stone-500">暂无通知</div>
            ) : (
              <ul className="max-h-80 overflow-y-auto">
                {sorted.map((n) => {
                  const meta = TYPE_META[n.type]
                  return (
                    <li key={n.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setOpen(false)
                          navigate(`/stage/${n.sceneId}/watch`)
                        }}
                        className={cn(
                          'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-stage-800',
                          !n.isRead && 'bg-stage-800/60',
                        )}
                      >
                        <span className="mt-0.5 text-base leading-none" title={meta.label}>
                          {meta.icon}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-stone-200">{n.message}</span>
                          <span className="mt-1 block text-xs text-stone-500">
                            {n.sceneTitle} · <span className="font-mono">{formatRelative(n.timestamp)}</span>
                          </span>
                        </span>
                        {!n.isRead && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-gold" />}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
