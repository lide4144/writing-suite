// Mock API —— 对应 spec §9.1 的 REST 端点，全部以模拟延迟返回内存数据。
// 数据为模块级可变引用，写操作（更新日记/记忆、开演等）直接修改内存。

import type {
  CharacterInfo,
  CharacterState,
  ChatMessage,
  DiaryEntry,
  MemoryItem,
  Message,
  Scene,
  SceneSummary,
} from '../types'
import {
  CHARACTERS,
  CHARACTER_STATES,
  CHAT_HISTORY,
  DIARIES,
  MEMORIES,
  MESSAGES,
  SCENE_SUMMARIES,
  SCENES,
} from './data'

const LATENCY = 260

function delay<T>(value: T, ms: number = LATENCY): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

let idCounter = 1000
export function nextId(prefix: string): string {
  idCounter += 1
  return `${prefix}-${idCounter}`
}

// ---- 场景 ----

export function getScenes(): Promise<Scene[]> {
  const sorted = SCENES.filter((s) => !s.archived).sort(
    (a, b) => +new Date(b.lastActivityAt) - +new Date(a.lastActivityAt),
  )
  return delay(sorted)
}

export function getScene(sceneId: string): Promise<Scene | null> {
  return delay(SCENES.find((s) => s.id === sceneId) ?? null)
}

export function getSceneTimeline(sceneId: string): Promise<Message[]> {
  return delay(MESSAGES[sceneId] ?? [])
}

export function getSceneCharacters(sceneId: string): Promise<CharacterInfo[]> {
  const scene = SCENES.find((s) => s.id === sceneId)
  return delay(scene ? scene.characters : [])
}

export function getSceneState(sceneId: string): Promise<Record<string, CharacterState>> {
  return delay(CHARACTER_STATES[sceneId] ?? {})
}

export function getSceneSummary(sceneId: string): Promise<SceneSummary | null> {
  return delay(SCENE_SUMMARIES[sceneId] ?? null)
}

export function createScene(title = '未命名场景'): Promise<Scene> {
  const scene: Scene = {
    id: nextId('scene'),
    title,
    status: 'draft',
    description: '',
    characters: [...CHARACTERS],
    totalMessages: 0,
    startedAt: null,
    endedAt: null,
    lastActivityAt: new Date().toISOString(),
    hasUnreadEvents: false,
    setupScript: '',
  }
  SCENES.push(scene)
  return delay(scene, 180)
}

export function saveSceneDoc(sceneId: string, markdown: string, title?: string): Promise<void> {
  const scene = SCENES.find((s) => s.id === sceneId)
  if (scene) {
    scene.setupScript = markdown
    if (title !== undefined && title.trim()) scene.title = title.trim()
  }
  return delay(undefined, 150)
}

/** 开演：draft → running，返回更新后的场景 */
export function startScene(sceneId: string): Promise<Scene | null> {
  const scene = SCENES.find((s) => s.id === sceneId)
  if (scene) {
    scene.status = 'running'
    scene.startedAt = new Date().toISOString()
    scene.lastActivityAt = scene.startedAt
  }
  return delay(scene ?? null, 500)
}

/** 归档：从画廊列表隐藏（mock 阶段仅标记） */
export function archiveScene(sceneId: string): Promise<void> {
  const scene = SCENES.find((s) => s.id === sceneId)
  if (scene) scene.archived = true
  return delay(undefined, 150)
}

/** 删除：从数据集中移除场景及其时间线 */
export function deleteScene(sceneId: string): Promise<void> {
  const idx = SCENES.findIndex((s) => s.id === sceneId)
  if (idx >= 0) SCENES.splice(idx, 1)
  delete MESSAGES[sceneId]
  delete SCENE_SUMMARIES[sceneId]
  delete CHARACTER_STATES[sceneId]
  return delay(undefined, 150)
}

// ---- 角色 ----

export function getCharacters(): Promise<CharacterInfo[]> {
  return delay([...CHARACTERS])
}

export function getCharacter(characterId: string): Promise<CharacterInfo | null> {
  return delay(CHARACTERS.find((c) => c.id === characterId) ?? null)
}

// ---- 日记 ----

export function getDiaries(characterId: string): Promise<DiaryEntry[]> {
  const list = DIARIES.filter((d) => d.characterId === characterId).sort(
    (a, b) => +new Date(b.createdAt) - +new Date(a.createdAt),
  )
  return delay(list)
}

export function updateDiary(diaryId: string, patch: Partial<Pick<DiaryEntry, 'isImportant' | 'note'>>): Promise<void> {
  const entry = DIARIES.find((d) => d.id === diaryId)
  if (entry) Object.assign(entry, patch)
  return delay(undefined, 120)
}

// ---- 记忆 ----

export function getMemories(characterId: string): Promise<MemoryItem[]> {
  const list = MEMORIES.filter((m) => m.characterId === characterId).sort(
    (a, b) => +new Date(b.updatedAt) - +new Date(a.updatedAt),
  )
  return delay(list)
}

export function updateMemory(
  memoryId: string,
  patch: Partial<Pick<MemoryItem, 'content' | 'importance' | 'isActive' | 'tags'>>,
): Promise<void> {
  const item = MEMORIES.find((m) => m.id === memoryId)
  if (item) {
    Object.assign(item, patch)
    item.updatedAt = new Date().toISOString()
  }
  return delay(undefined, 120)
}

export function deleteMemories(memoryIds: string[]): Promise<void> {
  for (const id of memoryIds) {
    const idx = MEMORIES.findIndex((m) => m.id === id)
    if (idx >= 0) MEMORIES.splice(idx, 1)
  }
  return delay(undefined, 150)
}

/** 合并：source 并入 target，source 删除 */
export function mergeMemories(sourceId: string, targetId: string): Promise<void> {
  const source = MEMORIES.find((m) => m.id === sourceId)
  const target = MEMORIES.find((m) => m.id === targetId)
  if (source && target && sourceId !== targetId) {
    target.content = `${target.content}／${source.content}`
    target.tags = Array.from(new Set([...target.tags, ...source.tags]))
    target.importance = Math.max(target.importance, source.importance)
    target.updatedAt = new Date().toISOString()
    MEMORIES.splice(MEMORIES.indexOf(source), 1)
  }
  return delay(undefined, 150)
}

// ---- 聊天历史 ----

export function getChatHistory(characterId: string): Promise<ChatMessage[]> {
  return delay(CHAT_HISTORY[characterId] ?? [])
}

export function appendChatMessage(message: ChatMessage): void {
  const list = (CHAT_HISTORY[message.characterId] ??= [])
  list.push(message)
}

// ---- 直播追加：WS 模拟器推送的消息也写入时间线 ----

export function appendSceneMessage(message: Message): void {
  const list = (MESSAGES[message.sceneId] ??= [])
  list.push(message)
  const scene = SCENES.find((s) => s.id === message.sceneId)
  if (scene) {
    scene.totalMessages += 1
    scene.lastActivityAt = message.timestamp
  }
}
