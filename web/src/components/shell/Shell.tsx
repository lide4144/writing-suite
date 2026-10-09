import { Outlet } from 'react-router-dom'
import { TopNav } from './TopNav'

// 全局 UI 外壳（§3）：顶部隐藏式导航栏 + 页面出口。
// 外壳不设统一页面背景——每个页面有自身的氛围/背景（§3.1）。
export function Shell() {
  return (
    <div className="min-h-full">
      <TopNav />
      <Outlet />
    </div>
  )
}
