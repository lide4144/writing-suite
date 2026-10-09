import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getChatHistory } from '../../mock/api'
import type { CharacterInfo, ChatMessage } from '../../types'
import { cn } from '../../utils/cn'
import { formatRelative } from '../../utils/time'
import { Avatar } from '../common/Avatar'

// 角色列表（§7.4 左侧栏，固定 280px）：按最近聊天时间倒序，当前选中高亮。
// 点击切换角色时保留当前 Tab 后缀（/diary、/audit）。

interface Entry {
  character: CharacterInfo
  last: ChatMessage | null
}

interface CharacterListProps {
  characters: CharacterInfo[]
  activeId: string
}

export function CharacterList({ characters, activeId }: CharacterListProps) {
  const location = useLocation()
  const [entries, setEntries] = useState<Entry[] | null>(null)

  // 拉取每个角色的最近一条聊天做预览；路径变化（切角色/切 Tab）时静默刷新
  useEffect(() => {
    let cancelled = false
    Promise.all(
      characters.map(async (character): Promise<Entry> => {
        const history = await getChatHistory(character.id)
        return { character, last: history.length > 0 ? history[history.length - 1] : null }
      }),
    ).then((list) => {
      if (cancelled) return
      list.sort(
        (a, b) => (b.last ? +new Date(b.last.timestamp) : 0) - (a.last ? +new Date(a.last.timestamp) : 0),
      )
      setEntries(list)
    })
    return () => {
      cancelled = true
    }
  }, [characters, location.pathname])

  const suffix = location.pathname.endsWith('/diary') ? '/diary' : location.pathname.endsWith('/audit') ? '/audit' : ''

  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r border-stage-700 bg-stage-900">
      <div className="border-b border-stage-700 px-4 py-3">
        <Link to="/" className="text-xs text-stone-500 hover:text-gold">
          ← 返回画廊
        </Link>
        <h2 className="mt-1 font-serif text-lg text-stone-100">休息室</h2>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {entries === null ? (
          <p className="px-4 py-6 text-sm text-stone-500">加载角色中…</p>
        ) : (
          entries.map(({ character, last }) => {
            const active = character.id === activeId
            return (
              <Link
                key={character.id}
                to={`/chat/${character.id}${suffix}`}
                className={cn(
                  'flex items-center gap-3 border-l-2 px-4 py-3 transition-colors',
                  active ? 'border-gold bg-stage-800' : 'border-transparent hover:bg-stage-800/60',
                )}
              >
                <Avatar name={character.name} color={character.color} size={36} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className={cn('truncate text-sm', active ? 'text-stone-100' : 'text-stone-300')}>
                      {character.name}
                    </span>
                    {last && (
                      <span className="shrink-0 text-[11px] text-stone-500">{formatRelative(last.timestamp)}</span>
                    )}
                  </span>
                  <span className="mt-0.5 block truncate text-xs text-stone-500">
                    {last ? `${last.role === 'user' ? '你：' : ''}${last.content}` : '还没有说过话'}
                  </span>
                </span>
              </Link>
            )
          })
        )}
      </nav>
    </aside>
  )
}
