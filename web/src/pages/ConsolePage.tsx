import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { getCharacter, getCharacters } from '../mock/api'
import type { CharacterInfo } from '../types'
import { cn } from '../utils/cn'
import { Avatar } from '../components/common/Avatar'
import { CharacterList } from '../components/console/CharacterList'
import { ChatTab } from '../components/console/ChatTab'
import { DiaryTab } from '../components/console/DiaryTab'
import { MemoryTab } from '../components/console/MemoryTab'

// 角色控制台（§7 休息室）：左侧角色列表（280px）+ 右侧聊天/日记/记忆整理三个 Tab。
// 三个 Tab 对应三条路由（/chat/:id、/diary、/audit），由 useLocation 判断当前 Tab。

type ConsoleTab = 'chat' | 'diary' | 'audit'

const TABS: Array<{ key: ConsoleTab; label: string; suffix: string }> = [
  { key: 'chat', label: '聊天', suffix: '' },
  { key: 'diary', label: '日记', suffix: '/diary' },
  { key: 'audit', label: '记忆整理', suffix: '/audit' },
]

export function ConsolePage() {
  const { characterId } = useParams<{ characterId: string }>()
  const location = useLocation()
  const tab: ConsoleTab = location.pathname.endsWith('/diary')
    ? 'diary'
    : location.pathname.endsWith('/audit')
      ? 'audit'
      : 'chat'

  const [characters, setCharacters] = useState<CharacterInfo[] | null>(null)
  const [character, setCharacter] = useState<CharacterInfo | null | undefined>(undefined) // undefined = 加载中

  useEffect(() => {
    let cancelled = false
    getCharacters().then((list) => {
      if (!cancelled) setCharacters(list)
    })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!characterId) return
    let cancelled = false
    setCharacter(undefined)
    getCharacter(characterId).then((c) => {
      if (!cancelled) setCharacter(c)
    })
    return () => {
      cancelled = true
    }
  }, [characterId])

  if (characters === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-stage-950 text-sm text-stone-500">
        休息室的灯正在亮起…
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-stage-950">
      <CharacterList characters={characters} activeId={characterId ?? ''} />

      {character === undefined ? (
        <main className="flex min-w-0 flex-1 items-center justify-center text-sm text-stone-500">
          正在敲门…
        </main>
      ) : character === null ? (
        // §8.4：角色不存在
        <main className="flex min-w-0 flex-1 flex-col items-center justify-center gap-4">
          <p className="font-serif text-2xl text-stone-300">休息室里没有这个人</p>
          <p className="text-sm text-stone-500">也许 ta 还没被写出来。</p>
          <Link to="/" className="text-sm text-gold hover:underline">
            ← 返回画廊
          </Link>
        </main>
      ) : (
        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-stage-700 px-6 py-3">
            <div className="flex items-center gap-3">
              <Avatar name={character.name} color={character.color} size={34} />
              <div>
                <div className="text-sm font-medium text-stone-100">{character.name}</div>
                <div className="font-mono text-[11px] text-stone-500">{character.id}</div>
              </div>
            </div>
            <nav className="flex gap-1">
              {TABS.map((t) => (
                <Link
                  key={t.key}
                  to={`/chat/${character.id}${t.suffix}`}
                  className={cn(
                    'rounded-md px-4 py-1.5 text-sm transition-colors',
                    tab === t.key ? 'bg-stage-800 text-gold' : 'text-stone-400 hover:bg-stage-800/60 hover:text-stone-200',
                  )}
                >
                  {t.label}
                </Link>
              ))}
            </nav>
          </header>

          <div className="min-h-0 flex-1 bg-stage-950/40">
            <AnimatePresence mode="wait">
              <motion.div
                key={`${character.id}:${tab}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.18 }}
                className="h-full"
              >
                {tab === 'chat' && <ChatTab character={character} />}
                {tab === 'diary' && <DiaryTab character={character} />}
                {tab === 'audit' && <MemoryTab character={character} />}
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      )}
    </div>
  )
}
