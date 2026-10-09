import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Scene, SceneStatus } from '../../types'
import { archiveScene, deleteScene } from '../../mock/api'
import { cn } from '../../utils/cn'
import { formatDuration, formatRelative } from '../../utils/time'
import { Avatar } from '../common/Avatar'

const STATUS_META: Record<SceneStatus, { label: string; badgeClass: string }> = {
  running: { label: '运行中', badgeClass: 'border-gold/40 bg-gold/10 text-gold' },
  ended: { label: '已落幕', badgeClass: 'border-stage-600 bg-stage-800 text-stone-400' },
  draft: { label: '草稿', badgeClass: 'border-stage-600 bg-stage-800 text-stone-500' },
}

const MAX_AVATARS = 4
const MENU_WIDTH = 176
const MENU_HEIGHT = 132

interface MenuPos {
  x: number
  y: number
}

// 场景卡片（§4.3）：点击进入观众席；右键呼出快捷菜单（舞台监督 / 归档 / 删除）。
export function SceneCard({ scene, onChanged }: { scene: Scene; onChanged?: () => void }) {
  const navigate = useNavigate()
  const [menu, setMenu] = useState<MenuPos | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)

  // 点击菜单外部 / 按 Esc / 窗口失焦时关闭快捷菜单
  useEffect(() => {
    if (!menu) return
    const onMouseDown = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenu(null)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null)
    }
    const close = () => setMenu(null)
    window.addEventListener('mousedown', onMouseDown)
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('blur', close)
    return () => {
      window.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('blur', close)
    }
  }, [menu])

  const status = STATUS_META[scene.status]
  const isRunning = scene.status === 'running'
  const isDraft = scene.status === 'draft'
  const shownCharacters = scene.characters.slice(0, MAX_AVATARS)
  const extraCount = scene.characters.length - shownCharacters.length

  const openMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    setMenu({
      x: Math.max(8, Math.min(e.clientX, window.innerWidth - MENU_WIDTH - 8)),
      y: Math.max(8, Math.min(e.clientY, window.innerHeight - MENU_HEIGHT - 8)),
    })
  }

  const handleArchive = async () => {
    setMenu(null)
    await archiveScene(scene.id)
    onChanged?.()
  }

  const handleDelete = async () => {
    setMenu(null)
    if (!window.confirm(`确定删除场景「${scene.title}」？此操作不可恢复。`)) return
    await deleteScene(scene.id)
    onChanged?.()
  }

  return (
    <article
      onClick={() => navigate(`/stage/${scene.id}/watch`)}
      onContextMenu={openMenu}
      className={cn(
        'group relative flex cursor-pointer flex-col rounded-xl border bg-stage-900 p-5 transition-colors',
        isRunning && 'animate-breathe border-gold/40',
        scene.status === 'ended' && 'border-stage-700 hover:border-stage-600',
        isDraft && 'border-dashed border-stage-600 opacity-75 hover:opacity-90',
        !isDraft && 'hover:bg-stage-800/70',
      )}
    >
      {/* 状态徽章 + 未读徽章 */}
      <div className="flex items-center gap-2">
        <span className={cn('flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs', status.badgeClass)}>
          {isRunning && <span className="h-1.5 w-1.5 rounded-full bg-gold" />}
          {status.label}
        </span>
        {scene.hasUnreadEvents && (
          <span className="rounded-full border border-rose-500/40 bg-rose-500/10 px-2.5 py-0.5 text-xs text-rose-300">
            未读事件
          </span>
        )}
      </div>

      <h2 className="mt-3 text-lg font-semibold text-stone-100 transition-colors group-hover:text-gold">
        {scene.title}
      </h2>
      <p className="mt-2 line-clamp-2 min-h-10 font-serif text-sm leading-relaxed text-stone-400">
        {scene.description || '（暂无描述）'}
      </p>

      {/* 参与角色：头像叠放，最多 4 个，超出 +N */}
      <div className="mt-4 flex items-center gap-3">
        <div className="flex -space-x-2">
          {shownCharacters.map((c) => (
            <Avatar key={c.id} name={c.name} color={c.color} size={28} className="ring-2 ring-stage-900" />
          ))}
          {extraCount > 0 && (
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-stage-700 font-mono text-[10px] text-stone-300 ring-2 ring-stage-900">
              +{extraCount}
            </span>
          )}
        </div>
        <span className="truncate text-xs text-stone-500">{scene.characters.map((c) => c.name).join('、')}</span>
      </div>

      {/* 交互轮次 / 持续时间 / 最后活动 */}
      <div className="mt-4 flex items-center gap-4 border-t border-stage-800 pt-3 text-xs text-stone-500">
        <span>
          交互 <span className="font-mono text-stone-300">{scene.totalMessages}</span> 轮
        </span>
        <span>
          持续 <span className="font-mono text-stone-300">{formatDuration(scene.startedAt, scene.endedAt)}</span>
        </span>
        <span className="ml-auto font-mono">{formatRelative(scene.lastActivityAt)}</span>
      </div>

      {/* 右键快捷菜单 */}
      {menu && (
        <div
          ref={menuRef}
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          className="fixed z-50 w-44 overflow-hidden rounded-lg border border-stage-600 bg-stage-800 py-1 shadow-2xl shadow-black/60"
        >
          <button
            type="button"
            onClick={() => {
              setMenu(null)
              navigate(`/stage/${scene.id}/setup`)
            }}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-stone-200 transition-colors hover:bg-stage-700"
          >
            🎬 进入舞台监督
          </button>
          <button
            type="button"
            onClick={() => void handleArchive()}
            title="从画廊隐藏此场景"
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-stone-200 transition-colors hover:bg-stage-700"
          >
            📦 归档
          </button>
          <button
            type="button"
            onClick={() => void handleDelete()}
            className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-red-300 transition-colors hover:bg-stage-700"
          >
            🗑 删除
          </button>
        </div>
      )}
    </article>
  )
}
