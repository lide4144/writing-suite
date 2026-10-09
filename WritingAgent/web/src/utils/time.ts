// 时间格式化工具

export function formatClock(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日`
}

/** 相对时间：「2 分钟前」「昨天」 */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const diff = now - new Date(iso).getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day === 1) return '昨天'
  if (day < 30) return `${day} 天前`
  return formatDate(iso)
}

/** 持续时间：「43 分钟」「2 小时 15 分钟」 */
export function formatDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return '—'
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  let min = Math.max(1, Math.floor((end - new Date(startIso).getTime()) / 60000))
  const hour = Math.floor(min / 60)
  min = min % 60
  if (hour === 0) return `${min} 分钟`
  if (min === 0) return `${hour} 小时`
  return `${hour} 小时 ${min} 分钟`
}
