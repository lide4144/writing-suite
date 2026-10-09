// 全局 store —— 通知、活跃场景、角色内部状态缓存（§3.2 / §5.5）

import { create } from 'zustand'
import type { CharacterState, NotificationEvent } from '../types'
import { NOTIFICATIONS, SCENES } from '../mock/data'

interface AppState {
  /** 当前正在运行的场景（导航栏中部指示器） */
  runningSceneId: string | null
  setRunningScene: (sceneId: string | null) => void

  notifications: NotificationEvent[]
  unreadCount: number
  addNotification: (event: NotificationEvent) => void
  markAllRead: () => void

  /** 角色内部状态缓存：scene:character_internal 推送更新，浮动面板展示时读取 */
  characterStates: Record<string, CharacterState>
  updateCharacterStates: (states: Record<string, CharacterState>) => void
}

export const useAppStore = create<AppState>((set) => ({
  runningSceneId: SCENES.find((s) => s.status === 'running')?.id ?? null,
  setRunningScene: (sceneId) => set({ runningSceneId: sceneId }),

  notifications: NOTIFICATIONS,
  unreadCount: NOTIFICATIONS.filter((n) => !n.isRead).length,
  addNotification: (event) =>
    set((state) => ({
      notifications: [event, ...state.notifications],
      unreadCount: state.unreadCount + 1,
    })),
  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, isRead: true })),
      unreadCount: 0,
    })),

  characterStates: {},
  updateCharacterStates: (states) =>
    set((state) => ({ characterStates: { ...state.characterStates, ...states } })),
}))
