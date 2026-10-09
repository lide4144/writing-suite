// 观众席数据钩子 —— 加载场景上下文（§9.1）并接入直播推送（§5.5）。
// 角色内部状态先入全局 store（characterStates），浮动仪表盘以 store 为准。

import { useEffect, useState } from 'react'
import type { CharacterInfo, Message, Scene, SceneSummary } from '../../types'
import {
  getScene,
  getSceneCharacters,
  getSceneState,
  getSceneSummary,
  getSceneTimeline,
  nextId,
} from '../../mock/api'
import { connectSceneSocket } from '../../mock/ws'
import { useAppStore } from '../../store/useAppStore'

/** 直播期间由 WS milestone 事件产生的里程碑标记（时间轴上的 ★） */
export interface LiveMilestone {
  id: string
  timestamp: string
  chapter: string
  summary: string
}

export interface SceneWatchData {
  scene: Scene | null
  messages: Message[]
  characters: CharacterInfo[]
  summary: SceneSummary | null
  loading: boolean
  notFound: boolean
  /** scene.status === 'ended' 或直播中途收到 scene_ended */
  ended: boolean
  liveMilestones: LiveMilestone[]
}

export function useSceneWatch(sceneId: string | undefined): SceneWatchData {
  const [scene, setScene] = useState<Scene | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [characters, setCharacters] = useState<CharacterInfo[]>([])
  const [summary, setSummary] = useState<SceneSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [endedLive, setEndedLive] = useState(false)
  const [liveMilestones, setLiveMilestones] = useState<LiveMilestone[]>([])

  const updateCharacterStates = useAppStore((s) => s.updateCharacterStates)
  const addNotification = useAppStore((s) => s.addNotification)
  const setRunningScene = useAppStore((s) => s.setRunningScene)

  // —— 初始数据：五个端点并行拉取 ——
  useEffect(() => {
    setScene(null)
    setMessages([])
    setCharacters([])
    setSummary(null)
    setLiveMilestones([])
    setEndedLive(false)
    setNotFound(false)

    if (!sceneId) {
      setNotFound(true)
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    Promise.all([
      getScene(sceneId),
      getSceneTimeline(sceneId),
      getSceneCharacters(sceneId),
      getSceneState(sceneId),
      getSceneSummary(sceneId),
    ]).then(([sceneData, timeline, chars, states, summaryData]) => {
      if (cancelled) return
      if (!sceneData) {
        setNotFound(true)
        setLoading(false)
        return
      }
      setScene(sceneData)
      setMessages([...timeline].sort((a, b) => +new Date(a.timestamp) - +new Date(b.timestamp)))
      setCharacters(chars)
      setSummary(summaryData)
      if (Object.keys(states).length > 0) updateCharacterStates(states)
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [sceneId, updateCharacterStates])

  // —— WebSocket：挂载连接，卸载关闭（§5.5）——
  useEffect(() => {
    if (!sceneId || loading || notFound || !scene) return
    const handle = connectSceneSocket(sceneId, (event) => {
      switch (event.type) {
        case 'message':
          setMessages((prev) => [...prev, event.data])
          break
        case 'state_change':
          updateCharacterStates(event.data.characterStates)
          break
        case 'milestone': {
          const timestamp = new Date().toISOString()
          setLiveMilestones((prev) => [
            ...prev,
            { id: nextId('milestone'), timestamp, chapter: event.data.chapter, summary: event.data.summary },
          ])
          addNotification({
            id: nextId('ntf'),
            type: 'milestone',
            sceneId,
            sceneTitle: scene.title,
            message: `里程碑 · ${event.data.chapter}：${event.data.summary}`,
            timestamp,
            isRead: false,
          })
          break
        }
        case 'scene_ended':
          setEndedLive(true)
          // 场景落幕，清掉导航栏的「运行中」指示器（若指向本场景）
          if (useAppStore.getState().runningSceneId === sceneId) setRunningScene(null)
          addNotification({
            id: nextId('ntf'),
            type: 'scene_ended',
            sceneId,
            sceneTitle: scene.title,
            message: `场景已落幕：${event.data.summary}`,
            timestamp: new Date().toISOString(),
            isRead: false,
          })
          break
        case 'summary_ready':
          // mock WS 已把新摘要写入 SCENE_SUMMARIES；这里拉取更新本地状态。
          // 不主动弹窗：观众正在现场，摘要弹窗留给下次进入时的补课模式（§5.4.6 / §5.5）
          void getSceneSummary(sceneId).then((s) => {
            if (s) setSummary(s)
          })
          break
      }
    })
    return () => handle.close()
  }, [sceneId, loading, notFound, scene, updateCharacterStates, addNotification, setRunningScene])

  return {
    scene,
    messages,
    characters,
    summary,
    loading,
    notFound,
    ended: endedLive || scene?.status === 'ended',
    liveMilestones,
  }
}
