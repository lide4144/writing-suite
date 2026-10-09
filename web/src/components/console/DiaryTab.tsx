import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { getDiaries, updateDiary } from '../../mock/api'
import type { CharacterInfo, DiaryEntry } from '../../types'
import { cn } from '../../utils/cn'
import { formatDate } from '../../utils/time'

// 日记 Tab（§7.4）：按时间倒序的日记卡片（API 已排好序）。
// 日记由系统生成、用户不可编辑，但可「标记为重要」和「添加注释」。

interface DiaryTabProps {
  character: CharacterInfo
}

export function DiaryTab({ character }: DiaryTabProps) {
  const [diaries, setDiaries] = useState<DiaryEntry[] | null>(null)

  useEffect(() => {
    let cancelled = false
    getDiaries(character.id).then((list) => {
      if (!cancelled) setDiaries(list)
    })
    return () => {
      cancelled = true
    }
  }, [character.id])

  const patchLocal = (id: string, patch: Partial<Pick<DiaryEntry, 'isImportant' | 'note'>>) => {
    setDiaries((prev) => prev?.map((d) => (d.id === id ? { ...d, ...patch } : d)) ?? null)
  }

  const toggleImportant = async (entry: DiaryEntry) => {
    const next = !entry.isImportant
    patchLocal(entry.id, { isImportant: next })
    await updateDiary(entry.id, { isImportant: next })
  }

  const saveNote = async (entry: DiaryEntry, note: string) => {
    patchLocal(entry.id, { note })
    await updateDiary(entry.id, { note })
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      {diaries === null ? (
        <p className="text-sm text-stone-500">翻开日记本…</p>
      ) : diaries.length === 0 ? (
        <p className="py-10 text-center text-sm text-stone-500">{character.name} 还没有写过日记。</p>
      ) : (
        <div className="mx-auto max-w-2xl space-y-4">
          {diaries.map((entry) => (
            <DiaryCard
              key={entry.id}
              entry={entry}
              onToggleImportant={() => void toggleImportant(entry)}
              onSaveNote={(note) => void saveNote(entry, note)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function DiaryCard({
  entry,
  onToggleImportant,
  onSaveNote,
}: {
  entry: DiaryEntry
  onToggleImportant: () => void
  onSaveNote: (note: string) => void
}) {
  const [editingNote, setEditingNote] = useState(false)
  const [noteDraft, setNoteDraft] = useState(entry.note)
  const sceneNum = entry.sceneId.replace(/^scene-/, '')

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-stage-700 bg-stage-900 p-5"
    >
      <header className="flex items-center justify-between gap-3">
        <time className="text-sm text-stone-400">{formatDate(entry.createdAt)}</time>
        <button
          onClick={onToggleImportant}
          className={cn(
            'rounded-full border px-2.5 py-0.5 text-xs transition-colors',
            entry.isImportant
              ? 'border-gold/60 bg-gold/10 text-gold'
              : 'border-stage-600 text-stone-500 hover:border-gold/50 hover:text-gold',
          )}
        >
          {entry.isImportant ? '★ 已标记重要' : '☆ 标记为重要'}
        </button>
      </header>

      <Link
        to={`/stage/${entry.sceneId}/watch`}
        className="mt-1.5 inline-block text-xs text-gold/80 hover:text-gold hover:underline"
      >
        来自场景 #{sceneNum}：{entry.sceneTitle} →
      </Link>

      <p className="mt-3 whitespace-pre-line font-serif leading-loose text-stone-200">{entry.content}</p>

      <footer className="mt-4 border-t border-stage-800 pt-3">
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-stone-500">{entry.wordCount} 字</span>
          <button
            onClick={() => {
              setNoteDraft(entry.note)
              setEditingNote((v) => !v)
            }}
            className="text-xs text-stone-500 hover:text-gold"
          >
            {editingNote ? '收起' : entry.note ? '编辑注释' : '添加注释'}
          </button>
        </div>

        {entry.note && !editingNote && (
          <p className="mt-2 border-l-2 border-gold/50 pl-3 text-xs leading-relaxed text-stone-400">{entry.note}</p>
        )}

        {editingNote && (
          <div className="mt-2 flex gap-2">
            <input
              value={noteDraft}
              onChange={(e) => setNoteDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                  onSaveNote(noteDraft.trim())
                  setEditingNote(false)
                }
              }}
              placeholder="给这篇日记写一句注释…"
              className="flex-1 rounded border border-stage-600 bg-stage-950 px-2.5 py-1.5 text-xs text-stone-200 outline-none placeholder:text-stone-600 focus:border-gold"
            />
            <button
              onClick={() => {
                onSaveNote(noteDraft.trim())
                setEditingNote(false)
              }}
              className="rounded bg-gold px-3 py-1.5 text-xs font-medium text-stage-950"
            >
              保存
            </button>
          </div>
        )}
      </footer>
    </motion.article>
  )
}
