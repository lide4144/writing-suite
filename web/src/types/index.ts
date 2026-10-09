// 数据契约 —— 对应 spec/FRONTEND_SPEC.md §9.2 / §9.3

export type SceneStatus = 'draft' | 'running' | 'ended'

export interface CharacterInfo {
  id: string
  name: string
  avatar: string // URL（mock 阶段以角色色 + 首字渲染）
  color: string // 主题色 hex
}

export interface Scene {
  id: string
  title: string
  status: SceneStatus
  description: string
  characters: CharacterInfo[]
  totalMessages: number
  startedAt: string | null // ISO timestamp
  endedAt: string | null
  lastActivityAt: string // ISO timestamp
  hasUnreadEvents: boolean
  setupScript: string // 场景设定文档（markdown）
  archived?: boolean // 归档后从画廊隐藏（快捷菜单「归档」）
}

export type MessageType = 'env' | 'npc' | 'action' | 'dialogue' | 'scene_change'

export interface Message {
  id: string
  sceneId: string
  timestamp: string // ISO timestamp
  type: MessageType
  characterId: string | null // null 表示 GM
  characterName: string
  characterAvatar: string
  content: string
  innerThought: string | null // 内心独白
  importance: number // 0-10
  chapter: string | null // 段落归属，如「午后」「冲突」「破冰」
}

export interface CharacterState {
  characterId: string
  emotion: string // 情绪标签，如 😊 平静
  innerThought: string
  lastMemoryActivity: {
    type: 'recall' | 'memorize'
    content: string
  } | null
}

export interface DiaryEntry {
  id: string
  characterId: string
  sceneId: string
  sceneTitle: string
  createdAt: string
  content: string
  wordCount: number
  isImportant: boolean
  note: string
}

export interface MemoryItem {
  id: string
  characterId: string
  content: string
  tags: string[]
  importance: number // 1-5
  createdAt: string
  updatedAt: string
  isActive: boolean
}

export interface NotificationEvent {
  id: string
  type: 'scene_ended' | 'milestone'
  sceneId: string
  sceneTitle: string
  message: string
  timestamp: string
  isRead: boolean
}

// ---- 角色控制台聊天消息 ----

export interface ChatMessage {
  id: string
  characterId: string
  role: 'user' | 'character'
  content: string
  timestamp: string
}

// ---- WebSocket 消息类型（§9.3） ----

export type WsSceneEvent =
  | { type: 'message'; data: Message }
  | { type: 'state_change'; data: { characterStates: Record<string, CharacterState> } }
  | { type: 'milestone'; data: { chapter: string; summary: string } }
  | { type: 'scene_ended'; data: { summary: string } }
  | { type: 'summary_ready'; data: { summary: string } }

export interface WsChatRequest {
  type: 'message'
  data: { content: string; fourthWall: boolean }
}

export type WsChatEvent =
  | { type: 'message'; data: { content: string; done: boolean } }
  | { type: 'diary_ready'; data: { entry: DiaryEntry } }

// ---- 场景摘要（补课模式 §5.4.6） ----

export interface SceneSummary {
  sceneId: string
  bullets: string[]
  generatedAt: string
}
