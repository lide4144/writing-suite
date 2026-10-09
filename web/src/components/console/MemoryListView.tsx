import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { deleteMemories, getMemories, mergeMemories, updateMemory } from '../../mock/api'
import type { CharacterInfo, MemoryItem } from '../../types'
import { cn } from '../../utils/cn'
import { formatRelative } from '../../utils/time'

// 记忆整理 · 列表视图（§7.4 次级交互）：结构化卡片列表。
// 行内：编辑、删除、⭐重要性（点击调整）、isActive 状态；
// 批量：checkbox 多选后批量删除；合并：HTML5 拖拽一行到另一行上（source 并入 target）。

interface MemoryListViewProps {
  character: CharacterInfo
}

export function MemoryListView({ character }: MemoryListViewProps) {
  const [items, setItems] = useState<MemoryItem[] | null>(null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [dragOverId, setDragOverId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(() => getMemories(character.id).then(setItems), [character.id])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 操作提示条：几秒后自动消失
  useEffect(() => {
    if (notice === null) return
    const t = setTimeout(() => setNotice(null), 3000)
    return () => clearTimeout(t)
  }, [notice])

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleImportance = async (id: string, importance: number) => {
    setItems((prev) => prev?.map((m) => (m.id === id ? { ...m, importance } : m)) ?? null)
    await updateMemory(id, { importance })
  }

  const handleSaveEdit = async (id: string) => {
    const content = editDraft.trim()
    setEditingId(null)
    if (!content) return
    await updateMemory(id, { content })
    await refresh()
    setNotice(`已更新 ${id}`)
  }

  const handleDelete = async (ids: string[]) => {
    await deleteMemories(ids)
    setSelected((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => next.delete(id))
      return next
    })
    await refresh()
    setNotice(`已删除 ${ids.length} 条记忆`)
  }

  // 归档 = 标记为失效（isActive: false），保留记录但不参与回忆
  const handleArchive = async (ids: string[]) => {
    await Promise.all(ids.map((id) => updateMemory(id, { isActive: false })))
    setSelected((prev) => {
      const next = new Set(prev)
      ids.forEach((id) => next.delete(id))
      return next
    })
    await refresh()
    setNotice(`已归档 ${ids.length} 条记忆`)
  }

  const handleMerge = async (sourceId: string, targetId: string) => {
    if (sourceId === targetId) return
    await mergeMemories(sourceId, targetId)
    await refresh()
    setNotice(`已将 ${sourceId} 并入 ${targetId}`)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {items === null ? (
          <p className="text-sm text-stone-500">读取记忆库…</p>
        ) : items.length === 0 ? (
          <p className="py-10 text-center text-sm text-stone-500">记忆库是空的。</p>
        ) : (
          <ul className="space-y-2.5">
            {items.map((m) => (
              <li
                key={m.id}
                draggable={editingId !== m.id}
                onDragStart={(e) => {
                  e.dataTransfer.setData('text/plain', m.id)
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragOver={(e) => {
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  if (dragOverId !== m.id) setDragOverId(m.id)
                }}
                onDragLeave={() => setDragOverId((cur) => (cur === m.id ? null : cur))}
                onDrop={(e) => {
                  e.preventDefault()
                  const sourceId = e.dataTransfer.getData('text/plain')
                  setDragOverId(null)
                  if (sourceId) void handleMerge(sourceId, m.id)
                }}
                className={cn(
                  'rounded-lg border bg-stage-900 p-4 transition-colors',
                  dragOverId === m.id ? 'border-gold ring-1 ring-gold/50' : 'border-stage-700',
                  !m.isActive && 'opacity-60',
                )}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(m.id)}
                    onChange={() => toggleSelect(m.id)}
                    className="mt-1 accent-gold"
                    aria-label={`选择 ${m.id}`}
                  />

                  <div className="min-w-0 flex-1">
                    {editingId === m.id ? (
                      <div className="flex gap-2">
                        <textarea
                          value={editDraft}
                          onChange={(e) => setEditDraft(e.target.value)}
                          rows={2}
                          autoFocus
                          className="flex-1 resize-none rounded border border-gold/50 bg-stage-950 px-2.5 py-1.5 text-sm text-stone-200 outline-none"
                        />
                        <div className="flex flex-col gap-1.5">
                          <button
                            onClick={() => void handleSaveEdit(m.id)}
                            className="rounded bg-gold px-2.5 py-1 text-xs font-medium text-stage-950"
                          >
                            保存
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="rounded border border-stage-600 px-2.5 py-1 text-xs text-stone-400"
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="font-serif text-sm leading-relaxed text-stone-200">{m.content}</p>
                    )}

                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {m.tags.map((tag) => (
                        <span key={tag} className="rounded-full bg-stage-800 px-2 py-0.5 text-[11px] text-stone-400">
                          {tag}
                        </span>
                      ))}
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-[11px]',
                          m.isActive ? 'bg-emerald-900/40 text-emerald-300' : 'bg-stage-800 text-stone-500',
                        )}
                      >
                        {m.isActive ? '有效' : '已失效'}
                      </span>
                    </div>

                    <div className="mt-1.5 font-mono text-[11px] text-stone-500">
                      {m.id} · 更新于 {formatRelative(m.updatedAt)}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <div className="flex gap-0.5" title="重要性（点击调整）">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          onClick={() => void handleImportance(m.id, n)}
                          className={cn(
                            'text-sm leading-none transition-colors',
                            n <= m.importance ? 'text-gold' : 'text-stage-600 hover:text-gold/60',
                          )}
                        >
                          ★
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2.5 text-xs">
                      <button
                        onClick={() => {
                          setEditingId(m.id)
                          setEditDraft(m.content)
                        }}
                        className="text-stone-500 hover:text-gold"
                      >
                        编辑
                      </button>
                      <button onClick={() => void handleDelete([m.id])} className="text-stone-500 hover:text-red-400">
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* 批量操作条（吸底） */}
        {selected.size > 0 && (
          <div className="sticky bottom-2 mt-4 flex items-center justify-between rounded-lg border border-stage-600 bg-stage-800 px-4 py-2.5 shadow-lg">
            <span className="text-xs text-stone-300">已选 {selected.size} 条</span>
            <div className="flex gap-2">
              <button
                onClick={() => setSelected(new Set())}
                className="rounded border border-stage-600 px-3 py-1 text-xs text-stone-400 hover:text-stone-200"
              >
                清除选择
              </button>
              <button
                onClick={() => void handleArchive([...selected])}
                className="rounded border border-stage-500 px-3 py-1 text-xs text-stone-300 hover:border-gold hover:text-gold"
              >
                📦 批量归档
              </button>
              <button
                onClick={() => void handleDelete([...selected])}
                className="rounded bg-red-900/60 px-3 py-1 text-xs text-red-200 hover:bg-red-900"
              >
                🗑 批量删除
              </button>
            </div>
          </div>
        )}

        <p className="mt-4 text-center text-[11px] text-stone-600">提示：拖动一条记忆到另一条上，可以把它们合并。</p>
      </div>

      {/* 操作提示条 */}
      <AnimatePresence>
        {notice && (
          <motion.div
            initial={{ opacity: 0, y: 12, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 12, x: '-50%' }}
            className="absolute bottom-4 left-1/2 z-10 rounded-full border border-gold/40 bg-stage-800 px-4 py-2 font-mono text-xs text-gold shadow-lg"
          >
            {notice}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
