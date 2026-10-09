import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Shell } from './components/shell/Shell'
import { GalleryPage } from './pages/GalleryPage'
import { WatchPage } from './pages/WatchPage'
import { SetupPage } from './pages/SetupPage'
import { ConsolePage } from './pages/ConsolePage'
import { NotFoundPage } from './pages/NotFoundPage'

/** 路由级页面过渡：淡入淡出（§11 Phase 4 页面切换动画） */
function PageTransition({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.22 }}
    >
      {children}
    </motion.div>
  )
}

export default function App() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route element={<Shell />}>
          <Route path="/" element={<PageTransition><GalleryPage /></PageTransition>} />
          <Route path="/stage/:sceneId/watch" element={<PageTransition><WatchPage /></PageTransition>} />
          <Route path="/stage/:sceneId/setup" element={<PageTransition><SetupPage /></PageTransition>} />
          <Route path="/chat/:characterId" element={<PageTransition><ConsolePage /></PageTransition>} />
          <Route path="/chat/:characterId/diary" element={<PageTransition><ConsolePage /></PageTransition>} />
          <Route path="/chat/:characterId/audit" element={<PageTransition><ConsolePage /></PageTransition>} />
          <Route path="/404" element={<PageTransition><NotFoundPage /></PageTransition>} />
          <Route path="*" element={<Navigate to="/404" replace />} />
        </Route>
      </Routes>
    </AnimatePresence>
  )
}
